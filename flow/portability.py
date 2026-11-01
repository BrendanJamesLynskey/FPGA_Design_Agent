#!/usr/bin/env python3
"""Portability check (brief 04f): does every SystemVerilog file a bench or checker uses compile in each simulator?

    python3 flow/portability.py designs/t1_dimmer_counter/verif/portability.yaml [--json OUT]

The YAML lists file sets; each set names the files, the top module, and what each tool must do:
``expect: {icarus: pass, verilator: pass, slang: pass, xsim: pass}`` (default pass everywhere). A tool that is
not installed is reported ``skipped`` (xsim in CI). The exit status is non-zero if any tool's result differs
from the expectation, so a set that is meant to fail in one tool (the negative fixture) is a check too.

Tools: Icarus 12 (iverilog -g2012 -t null), Verilator (--lint-only --assert --timing, errors only; every
executable in $PORT_VERILATORS, colon-separated, else ``verilator`` from PATH), slang (pyslang, errors only),
xsim (xvlog -sv, then xelab; skipped unless xvlog is on PATH or $XSIM_SETTINGS names Vivado's settings64.sh).
Raw tool messages only; no advice.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], env: dict | None = None, cwd: str | None = None) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd, timeout=600)
    return r.returncode, (r.stdout + r.stderr)


def _inc(flag: str, files: list[str]) -> list[str]:
    """Include directories: the folder of every file (the checkers include v_macros.svh next to them)."""
    return [f"{flag}{x}" for x in sorted({str(Path(f).parent) for f in files})]


def _first(pattern: str, text: str) -> str:
    m = re.search(pattern, text, re.M)
    return m.group(0).strip()[:300] if m else ""


def check_icarus(files: list[str], top: str, defines: list[str]) -> dict:
    exe = shutil.which("iverilog")
    if not exe:
        return {"status": "skipped", "why": "iverilog not installed"}
    ver = _run([exe, "-V"])[1].splitlines()[0]
    rc, out = _run([exe, "-g2012", "-t", "null", "-s", top] + [f"-D{d}" for d in defines] + _inc("-I", files) + files)
    return {"status": "pass" if rc == 0 else "fail", "version": ver, "message": "" if rc == 0 else out.strip().splitlines()[0][:300]}


def check_verilator(files: list[str], top: str, defines: list[str]) -> list[dict]:
    exes = [e for e in os.environ.get("PORT_VERILATORS", "").split(":") if e] or [shutil.which("verilator") or ""]
    out_rows = []
    for exe in exes:
        if not exe or not Path(exe).exists():
            out_rows.append({"tool": "verilator", "status": "skipped", "why": "verilator not installed"})
            continue
        env = dict(os.environ)
        root = Path(exe).parent.parent
        if (root / "include" / "verilated.h").is_file():   # a .deb extracted without root: bin/ sits in the root
            env["VERILATOR_ROOT"] = str(root)               # (apt and source installs find their own root)
        ver = _run([exe, "--version"], env)[1].strip().splitlines()[0]
        with tempfile.TemporaryDirectory() as td:
            rc, out = _run([exe, "--lint-only", "--assert", "--timing", "-Wno-fatal", "--top-module", top,
                            "-Mdir", td] + [f"-D{d}" for d in defines] + _inc("-I", files) + files, env)
        err = _first(r"^%Error.*", out)
        out_rows.append({"tool": "verilator", "status": "fail" if (rc != 0 or err) else "pass",
                         "version": ver, "message": err})
    return out_rows


_SLANG = """
import sys, pyslang
d = pyslang.driver.Driver()
d.addStandardArgs()
ok = d.parseCommandLine("slang " + " ".join(sys.argv[1:])) and d.processOptions() and d.parseAllSources()
ok = ok and d.runFullCompilation(False)
print("slang version", pyslang.__version__)
sys.exit(0 if ok else 1)
"""


def check_slang(files: list[str], top: str, defines: list[str]) -> dict:
    py = os.environ.get("SLANG_PYTHON", sys.executable)
    r = subprocess.run([py, "-c", "import pyslang"], capture_output=True)
    if r.returncode:
        return {"status": "skipped", "why": "pyslang not installed"}
    rc, out = _run([py, "-c", _SLANG, "--top", top] + [f"-D{d}" for d in defines] + _inc("-I", files) + files)
    ver = _first(r"slang version.*", out)
    return {"status": "pass" if rc == 0 else "fail", "version": ver,
            "message": "" if rc == 0 else _first(r"^.*error:.*", out) or out.strip()[:300]}


def check_xsim(files: list[str], top: str, defines: list[str]) -> dict:
    settings = os.environ.get("XSIM_SETTINGS")
    pre = f"source {settings} >/dev/null 2>&1; " if settings else ""
    if not settings and not shutil.which("xvlog"):
        return {"status": "skipped", "why": "xsim not available (no xvlog on PATH, XSIM_SETTINGS unset)"}
    with tempfile.TemporaryDirectory() as td:
        d = " ".join([f"-d {x}" for x in defines] + [f"-i {x}" for x in sorted({str(Path(f).parent) for f in files})])
        cmd = f"{pre}xvlog -sv {d} {' '.join(files)} && xelab -debug off {top} -s portability_snap"
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, cwd=td, timeout=900)
        out = r.stdout + r.stderr
    err = _first(r"^ERROR:.*", out)
    return {"status": "fail" if (r.returncode != 0 or err) else "pass", "version": "xsim (Vivado)", "message": err}


def check_set(spec: dict, base: Path) -> list[dict]:
    files = [str((base / f).resolve()) for f in spec["files"]]
    top, defines = spec["top"], spec.get("defines", [])
    rows = [{"tool": "icarus"} | check_icarus(files, top, defines)]
    rows += check_verilator(files, top, defines)
    rows += [{"tool": "slang"} | check_slang(files, top, defines), {"tool": "xsim"} | check_xsim(files, top, defines)]
    expect = spec.get("expect", {})
    for r in rows:
        want = expect.get(r["tool"], "pass")
        r["expect"] = want
        r["ok"] = r["status"] == "skipped" or r["status"] == want
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--json")
    a = ap.parse_args()
    cfg_path = Path(a.config).resolve()
    cfg = yaml.safe_load(cfg_path.read_text())
    report, bad = {}, 0
    for name, spec in cfg["sets"].items():
        rows = check_set(spec, ROOT)
        report[name] = rows
        for r in rows:
            flag = "ok " if r["ok"] else "BAD"
            print(f"{flag} {name:28s} {r['tool']:9s} {r['status']:8s} (want {r['expect']}) {r.get('version', '')} {r.get('message', r.get('why', ''))}")
            bad += not r["ok"]
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=2) + "\n")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
