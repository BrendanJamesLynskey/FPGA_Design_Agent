#!/usr/bin/env python3
"""One-command board self-check (brief 04c): program a design and run its selfcheck.py over the UART.

    python3 flow/board_check.py designs/b2_tmp_adt7420 [--runs 3] [--board nexys_a7_100t]

For each run (the first failed step stops that run):
  1. power_ok     the base build passes the power gate for the board's power source (flow/hw.py)
  2. discover     flow/hw_discover.py: exactly one JTAG target, an xc7a100t, and its UART
  3. program      flow/program.py <design> base (SRAM only, by cable serial; the gate is checked again)
  4. identify     DESIGN_ID is the one selfcheck.py names and BUILD_STAMP is the build's
  5. selfcheck    designs/<name>/selfcheck.py check(shell): its pass rule is in its docstring
  6. still_alive  identity unchanged, a scratch value written before the check kept, no shell errors
Writes results/board_v2/runs/<design>_<time>.json for each run and results/board_v2/<design>.json
(every run of this invocation). The cable serial appears only as its last 4 characters and no /dev
path is written. Exit 0 only if every run passed.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flow import hw, hw_discover, program  # noqa: E402
from shell.host import protocol as p  # noqa: E402
from shell.host.fpga_shell import FpgaShell, design_id_text  # noqa: E402

RESULTS = hw.ROOT / "results" / "board_v2"
SENTINEL = 0xB0A2_D042


class StepFailed(Exception):
    pass


class Run:
    def __init__(self, design: Path, board: str, log_root: Path) -> None:
        self.design, self.name, self.board_name = design, design.name, board
        self.check = importlib.import_module(f"designs.{design.name}.selfcheck")
        self.stamp_time = time.strftime("%Y%m%d_%H%M%S")
        self.log_dir = log_root / self.stamp_time
        self.log_dir.mkdir(parents=True, exist_ok=True)
        commit, dirty = hw.git_commit()
        self.res: dict[str, Any] = {"design": str(design.relative_to(hw.ROOT)),
                                    "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                    "git_commit": commit, "git_dirty": dirty, "steps": {}, "pass": False}
        self.secrets: list[str] = []

    def step(self, name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        print(f"board_check: {name} ...", flush=True)
        t0 = time.monotonic()
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001 - any failure is recorded as this step's
            r = {"pass": False, "why": self.scrub(f"{type(e).__name__}: {e}")}
        r["seconds"] = round(time.monotonic() - t0, 1)
        self.res["steps"][name] = r
        print(f"board_check: {name}: {'PASS' if r.get('pass') else 'FAIL'} ({r['seconds']} s)"
              + ("" if r.get("pass") else f": {r.get('why', '')}"), flush=True)
        if not r.get("pass"):
            raise StepFailed(name)
        return r

    def scrub(self, text: str) -> str:
        for s in self.secrets:
            if s:
                text = text.replace(s, hw.redact(s) or "")
        return re.sub(r"/dev/\S+", "<uart>", text)

    def power(self) -> dict[str, Any]:
        return hw.power_ok(self.design / "build" / "base", self.board_name)

    def discover(self) -> dict[str, Any]:
        r = hw_discover.discover(self.board_name, self.log_dir / "discover")
        self.board = hw.load_board(self.board_name)
        self.secrets = [self.board["cable_serial"], hw_discover.usb_serial(self.board["cable_serial"])]
        self.res["cable_serial"] = hw.redact(self.board["cable_serial"])
        self.res["vivado_version"] = r.get("vivado_version")
        return r

    def program(self) -> dict[str, Any]:
        r = program.program(self.design, "base", self.board["name"], self.log_dir / "program")
        self.res["build_stamp"] = r["build_stamp"]
        return r

    def identify(self) -> dict[str, Any]:
        with FpgaShell.open(self.board["uart"]) as sh:
            ident = sh.identify()
            sh.write(p.REG_SCRATCH, SENTINEL)
            sh.write(p.REG_STATUS, 0)
        ok = ident["design_id"] == self.check.DESIGN_ID and f"{ident['build_stamp']:08x}" == self.res["build_stamp"]
        return {"pass": ok, "design_id": design_id_text(ident["design_id"]),
                "build_stamp": f"{ident['build_stamp']:08x}", "shell_version": f"0x{ident['shell_version']:08X}",
                **({} if ok else {"why": "wrong design or stale bitstream on the board"})}

    def selfcheck(self) -> dict[str, Any]:
        with FpgaShell.open(self.board["uart"]) as sh:
            r = self.check.check(sh)
        if not r["pass"]:
            r["why"] = "the pass rule in selfcheck.py was not met"
        rule = (self.check.__doc__ or "").split("Pass rule", 1)[-1]
        r["rule"] = " ".join(("Pass rule" + rule).split())
        return r

    def still_alive(self) -> dict[str, Any]:
        with FpgaShell.open(self.board["uart"]) as sh:
            ident = sh.identify()
            scratch = sh.read(p.REG_SCRATCH)
            status = sh.status()
        ok = (f"{ident['build_stamp']:08x}" == self.res["build_stamp"] and scratch == SENTINEL
              and not any(status.values()))
        return {"pass": ok, "scratch_kept": scratch == SENTINEL, "status": status}

    def run(self) -> dict[str, Any]:
        t0 = time.monotonic()
        try:
            self.step("power_ok", self.power)
            self.step("discover", self.discover)
            self.step("program", self.program)
            self.step("identify", self.identify)
            self.step("selfcheck", self.selfcheck)
            self.step("still_alive", self.still_alive)
            self.res["pass"] = True
        except StepFailed as e:
            self.res["failed_step"] = str(e)
        self.res["seconds"] = round(time.monotonic() - t0, 1)
        return self.res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("design", type=Path)
    ap.add_argument("--board", default="nexys_a7_100t")
    ap.add_argument("--runs", type=int, default=1)
    a = ap.parse_args(argv)
    design = (hw.ROOT / a.design).resolve() if not a.design.is_absolute() else a.design
    log_root = hw.ROOT / "build" / "hw" / "board_check" / design.name
    (RESULTS / "runs").mkdir(parents=True, exist_ok=True)
    runs = []
    server = hw.HwServer(log_root)          # one hw_server for every run; stopped at the end
    try:
        server.__enter__()
        for i in range(a.runs):
            print(f"board_check: {design.name} run {i + 1} of {a.runs}", flush=True)
            run = Run(design, a.board, log_root)
            r = run.run()
            text = run.scrub(json.dumps(r, indent=2, default=str)) + "\n"
            (RESULTS / "runs" / f"{design.name}_{run.stamp_time}.json").write_text(text)
            runs.append(json.loads(text))
            if i + 1 < a.runs:
                time.sleep(1.0)              # distinct run times
    finally:
        server.__exit__(None, None, None)
    summary = {"design": str(design.relative_to(hw.ROOT)), "runs": len(runs),
               "passed": sum(r["pass"] for r in runs), "pass": all(r["pass"] for r in runs) and bool(runs),
               "results": runs}
    (RESULTS / f"{design.name}.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")
    print(f"board_check: {design.name}: {summary['passed']}/{summary['runs']} runs passed; "
          f"results/board_v2/{design.name}.json")
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
