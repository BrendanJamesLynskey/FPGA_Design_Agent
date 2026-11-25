#!/usr/bin/env python3
"""Brief 156: which PSL constructs each tool accepts, in simulation and in formal, and whether the verdict is right.

    python3 results/156_vhdl_tools/psl_probe.py [--out psl_constructs.json]

A one-bit design (``gnt`` is ``req`` registered, ``gnt`` starts low; ``req`` and ``rst`` are free inputs). Each probe is one PSL
directive written as VHDL-2008 PSL (``default clock is rising_edge(clk); assert always ...;``) and has an expected verdict: ``true`` (holds
for every input) or ``false`` (some input violates it). A tool is scored on whether it accepts the text, and whether its verdict
matches: in simulation, a testbench drives a fixed pattern that violates every ``false`` probe and the output must show an assertion
failure only for those; in formal, SymbiYosys ``bmc`` (depth 20, z3) must PASS a ``true`` probe and FAIL a ``false`` one, and ``cover``
must reach a cover directive.

Tools: simulation GHDL 4.1.0 mcode, GHDL 7.0.0-dev LLVM, NVC 1.23.1; formal: Yosys 0.33 + the Ubuntu GHDL 4.1.0 plugin (the CI-pinned
flavour) and Yosys 0.70 + the GHDL 7.0.0-dev plugin (OSS CAD Suite).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HOME = Path.home()

DUT = """library ieee;
use ieee.std_logic_1164.all;

entity p is
    port (clk, rst, req : in std_logic; gnt : out std_logic);
end entity p;

architecture rtl of p is
    signal g       : std_logic := '0';
    signal started : std_logic := '0';
    default clock is rising_edge(clk);
{decl}begin
    process (clk)
    begin
        if rising_edge(clk) then
            g       <= req;
            started <= '1';
        end if;
    end process;
    gnt <= g;
{body}
end architecture rtl;
"""

TB = """library ieee;
use ieee.std_logic_1164.all;

entity tb is end entity tb;

architecture sim of tb is
    signal clk : std_logic := '0';
    signal rst : std_logic := '1';
    signal req : std_logic := '0';
    signal gnt : std_logic;
    constant PAT : std_logic_vector(0 to 39) := "0010110111000101110010111000110101100111";
begin
    dut : entity work.p port map (clk => clk, rst => rst, req => req, gnt => gnt);
    process
    begin
        for i in 0 to 119 loop
            clk <= '0'; wait for 5 ns;
            clk <= '1'; wait for 5 ns;
        end loop;
        report "TB-DONE";
        wait;
    end process;
    process (clk)
        variable n : natural := 0;
    begin
        if rising_edge(clk) then
            if n > 3 then rst <= '0'; end if;
            req <= PAT(n mod 40) when (n > 3 and n < 105) else '0';
            n := n + 1;
        end if;
    end process;
end architecture sim;
"""

# name, expected ("true" holds, "false" is violated by the testbench and by some input), PSL text (lines of the architecture body),
# kind ("assert" or "cover"), extra file (a vunit) or None
PROBES = [
    ("always_next_impl", "true", "    assert always (req = '1' -> next (gnt = '1'));"),
    ("always_next_impl_bad", "false", "    assert always (req = '1' -> next (gnt = '0'));"),
    ("prev", "true", "    assert always (started = '1' -> gnt = prev(req));"),
    ("rose", "true", "    assert always ((started = '1' and rose(req)) -> next (gnt = '1'));"),
    ("fell", "true", "    assert always ((started = '1' and fell(req)) -> next (gnt = '0'));"),
    ("stable", "true", "    assert always ((started = '1' and stable(req)) -> next (stable(gnt)));"),
    ("onehot0_bad", "false", "    assert always (onehot0(req & gnt));"),
    ("onehot", "true", "    assert always (onehot(req & not req));"),
    ("sere_suffix_nonoverlap", "true", "    assert always ({req; req} |=> {gnt});"),
    ("sere_suffix_overlap", "true", "    assert always ({req; gnt} |-> {gnt});"),
    ("sere_repeat_overlap", "true", "    assert always ({req[*2]} |-> {gnt; gnt});"),
    ("sere_repeat_nonoverlap_bad", "false", "    assert always ({req[*2]} |=> {gnt[*2]});"),
    ("never_sere", "true", "    assert never {req; not gnt};"),
    ("until", "true", "    assert always (req = '1' -> next ((gnt = '1') until (req = '0')));"),
    ("eventually", "true", "    assert always (req = '1' -> eventually! (gnt = '1'));"),
    ("next_e_range", "true", "    assert always (req = '1' -> next_e[1 to 3] (gnt = '1'));"),
    ("next_a_range", "true", "    assert always (req = '1' -> next_a[1 to 1] (gnt = '1'));"),
    ("next_n", "true", "    assert always (req = '1' -> next[1] (gnt = '1'));"),
    ("before", "true", "    assert always (req = '1' -> next ((gnt = '1') before! (gnt = '0' and gnt = '1')));"),
    ("abort", "true", "    assert (always (req = '1' -> next (gnt = '1'))) abort rst;"),
    ("sync_abort", "true", "    assert (always (req = '1' -> next (gnt = '1'))) sync_abort rst;"),
    ("within", "true", "    assert always ({req; req} |-> ({gnt[*2]} within {true[*3]}));"),
    ("assume_then_assert", "true",
     "    assume always (not (req = '1' and rst = '1'));\n    assert always (not (req = '1' and rst = '1'));"),
    ("named_property_stmt_part", "true",
     "    sequence s_req_gnt is {req; gnt};\n    property p_follow is always (req = '1' -> next (gnt = '1'));\n"
     "    assert p_follow;\n    assert always ({s_req_gnt} |-> {gnt});"),
    ("named_property_decl_part", "true",
     "    sequence s_req_gnt is {req; gnt};\n    property p_follow is always (req = '1' -> next (gnt = '1'));\n@@"
     "    assert p_follow;\n    assert always ({s_req_gnt} |-> {gnt});"),
    ("assert_report", "false", "    assert always (req = '1' -> next (gnt = '0')) report \"gnt must follow req\" severity error;"),
    ("cover_sequence", "cover", "    cover {req; gnt; not gnt};"),
    ("cover_bad_unreachable", "cover-unreachable", "    cover {gnt = '1' and req = '1' and rst = '1' and gnt = '0'};"),
    ("restrict", "true", "    restrict {rst = '1'; rst = '0'[*]};\n    assert always (rst = '0' or req = '0' or true);"),
    ("fairness", "true", "    fairness req = '1';\n    assert always (eventually! (req = '1'));"),
    ("strong_next", "true", "    assert always (req = '1' -> next! (gnt = '1'));"),
]


def toolenv(kind: str) -> dict:
    e = dict(os.environ)
    if kind == "oss":
        e["PATH"] = f"{HOME}/.local/opt/oss-cad-suite/bin:{e['PATH']}"
    elif kind == "debformal":
        d = HOME / ".local/opt/formal-deb"
        e["PATH"] = f"{d}/sbyroot/bin:{d}/root/usr/bin:{e['PATH']}"
        e["LD_LIBRARY_PATH"] = f"{d}/root/usr/lib/x86_64-linux-gnu:{e.get('LD_LIBRARY_PATH', '')}"
        e["YOSYS_DATDIR"] = f"{d}/root/usr/share/yosys"
        e["PYTHONPATH"] = f"{d}/root/usr/share/yosys:{e.get('PYTHONPATH', '')}"
        e["GHDL_PREFIX"] = f"{HOME}/.local/opt/ghdl/lib/ghdl/mcode/vhdl"
    elif kind == "nvc":
        h = HOME / ".local/opt/nvc-1.23.1/root/usr"
        e["PATH"] = f"{h}/bin:{e['PATH']}"
        e["LD_LIBRARY_PATH"] = f"{h}/lib:{e.get('LD_LIBRARY_PATH', '')}"
        e["NVC_LIBPATH"] = f"{h}/lib/x86_64-linux-gnu/nvc"
    return e


def run(cmd, cwd, env, timeout=120):
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr)
    except subprocess.TimeoutExpired:
        return 124, "timeout"


ERR_RE = re.compile(r"cannot handle|error:|\*\* Error|Exception [A-Z_.]+ raised|sorry|not implemented|not supported|unexpected|Fatal|BUG|missing matching", re.I)


def first_error(out: str) -> str:
    """The first line of a tool's output that names the problem (one line, no paths)."""
    lines = [l for l in out.splitlines() if not l.strip().startswith("*****")]       # GHDL's "bug occurred" banner says nothing: its cause is the next lines
    for l in lines:
        if ERR_RE.search(l) and "GHDL Bug occurred" not in l:
            l = re.sub(r"/home/\S*?/(?=[^/\s]+\.vhd)", "", l)
            l = re.sub(r"SBY\s+[\d:]+\s+\[[^\]]*\]\s*", "", l)
            return l.strip()[:170]
    return out.strip().splitlines()[-1][:170] if out.strip() else "no output"


FAIL_RE = re.compile(r"assert|violat|failed", re.I)


def sim_probe(tool: str, d: Path, expected: str) -> dict:
    """tool: ghdl-mcode | ghdl-llvm | nvc. Returns {'accepted': bool, 'verdict': 'pass'|'fail'|None, 'note': str}."""
    if tool == "nvc":
        env = toolenv("nvc")
        rc, out = run(["nvc", "--std=2008", "-a", "p.vhd", "tb.vhd", "-e", "tb", "-r"], d, env)
    else:
        env = toolenv("oss") if tool == "ghdl-llvm" else dict(os.environ)
        rc, out = run(["ghdl", "-a", "--std=08", "-fpsl", "p.vhd", "tb.vhd"], d, env)
        if rc == 0:
            rc, out = run(["ghdl", "-e", "--std=08", "-fpsl", "tb"], d, env)
        if rc == 0:
            rc, out = run(["ghdl", "-r", "--std=08", "-fpsl", "tb"], d, env)
    done = "TB-DONE" in out
    if not done:
        return {"accepted": False, "verdict": None, "note": first_error(out) or f"rc {rc}"}
    bad = [l for l in out.splitlines() if "TB-DONE" not in l and FAIL_RE.search(l)]
    return {"accepted": True, "verdict": "fail" if bad else "pass", "note": (bad[0].strip()[:140] if bad else "")}


def formal_probe(kind: str, d: Path, task: str) -> dict:
    env = toolenv(kind)
    plug = "plugin -i ghdl" if kind == "oss" else f"plugin -i {HOME}/.local/opt/formal-deb/root/usr/lib/yosys/plugins/ghdl.so"
    sby = f"""[tasks]
bmc
cover

[options]
bmc: mode bmc
cover: mode cover
depth 20

[engines]
smtbmc z3

[script]
{plug}
ghdl --std=08 -fpsl {{files}} -e p
prep -top p

[files]
{{files}}
"""
    files = "p.vhd" + (" v.vhd" if (d / "v.vhd").is_file() else "")
    (d / f"f_{kind}.sby").write_text(sby.replace("{files}", files))
    out_dir = d / f"sby_{kind}_{task}"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    rc, out = run(["sby", "-f", "-d", str(out_dir), f"f_{kind}.sby", task], d, env, timeout=180)
    st = (out_dir / "status").read_text().split()[0] if (out_dir / "status").is_file() else None
    if st in ("PASS", "FAIL"):
        return {"accepted": True, "verdict": st.lower(), "note": ""}
    return {"accepted": False, "verdict": None, "note": first_error(out)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "psl_constructs.json"))
    ap.add_argument("--work", default=str(ROOT / "build" / "156_psl"))
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    work = Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    res = {"probes": {}, "tools": {"ghdl-mcode": "GHDL 4.1.0 mcode (Ubuntu package)", "ghdl-llvm": "GHDL 7.0.0-dev LLVM (OSS CAD Suite)",
                                   "nvc": "NVC 1.23.1", "formal-debgh": "Yosys 0.33 + GHDL 4.1.0 plugin + SymbiYosys",
                                   "formal-oss": "Yosys 0.70+385 + GHDL 7.0.0-dev plugin + SymbiYosys (OSS CAD Suite)"}}
    for name, exp, body, *_ in PROBES:
        if a.only and name not in a.only.split(","):
            continue
        d = work / name
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        decl, _, rest = body.partition("@@")
        decl, rest = (decl + "\n", rest) if rest else ("", body)
        (d / "p.vhd").write_text(DUT.format(decl=decl, body=rest))
        (d / "tb.vhd").write_text(TB)
        row = {"expected": exp, "text": body.replace("@@", "").strip(), "sim": {}, "formal": {}}
        for t in ("ghdl-mcode", "ghdl-llvm", "nvc"):
            row["sim"][t] = sim_probe(t, d, exp)
        for kind, label in (("debformal", "formal-debgh"), ("oss", "formal-oss")):
            task = "cover" if exp.startswith("cover") else "bmc"
            row["formal"][label] = dict(formal_probe(kind, d, task), task=task)
        res["probes"][name] = row
        print(name, {t: (r["accepted"], r["verdict"]) for t, r in {**row["sim"], **row["formal"]}.items()}, flush=True)
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
