#!/usr/bin/env python3
"""Formal equivalent-mutant filter (brief 143b): a SymbiYosys miter of a surviving mutant against the original RTL.

A mutant that the bench does not kill is either a real gap in the bench or an *equivalent* mutant: a change that cannot alter any
output (a dead branch, a bit nobody reads). Counting equivalents as survivors makes a good bench look bad; dropping them by hand
makes a bad bench look good (brief 143 report: GateTruth). The method here is the one of YosysHQ MCY (AppNote 400): decide each survivor
by a formal miter, and say what could not be decided.

``classify(...)`` returns one of

* ``equivalent``       the miter was proved: for every input sequence the original and the mutant show the same outputs (dropped
                       from the score's denominator and listed)
* ``not_equivalent``   a counterexample exists: a real survivor, the bench misses a behaviour that differs (the trace is kept)
* ``undecided``        neither within the time limit (BMC found nothing to ``bmc_depth`` clocks, the unbounded proof did not finish):
                       reported separately, never counted as killed, never as equivalent
* ``error``            the tool failed (not a pass; listed)
* ``skipped``          the OSS CAD Suite is not installed

How the miter is built. The mutant's copy of the RTL has every module renamed with a ``_mut`` suffix so that both versions sit in one
elaboration; the wrapper ``mt_miter`` instantiates the original and the mutant on the same free inputs and asserts that their outputs agree.
Outputs are compared always, or only when a *qualifier* output is high (a streaming interface: data is meaningful only with its valid),
as the target says. Reset: a target names a reset input and the number of clocks it is held (the wrapper assumes it for those clocks and
asserts nothing before), or has none (registers carry initial values). Every register still without an initial value starts at 0 in both versions
(``setundef -zero -init``, memories mapped to registers first): the two versions begin from the same power-up state, so a difference
is a difference of behaviour and not of two arbitrary start-up garbage values. ``assume`` lines constrain the free inputs to the protocol the
design is used under (for example ``!in_valid || in_ready``); a mutant that differs only under inputs the assumptions forbid is then
equivalent *under those assumptions*, which the record states.

The decision is of the configuration set the target gives (parameters and widths), not of every parameter value the RTL could take.
BMC runs first (a counterexample is a real difference from reset, and fast), then the unbounded proof: ``abc pdr`` for single-clock
targets, k-induction (``smtbmc``) for multi-clock ones. Every run has a wall-clock limit.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SBY_STATUS = ("PASS", "FAIL", "UNKNOWN", "ERROR", "TIMEOUT")


def suite_bin() -> Path | None:
    for c in (os.environ.get("FDA_OSS_CAD"), str(Path.home() / ".local/opt/oss-cad-suite")):
        if c and (Path(c) / "bin" / "sby").exists():
            return Path(c) / "bin"
    w = shutil.which("sby")
    return Path(w).parent if w else None


def _env() -> dict[str, str]:
    e = dict(os.environ)
    b = suite_bin()
    if b:
        e["PATH"] = f"{b}:{e.get('PATH', '')}"
    return e


def module_names(files: list[Path]) -> list[str]:
    names: list[str] = []
    for f in files:
        names += re.findall(r"^\s*module\s+(\w+)", f.read_text(errors="replace"), re.M)
    return names


def rename_modules(text: str, names: list[str], suffix: str = "_mut") -> str:
    """Every whole-word occurrence of a module name gets the suffix (definition and instantiation alike)."""
    if not names:
        return text
    rx = re.compile(r"\b(" + "|".join(sorted(map(re.escape, names), key=len, reverse=True)) + r")\b")
    return rx.sub(lambda m: m.group(1) + suffix, text)


def run_cmd(argv: list[str], cwd: Path, timeout: float) -> tuple[int, str]:
    """A command in its own process group, killed on timeout. Returns (rc, output); rc 124 on timeout."""
    p = subprocess.Popen(argv, cwd=cwd, env=_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, _ = p.communicate()
        return 124, out or ""


def port_table(files: list[Path], top: str, params: dict, work: Path) -> list[dict]:
    """The top's ports with their widths after elaboration with ``params`` (read through Yosys's JSON writer)."""
    g = " ".join(f"-G {k}={v}" for k, v in params.items())
    rc, out = run_cmd(["yosys", "-q", "-m", "slang", "-p", f"read_slang --top {top} {g} {' '.join(map(str, files))}; write_json {work / 'ports.json'}"], work, 120)
    if rc != 0:
        raise RuntimeError(f"cannot elaborate {top}: {out[-400:]}")
    mod = json.loads((work / "ports.json").read_text())["modules"][top]
    return [{"name": n, "dir": p["direction"], "width": len(p["bits"])} for n, p in mod["ports"].items()]


def wrapper_sv(top: str, params: dict, ports: list[dict], target: dict) -> str:
    """The miter module: both versions on the same inputs; the assertions are the outputs' agreement."""
    clocks = set(target.get("clocks") or [])
    rst = target.get("reset")
    qual = target.get("qualifiers") or {}         # data output -> the output that says it is meaningful
    pr = ", ".join(f".{k}({v})" for k, v in params.items())
    pdecl = f" #({pr})" if pr else ""
    L = ["module mt_miter ("]
    ins = [p for p in ports if p["dir"] == "input"]
    L.append(",\n".join(f"    input wire [{p['width'] - 1}:0] {p['name']}" for p in ins))
    L.append(");")
    outs = [p for p in ports if p["dir"] == "output"]
    for p in outs:
        L.append(f"    wire [{p['width'] - 1}:0] g_{p['name']}, m_{p['name']};")
    conn = lambda pre: ", ".join([f".{p['name']}({p['name']})" for p in ins] + [f".{p['name']}({pre}_{p['name']})" for p in outs])
    L.append(f"    {top}{pdecl} gold ({conn('g')});")
    L.append(f"    {top}_mut{pdecl} mut ({conn('m')});")
    if rst:
        c = rst["clock"]
        L.append(f"    reg [3:0] rst_n = 4'd0;\n    always @(posedge {c}) if (rst_n != 4'd{rst['cycles']}) rst_n <= rst_n + 4'd1;")
        L.append(f"    wire in_reset = (rst_n != 4'd{rst['cycles']});")
        act = "1'b1" if rst.get("active", 1) else "1'b0"
        L.append(f"    always @* if (in_reset) assume ({rst['port']}[0] == {act});")
    else:
        L.append("    wire in_reset = 1'b0;")
    for a in target.get("assume") or []:
        L.append(f"    always @* if (!in_reset) assume ({a});")
    for p in outs:
        n = p["name"]
        if n in qual:
            L.append(f"    always @* if (!in_reset) assert (g_{qual[n]} == m_{qual[n]} && (!g_{qual[n]} || g_{n} == m_{n}));")
        elif n not in set(qual.values()):
            L.append(f"    always @* if (!in_reset) assert (g_{n} == m_{n});")
    L.append("endmodule")
    return "\n".join(L) + "\n"


def sby_text(files: list[str], task: str, depth: int, multiclock: bool, timeout_s: int, engine: str) -> str:
    return (f"[options]\nmode {task}\ndepth {depth}\nmulticlock {'on' if multiclock else 'off'}\ntimeout {timeout_s}\n\n"
            f"[engines]\n{engine}\n\n[script]\nplugin -i slang\nread_slang --top mt_miter {' '.join(files)}\n"
            "prep -top mt_miter\nflatten\nmemory_map\ntechmap\nopt -fast\nsetundef -zero -init\nsetundef -zero\n\n[files]\n" + "\n".join(files) + "\n")


def _status(d: Path) -> str:
    for cand in sorted(d.glob("*/status")) + sorted(d.glob("status")):
        w = cand.read_text().split()
        if w:
            return w[0]
    return "ERROR"


def run_sby(workdir: Path, name: str, files: list[Path], task: str, depth: int, multiclock: bool, timeout_s: int, engine: str) -> tuple[str, str]:
    """One SymbiYosys job. Returns (status, log tail). The wall-clock limit is the job's timeout plus a margin; a kill is TIMEOUT."""
    names = []
    for f in files:
        if f.resolve().parent != workdir.resolve():
            shutil.copy(f, workdir / f.name)
        names.append(f.name)
    sby = workdir / f"{name}.sby"
    sby.write_text(sby_text(names, task, depth, multiclock, timeout_s, engine))
    rc, out = run_cmd(["sby", "-f", sby.name], workdir, timeout_s + 90)
    if rc == 124:
        return "TIMEOUT", out[-600:]
    if "DONE (PASS" in out:
        return "PASS", out[-600:]
    if "DONE (FAIL" in out:
        return "FAIL", out[-600:]
    if "DONE (UNKNOWN" in out or "TIMEOUT" in out or "timeout" in out.lower():
        return "UNKNOWN" if "DONE (UNKNOWN" in out else "TIMEOUT", out[-600:]
    return "ERROR", out[-600:]


def equiv_fast(top: str, params: dict, srcs: list[Path], work: Path, timeout_s: int) -> str:
    """The register-matched proof (Yosys ``equiv_make`` / ``equiv_induct``, the classic flow eqy automates): registers and outputs with the
    same name in the original and the mutant are matched and each cone is proved equal by induction, with the matched registers taken as equal.
    Returns ``proved``, ``not_proved`` (the method is incomplete: this is not a difference) or ``error``."""
    g = " ".join(f"-G {k}={v}" for k, v in params.items())
    script = (f"read_slang --top {top} --top {top}_mut {g} {' '.join(map(str, srcs))}; proc; opt_clean; memory_map; setundef -zero -init; "
              f"equiv_make {top} {top}_mut equiv; hierarchy -top equiv; flatten; async2sync; equiv_simple -seq 3; equiv_induct -seq 3; equiv_status -assert")
    rc, out = run_cmd(["yosys", "-q", "-m", "slang", "-p", script], work, timeout_s)
    if rc == 0:
        return "proved"
    if "unproven" in out or "Found" in out or "not proven" in out.lower() or "Equivalence" in out:
        return "not_proved"
    return "error" if rc != 124 else "not_proved"


def _changed_line_is_clocking(orig: list[Path], mut: list[Path]) -> bool:
    """True when a line that differs between the copies mentions a clock edge, an ``always`` or a clock gate: the register-matched proof does not
    see which clock a register runs on, so it is not used then (the BMC and unbounded miter still are)."""
    for a, b in zip(orig, mut):
        la, lb = a.read_text(errors="replace").splitlines(), b.read_text(errors="replace").splitlines()
        for x, y in zip(la, lb):
            if x != y and re.search(r"@|\balways|\bposedge|\bnegedge|\bclk\b|\bclock", x + " " + y):
                return True
    return False


def _classify(orig_files: list[Path], mutant_files: list[Path], target: dict, config: dict, bmc_depth: int = 30, bmc_s: int = 60,
             prove_s: int = 180, keep: Path | None = None) -> dict:
    """Decide one (original, mutant) pair under one configuration ``config`` = {params}. See the module docstring for the verdicts."""
    if suite_bin() is None:
        return {"verdict": "skipped", "note": "the OSS CAD Suite (sby, yosys-slang) is not installed"}
    top, params = target["top"], config.get("params") or {}
    work = Path(tempfile.mkdtemp(prefix="mt_eq_", dir=str(keep) if keep else None))
    res: dict = {}
    try:
        names = module_names(orig_files)
        extras = [Path(x) for x in target.get("extra_sources") or []]
        gold_files, mut_files = [], []
        for f in orig_files:
            shutil.copy(f, work / f"g_{f.name}")
            gold_files.append(work / f"g_{f.name}")
        for f in mutant_files:
            (work / f"m_{f.name}").write_text(rename_modules(f.read_text(errors="replace"), names))
            mut_files.append(work / f"m_{f.name}")
        ports = port_table([*extras, *gold_files], top, params, work)
        wrap = work / "mt_miter.sv"
        wrap.write_text(wrapper_sv(top, params, ports, target))
        multi = len(target.get("clocks") or []) > 1
        allf = [*extras, *gold_files, *mut_files, wrap]
        st, tail = run_sby(work, "bmc", allf, "bmc", bmc_depth, multi, bmc_s, "smtbmc boolector")
        res = {"bmc_depth": bmc_depth, "bmc_status": st}
        if st == "FAIL":
            return res | {"verdict": "not_equivalent", "note": f"counterexample within {bmc_depth} clocks", **({"trace_dir": str(work)} if keep else {})}
        if st == "ERROR":
            return res | {"verdict": "error", "note": tail[-300:]}
        if st == "TIMEOUT":
            res["note"] = f"BMC to {bmc_depth} clocks timed out after {bmc_s} s; "
        if not (multi and _changed_line_is_clocking(orig_files, mutant_files)):
            ef = equiv_fast(top, params, [*extras, *gold_files, *mut_files], work, 120)
            res["register_matched_proof"] = ef
            if ef == "proved" and st == "PASS":
                return res | {"verdict": "equivalent", "method": "register-matched induction (yosys equiv_induct) after a clean BMC", "note": ""}
        engine = "smtbmc boolector" if multi else "abc pdr"
        st2, tail2 = run_sby(work, "prove", allf, "prove", 24, multi, prove_s, engine)
        res["prove_status"], res["prove_engine"] = st2, engine
        if st2 == "PASS" and st == "PASS":
            return res | {"verdict": "equivalent", "method": f"unbounded proof ({engine}) after a clean BMC", "note": ""}
        if st2 == "FAIL":
            return res | {"verdict": "not_equivalent", "note": "counterexample found by the prove task"}
        if st2 == "ERROR":
            return res | {"verdict": "error", "note": tail2[-300:]}
        return res | {"verdict": "undecided", "note": res.get("note", "") + (f"BMC clean to {bmc_depth} clocks; " if st == "PASS" else "") + f"the unbounded proof ({engine}) ended {st2} within {prove_s} s"}
    except (RuntimeError, OSError, KeyError, json.JSONDecodeError) as e:
        return res | {"verdict": "error", "note": f"{type(e).__name__}: {e}"[:300]}
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)


def classify(*a, **k) -> dict:
    """``_classify`` with the wall-clock seconds added to the verdict record."""
    t0 = time.monotonic()
    r = _classify(*a, **k)
    r["seconds"] = round(time.monotonic() - t0, 1)
    return r
