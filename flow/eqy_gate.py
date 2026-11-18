#!/usr/bin/env python3
"""Formal equivalence gate: RTL against a netlist, with ``eqy`` (brief 101, part 2).

Any flow that changes logic outside Vivado's own synthesis (Yosys, direct primitives, RapidWright, hand edits) must pass this
gate before its result is reported: ``check(...)`` returns an ``EqyResult`` whose ``status`` is one of

* ``PASS``      eqy proved the gate netlist equivalent to the RTL under the stated strategy, 
* ``FAIL``      eqy found a difference (the counterexample is in the work directory)
* ``SKIPPED``   the OSS CAD Suite is not installed (CI and the agent print a notice; nothing is claimed)
* ``ERROR``     the tool failed (an unreadable netlist, a missing primitive model): never a pass

Gold is the RTL, read by the slang front end (as flow/checks/elab.py does). The gate is a Yosys-readable Verilog netlist whose
primitives (LUT1..6, FDRE, FDSE, FDCE, FDPE, CARRY4/8, MUXF7/8/9, GND, VCC, ...) are modelled by the Yosys ``cells_sim.v`` of
the pinned suite, written from the vendor-neutral public behaviour of the primitives; no AMD simulation model (UNISIM) is
read or shipped. It works for the Yosys netlist of flow/oss_synth.py and for a Vivado ``write_verilog -mode funcsim`` netlist.

Sequential designs, the matching strategies and their limits (the report, section "How eqy is used", repeats this). Both
sides first run ``sim -w`` for two reset clocks, so every register starts from its post-reset value instead of an unknown:

* ``name``   registers correspond by name. ``rename -hide`` leaves public only the output wire of each register and the ports
             (the gate's own cell and net names are hidden first, so the surviving alias of a register's net is the RTL
             name); eqy matches those names between gold and gate, cuts the design at the matched registers and proves each
             cone by induction (depth 2, bitwuzla). An unbounded proof, quick, but it treats the matched registers as free:
             a register pair that differs only in a state the design can never reach (a counter bit that is always 0 and was
             removed by synthesis) fails here although the circuits behave the same. A register moved, merged, duplicated
             or renamed by the flow has no partner by name: it is then inside a partition instead of at a cut point (listed in
             ``unmatched_*``), which is still a proof, only a harder one; ``group`` does not need names at all.
* ``group``  all state in one partition, no cut points, engine ``abc pdr`` (property-directed reachability, which finds the
             invariant itself): proves the outputs equal for every input sequence from the post-reset state. Unbounded, slower
             (minutes where ``name`` takes seconds), and independent of register names, so it also covers retimed designs.
* ``bmc``    the same single partition, bounded model checking to 24 clocks from the post-reset state: a counterexample is a real
             difference; no counterexample proves nothing (it is only the quick first step of ``auto``).
* ``auto``   (default) ``name``; if that does not prove, ``bmc`` looks for a real counterexample from reset, and only if there is
             none does ``group`` try the proof.

Limits that hold for every strategy: INIT values are not compared (the RTL has no initial values; the post-reset state is
what is proved); the reset must be a synchronous input named ``rst`` (``reset=`` changes the name); a clock named ``clk``;
primitives other than those in the pinned suite's ``cells_sim.v`` (DSP48, RAMB, GT, clocking) are not modelled, and a netlist
that uses one is ERROR, not a pass; the proof is of the netlist's function, not of its timing or placement; the equivalence
is of the netlist text given, so it covers a Vivado post-synthesis netlist and a RapidWright netlist only if they are
written out as Verilog (a routed design's ``write_verilog`` is such a netlist).

Fault injection (``plant``) edits a netlist to show the gate catches what it should: a flipped LUT INIT bit, two swapped
registers, a register whose reset value was dropped.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from flow.checks.elab import find_tool
from flow.checks.elab import version as yosys_version


@dataclass
class EqyResult:
    status: str
    seconds: float = 0.0
    strategy: str = "name"
    depth: int = 2
    partitions: int = 0
    proved: int = 0
    unmatched_gold: list[str] = field(default_factory=list)
    unmatched_gate: list[str] = field(default_factory=list)
    message: str = ""
    workdir: str = ""
    eqy: str = ""

    def ok(self) -> bool:
        return self.status == "PASS"

    def notice(self) -> str:
        return f"eqy {self.status} ({self.strategy}, depth {self.depth}): {self.message}"


def find_eqy() -> tuple[str, dict[str, str]] | None:
    t = find_tool()
    if t is None:
        return None
    eqy = Path(t[0]).with_name("eqy")
    return (str(eqy), t[1]) if eqy.is_file() else None


def version() -> str:
    t = find_eqy()
    if not t:
        return ""
    try:
        return subprocess.run([t[0], "--version"], capture_output=True, text=True, env=t[1], timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


HIDE_ALL_BUT_FF = "opt_clean -purge\nselect -set keep t:$*dff* %co:+[Q] w:* %i\nrename -hide w:* @keep %d i:* %d o:* %d"
HIDE_ALL_BUT_PORTS = "rename -hide w:* i:* %d o:* %d"


def config(top: str, gold: list[str], gate: str, strategy: str, depth: int, engine: str, work: Path, reset: str | None = "rst", join: bool = False) -> str:
    engines = f"engine {engine}"
    collect = f"[collect {top}]\ngroup *" if join else ""
    init = (f"sim -w -clock clk -reset {reset} -rstlen 2 -n 2" if reset else "sim -w -clock clk -n 6")
    hide = HIDE_ALL_BUT_FF if strategy in ("name", "group") else HIDE_ALL_BUT_PORTS
    srcs = " ".join(str(Path(s).resolve()) for s in gold)
    return f"""[gold]
plugin -i slang
read_slang --top {top} {srcs}
hierarchy -top {top}
flatten
prep -top {top}
memory_map
{hide}

[gate]
read_verilog -sv +/xilinx/cells_sim.v
read_verilog -sv {Path(gate).resolve()}
hierarchy -top {top}
rename -hide c:*
rename -hide w:_*_ w:*_n_[0-9]* %u
flatten
prep -top {top}
memory_map
delete =A:whitebox =A:blackbox
{hide}

[script]
hierarchy -top {top}
{init}

{collect}

[strategy sby]
use sby
depth {24 if strategy == "bmc" else depth}
{engines}
"""


def _ids(path: Path) -> set[str]:
    out = set()
    for ln in path.read_text().splitlines():
        p = ln.split()
        if len(p) >= 2 and not ln.startswith("#") and p[1] != "." and not p[1].startswith("$") and not any(x.startswith("c=") for x in p[2:]):
            out.add(p[1])
    return out


def check(top: str, gold: list[str], gate: str, work: Path, strategy: str = "auto", depth: int = 2, timeout: int = 1500,
          reset: str | None = "auto", evidence_dir: Path | None = None) -> EqyResult:
    """Prove ``gate`` equivalent to ``gold``; see the module docstring for the statuses and strategies. ``auto`` runs ``name``
    first; only if it does not prove, ``group`` decides (a ``name`` failure may be an unreachable state: see ``group``)."""
    res = _check(top, gold, gate, work, strategy, depth, timeout, reset)
    work.mkdir(parents=True, exist_ok=True)
    (work / "result.json").write_text(json.dumps(asdict(res), indent=1))      # the final verdict (sub-runs keep their own)
    if evidence_dir is not None:
        record(res, gold, gate, evidence_dir)
    return res


def _check(top, gold, gate, work, strategy, depth, timeout, reset) -> EqyResult:
    if strategy != "auto":
        return _run(top, gold, gate, work, strategy, depth, timeout, reset)
    r1 = _run(top, gold, gate, work / "name", "name", depth, timeout, reset)
    if r1.status in ("PASS", "SKIPPED", "ERROR"):
        return r1
    # a real counterexample from reset is found quickly by bounded model checking over the whole design (one partition); only
    # if there is none is the (slow) PDR proof tried
    rb = _run(top, gold, gate, work / "bmc", "bmc", depth, timeout, reset)
    if rb.status == "FAIL" and any("BMC failed" in f.read_text(errors="replace") for f in Path(rb.workdir).glob("strategies/*/sby/*/logfile.txt")):
        rb.message = f"name strategy: {r1.status} ({r1.message}); whole design from reset: counterexample within 24 clocks"
        rb.seconds = round(r1.seconds + rb.seconds, 1)
        return rb
    r2 = _run(top, gold, gate, work / "group", "group", depth, timeout, reset)
    r2.message = f"name strategy: {r1.status} ({r1.message}); group strategy: {r2.message}"
    r2.seconds = round(r1.seconds + rb.seconds + r2.seconds, 1)
    return r2


def _strip_glbl(gate: str, work: Path) -> str:
    """Vivado's ``write_verilog -mode funcsim`` appends the simulation scaffolding module ``glbl`` (global set/reset nets with
    ``tri1``/``tri (weak1, strong0)`` strengths that Yosys cannot parse). It holds no logic of the design (nothing instantiates it
    in the netlist: the primitives are modelled by the suite's cells_sim.v), so a copy without it is read; the recorded hash is of
    the netlist as written, not of the copy."""
    text = Path(gate).read_text()
    m = re.search(r"^module glbl\b.*?^endmodule\b[^\n]*\n?", text, re.S | re.M)
    if not m:
        return gate
    out = work / "gate_without_glbl.v"
    out.write_text(text[:m.start()] + text[m.end():])
    return str(out)


def _run(top: str, gold: list[str], gate: str, work: Path, strategy: str, depth: int, timeout: int, reset: str | None) -> EqyResult:
    if reset == "auto":      # the top of the wrapper has a port named rst, or the designs are state-free from the clock only
        reset = "rst" if any(re.search(r"\binput\b[^;)]*\brst\b", Path(g).read_text()) for g in gold) else None
    engine = "abc pdr" if strategy == "group" else "smtbmc bitwuzla"
    join = strategy in ("group", "bmc")
    t = find_eqy()
    if t is None:
        return EqyResult("SKIPPED", strategy=strategy, depth=depth,
                         message="eqy (OSS CAD Suite 20261112) not found: set FDA_OSS_CAD or install it under ~/.local/opt/oss-cad-suite; "
                                 "nothing is claimed about this netlist")
    eqy, env = t
    work.mkdir(parents=True, exist_ok=True)
    gate = _strip_glbl(gate, work)
    cfg = work / "gate.eqy"
    cfg.write_text(config(top, gold, gate, strategy, depth, engine, work, reset, join))
    t0 = time.time()
    # own process group, so that a timeout also ends eqy's children (sby, abc, bitwuzla), which would otherwise run on
    p = subprocess.Popen([eqy, "-f", "-d", str(work / "eqy"), str(cfg)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
                         cwd=work, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return EqyResult("ERROR", time.time() - t0, strategy, depth, message=f"eqy timed out after {timeout} s", workdir=str(work / "eqy"))
    r = subprocess.CompletedProcess(p.args, p.returncode, out, err)
    secs = round(time.time() - t0, 1)
    log = r.stdout + r.stderr
    (work / "eqy.log").write_text(log)
    wd = work / "eqy"
    res = EqyResult("ERROR", secs, strategy, depth, workdir=str(wd), eqy=version())
    parts = re.findall(r"(?:Successfully proved|Failed to prove) equivalence of partition (\S+)", log)
    res.partitions = len(parts)
    res.proved = len(re.findall(r"Successfully proved equivalence of partition", log))
    if wd.exists() and (wd / "gold.ids").exists() and (wd / "matched.ids").exists():
        gold_ids, gate_ids = _ids(wd / "gold.ids"), _ids(wd / "gate_recoded.ids" if (wd / "gate_recoded.ids").exists() else wd / "gate.ids")
        matched = {ln.split()[1] for ln in (wd / "matched.ids").read_text().splitlines() if ln and not ln.startswith("#") and len(ln.split()) >= 3}
        res.unmatched_gold = sorted(gold_ids - matched)
        res.unmatched_gate = sorted(gate_ids - matched)
    if "DONE (PASS" in log and r.returncode == 0 and (res.proved >= 1 or strategy in ("group", "bmc")):
        res.status = "PASS"
        if strategy == "group":
            res.message = "one partition (all state), abc pdr: proved from the post-reset state"
        else:
            res.message = f"{res.proved} partition(s) proved"
            if res.unmatched_gold or res.unmatched_gate:
                res.message += (f"; {len(res.unmatched_gold)} gold and {len(res.unmatched_gate)} gate public names have no partner "
                                f"(they sit inside a partition, not at a cut point: {(res.unmatched_gold + res.unmatched_gate)[:3]})")
    elif "DONE (FAIL" in log or "Failed to prove" in log:
        res.status = "FAIL"
        res.message = f"{res.partitions - res.proved} of {res.partitions} partition(s) not proved"
    else:
        res.message = (log.strip().splitlines() or ["no output"])[-1][:300]
    (work / "result.json").write_text(json.dumps(asdict(res), indent=1))
    return res


# ------------------------------------------------------------------------------------------------------ the evidence and the gate
EVIDENCE = "eqy_result.json"
#: a build directory keeps one directory per non-Vivado netlist under ``oss_netlists/<name>/``: the netlist, its synth.json, and
#: (written by ``record``) the eqy result bound to the netlist's and the sources' hashes
NETLIST_DIR = "oss_netlists"


def sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(res: EqyResult, gold: list[str], netlist: str, dest: Path) -> Path:
    """Write ``<dest>/eqy_result.json``: the result bound to the exact netlist and RTL it was proved for."""
    f = dest / EVIDENCE
    dest.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({**asdict(res), "netlist": str(netlist), "netlist_sha256": sha256(netlist),
                             "gold_sha256": {str(g): sha256(g) for g in gold},
                             "dir_sha256": {n.name: sha256(n) for n in sorted([*dest.glob("*.v"), *dest.glob("*.edif")])}, "yosys": yosys_version()}, indent=1))
    return f


def evidence(build_dir: Path) -> dict | None:
    """The gate's view of a build directory: None when no flow outside Vivado's synthesis wrote a netlist there; otherwise
    ``{"pass": bool, "netlists": {name: reason-or-"PASS"}}``. A netlist passes only with an ``eqy_result.json`` whose status is
    PASS and whose recorded hashes equal the netlist now on disk and the RTL it names (an edited netlist or changed RTL must be
    proved again); no result, a FAIL, SKIPPED or ERROR, or a stale hash all fail. Fail closed."""
    root = Path(build_dir) / NETLIST_DIR
    if not root.is_dir():
        return None
    out: dict[str, str] = {}
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        nets = sorted(d.glob("*.v")) + sorted(d.glob("*.edif"))
        if not nets:
            continue
        f = d / EVIDENCE
        if not f.is_file():
            out[d.name] = "no eqy result: run the eqy gate before reporting this netlist"
            continue
        try:
            r = json.loads(f.read_text())
            if r["status"] != "PASS":
                out[d.name] = f"eqy {r['status']}: {r.get('message', '')[:120]}"
            elif Path(r["netlist"]).resolve().parent != d.resolve():
                out[d.name] = "the proof names a netlist outside this directory"
            elif sha256(r["netlist"]) != r["netlist_sha256"]:
                out[d.name] = "the netlist changed after it was proved"
            elif any(sha256(n) != r.get("dir_sha256", {}).get(n.name) for n in nets):
                out[d.name] = "a netlist or EDIF in this directory changed (or was added) after the proof"
            elif any(not Path(g).is_file() or sha256(g) != h for g, h in r["gold_sha256"].items()):
                out[d.name] = "the RTL changed after the netlist was proved"
            else:
                out[d.name] = "PASS"
        except (OSError, KeyError, ValueError) as e:
            out[d.name] = f"unreadable eqy result ({type(e).__name__})"
    if not out:
        return None
    return {"pass": all(v == "PASS" for v in out.values()), "netlists": out}


# ----------------------------------------------------------------------------------------------------- fault injection
_INST = re.compile(r"(?P<type>\b(?:LUT[1-6]|FDRE|FDSE|FDCE|FDPE)\b)\s*(?:#\s*\((?P<params>.*?)\)\s*)?(?P<name>\\?\S+)\s*\((?P<ports>.*?)\)\s*;", re.S)


def instances(text: str, kinds: tuple[str, ...]) -> list[re.Match]:
    return [m for m in _INST.finditer(text) if m.group("type") in kinds]


def _port(ports: str, pin: str) -> re.Match | None:
    return re.search(rf"\.{pin}\s*\(\s*(.*?)\s*\)\s*(?=,|$)", ports, re.S)


def plant(text: str, kind: str, which: int = 0) -> tuple[str, str]:
    """A copy of the netlist text with one planted fault, and a one-line description. ``which`` picks the instance
    (modulo the number available). Kinds:

    * ``lut_init``    flip one INIT bit of a LUT (bit ``which * 7 % width``: a different bit for each ``which``; a flipped bit on an input
                      combination the design never reaches is an equivalent mutant, which a correct checker passes)
    * ``swap_regs``   exchange the D inputs of two registers (of the same type when there is one)
    * ``reset_value`` a register that was set by reset becomes one that is cleared (FDSE -> FDRE, S pin to R)
    * ``reset_drop``  a register's reset pin tied low (the reset value is lost)
    """
    if kind == "lut_init":
        ms = [m for m in instances(text, ("LUT2", "LUT3", "LUT4", "LUT5", "LUT6")) if m.group("params") and re.search(r"INIT", m.group("params"))]
        m = ms[which % len(ms)]
        p = m.group("params")
        im = re.search(r"(\d+)'([hbd])([0-9a-fA-FxX_]+)", p)
        width, base, val = int(im.group(1)), im.group(2), im.group(3)
        n = int(val.replace("_", ""), {"h": 16, "b": 2, "d": 10}[base]) ^ (1 << (which * 7 % width))
        digits = f"{n:0{(width + 3) // 4}x}" if base == "h" else f"{n:0{width}b}" if base == "b" else str(n)
        new_p = p[:im.start(3)] + digits + p[im.end(3):]
        new = text[:m.start("params")] + new_p + text[m.end("params"):]
        return new, f"flipped INIT bit {which * 7 % width} of LUT {m.group('name')}: {val} -> {digits}"
    if kind in ("swap_regs", "reset_value", "reset_drop"):
        kinds = ("FDRE", "FDSE", "FDCE", "FDPE") if kind == "swap_regs" else ("FDSE",) if kind == "reset_value" else ("FDRE", "FDSE")
        ms = instances(text, kinds)
        if kind in ("reset_value", "reset_drop"):      # only registers whose reset pin is really used
            ms = [m for m in ms if (_port(m.group("ports"), "S" if m.group("type") == "FDSE" else "R") or [None, "1'h0"])[1] not in ("1'h0", "1'b0")]
        if kind == "swap_regs":
            ms = [m for m in ms if _port(m.group("ports"), "D") and _port(m.group("ports"), "Q")]
        if not ms:
            raise ValueError(f"no register to plant a {kind} fault in")
        m = ms[which % len(ms)]
        if kind == "swap_regs":
            a = m
            others = [x for x in ms if x is not a and _port(x.group("ports"), "D").group(1) != _port(a.group("ports"), "D").group(1)]
            b = next((x for x in others if x.group("type") == a.group("type")), others[0] if others else None)
            if b is None:
                raise ValueError("no second register to swap with")
            da, db = _port(a.group("ports"), "D"), _port(b.group("ports"), "D")
            first, second = (a, b) if a.start() < b.start() else (b, a)
            d1, d2 = _port(first.group("ports"), "D"), _port(second.group("ports"), "D")
            o1 = first.start("ports") + d1.start(1)
            o2 = second.start("ports") + d2.start(1)
            new = text[:o1] + d2.group(1) + text[o1 + len(d1.group(1)):o2] + d1.group(1) + text[o2 + len(d2.group(1)):]
            return new, f"swapped the D inputs of registers {a.group('name')} and {b.group('name')}"
        ports = m.group("ports")
        if kind == "reset_value":
            sp = _port(ports, "S")
            new_ports = ports[:sp.start()] + ".R(" + sp.group(1) + ")" + ports[sp.end():]
            seg = text[m.start():m.end()].replace("FDSE", "FDRE", 1)
            seg = seg[:m.start("ports") - m.start()] + new_ports + seg[m.end("ports") - m.start():]
            return text[:m.start()] + seg + text[m.end():], f"register {m.group('name')}: set-by-reset (FDSE) became clear-by-reset (FDRE)"
        pin = "S" if m.group("type") == "FDSE" else "R"
        sp = _port(ports, pin)
        new_ports = ports[:sp.start()] + f".{pin}(1'h0)" + ports[sp.end():]
        return text[:m.start("ports")] + new_ports + text[m.end("ports"):], f"register {m.group('name')}: reset pin {pin} tied low"
    raise ValueError(f"unknown fault kind {kind!r}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--top", required=True)
    ap.add_argument("--gold", nargs="+", required=True, help="RTL sources (SystemVerilog)")
    ap.add_argument("--gate", required=True, help="netlist Verilog (Yosys or Vivado funcsim)")
    ap.add_argument("--work", required=True, type=Path)
    ap.add_argument("--strategy", default="auto", choices=("auto", "name", "group"))
    ap.add_argument("--depth", type=int, default=2)
    ap.add_argument("--evidence", type=Path, help="write eqy_result.json here (a build's oss_netlists/<name>/ directory)")
    a = ap.parse_args(argv)
    r = check(a.top, a.gold, a.gate, a.work, a.strategy, a.depth, evidence_dir=a.evidence)
    print(r.notice())
    return 0 if r.ok() else (0 if r.status == "SKIPPED" else 1)


if __name__ == "__main__":
    sys.exit(main())
