#!/usr/bin/env python3
"""One-command bring-up on the attached board: discover, program, test over UART, capture with the ILA.

    python3 flow/bringup.py designs/t1_dimmer_counter [--board nexys_a7_100t] [--keep-captures]

Steps (each recorded with pass/fail and its time; the first failure stops the run):
  1. power_ok_usb  both bitstreams' report_power total on-chip power <= 0.5 W (USB-powered board)
  2. discover      flow/hw_discover.py: exactly one JTAG target, an xc7a100t, and its UART
  3. program_base  flow/program.py <design> base (SRAM only, by cable serial)
  4. uart_tests    pytest -m hw on designs/<name>/tests/test_*_hw.py with the build stamp
  5. program_ila   flow/program.py <design> ila (bitstream + .ltx)
  6. ila_captures  flow/ila_capture.tcl in Vivado, driven in step over the UART by
                   designs/<name>/hw_checks.py; each capture exported to CSV + VCD and checked
  7. still_alive   the design still answers with the same identity and a scratch value
                   written before the captures (a reset or brown-out would clear it)
Writes results/f0b/<design>_bringup.json (this run) and results/f0b/runs/<design>_<time>.json;
logs and captures go to build/hw/<time>/ (with --keep-captures the CSV/VCD files and the pytest
log are copied to results/f0b/captures/). The cable serial appears only as its last 4
characters, and no /dev path is written to results/. Exit 0 only if every step passed.
"""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flow import hw, hw_discover, ila, program  # noqa: E402
from shell.host import protocol as p  # noqa: E402
from shell.host.fpga_shell import FpgaShell  # noqa: E402

RESULTS = hw.ROOT / "results" / "f0b"
SENTINEL = 0x5EED_F0B0


class StepFailed(Exception):
    pass


class Run:
    def __init__(self, design: Path, board: str | None, keep: bool) -> None:
        self.design = design
        self.name = design.name
        self.board_name = board
        self.keep = keep
        self.stamp_time = time.strftime("%Y%m%d_%H%M%S")
        self.log_dir = hw.ROOT / "build" / "hw" / self.stamp_time
        self.log_dir.mkdir(parents=True, exist_ok=True)
        commit, dirty = hw.git_commit()
        self.res: dict[str, Any] = {
            "design": str(design.relative_to(hw.ROOT)), "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "git_commit": commit, "git_dirty": dirty, "steps": {}, "pass": False}
        self.secrets: list[str] = []

    # --- bookkeeping ------------------------------------------------------------------
    def step(self, name: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        print(f"bringup: {name} ...", flush=True)
        t0 = time.monotonic()
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001 - any failure is recorded as this step's
            r = {"pass": False, "why": self.scrub(f"{type(e).__name__}: {e}")}
        r["seconds"] = round(time.monotonic() - t0, 1)
        self.res["steps"][name] = r
        print(f"bringup: {name}: {'PASS' if r.get('pass') else 'FAIL'} ({r['seconds']} s)"
              + ("" if r.get("pass") else f": {r.get('why', r.get('errors', ''))}"), flush=True)
        if not r.get("pass"):
            raise StepFailed(name)
        return r

    def scrub(self, text: str) -> str:
        for s in self.secrets:
            if s:
                text = text.replace(s, hw.redact(s) or "")
        return re.sub(r"/dev/\S+", "<uart>", text)

    # --- steps --------------------------------------------------------------------------
    def power(self) -> dict[str, Any]:
        r = {v: hw.power_ok_usb(self.design / "build" / v) for v in ("base", "ila")}
        return {"pass": all(x["pass"] for x in r.values()), "limit_w": hw.USB_POWER_LIMIT_W, **r}

    def discover(self) -> dict[str, Any]:
        r = hw_discover.discover(self.board_name or "nexys_a7_100t", self.log_dir / "discover")
        self.board = hw.load_board(self.board_name or "nexys_a7_100t")
        self.secrets = [self.board["cable_serial"], hw_discover.usb_serial(self.board["cable_serial"])]
        self.res["cable_serial"] = hw.redact(self.board["cable_serial"])
        self.res["vivado_version"] = r.get("vivado_version")
        return r

    def program(self, variant: str) -> dict[str, Any]:
        gate = hw.power_ok_usb(self.design / "build" / variant)   # checked again right before programming
        if not gate["pass"]:
            return {"pass": False, "power_ok_usb": gate, "why": gate["why"]}
        r = program.program(self.design, variant, self.board["name"], self.log_dir / f"program_{variant}")
        if variant == "base":
            self.res["build_stamp"] = r["build_stamp"]
        return r

    def uart_tests(self) -> dict[str, Any]:
        tests = sorted((self.design / "tests").glob("test_*_hw.py"))
        if not tests:
            raise StepFailed(f"no tests/test_*_hw.py in {self.design}")
        junit = self.log_dir / "uart_tests.xml"
        cmd = [sys.executable, "-m", "pytest", "-q", "-m", "hw", "-p", "no:cacheprovider",
               "--hw-port", self.board["uart"], "--hw-stamp", self.res["build_stamp"],
               f"--junitxml={junit}", *map(str, tests)]
        r = subprocess.run(cmd, cwd=hw.ROOT, capture_output=True, text=True, timeout=900)
        (self.log_dir / "uart_tests.txt").write_text(self.scrub(r.stdout + r.stderr))
        xml = junit.read_text() if junit.is_file() else ""
        junit.write_text(self.scrub(xml))
        m = re.search(r'tests="(\d+)"', xml)
        f = re.search(r'failures="(\d+)"', xml)
        e = re.search(r'errors="(\d+)"', xml)
        s = re.search(r'skipped="(\d+)"', xml)
        counts = {k: int(v.group(1)) if v else None for k, v in
                  (("tests", m), ("failures", f), ("errors", e), ("skipped", s))}
        names = re.findall(r'<testcase [^>]*name="([^"]+)"[^>]*time="([0-9.]+)"', xml)
        ok = r.returncode == 0 and counts["tests"] and not counts["failures"] and not counts["errors"] \
            and not counts["skipped"]
        out = {"pass": bool(ok), **counts, "cases": {n: float(t) for n, t in names},
               "files": [str(t.relative_to(hw.ROOT)) for t in tests]}
        if not ok:
            out["why"] = self.scrub("\n".join(l for l in r.stdout.splitlines() if "Error" in l or "assert" in l)[-1500:])
        return out

    def ila_captures(self) -> dict[str, Any]:
        checks = importlib.import_module(f"designs.{self.name}.hw_checks")
        build = self.design / "build" / "ila"
        top = json.loads((build / "prepare.json").read_text())["top"]
        ltx = build / f"{top}.ltx"
        names = {n: port for port, (n, _) in ila.read_probe_map(build / "probe_map.txt").items()}
        cap_dir = self.log_dir / "ila"
        cap_dir.mkdir(parents=True, exist_ok=True)
        plan = ["set fda_depth 1024", "set fda_captures {}"]
        for c in checks.CAPTURES:
            comps = " ".join(f"[list {names[k]} {int(v)}]" for k, v in c.compares.items())
            plan.append(f"lappend fda_captures [list {c.name} {c.condition} {c.position} [list {comps}]]")
        (cap_dir / "plan.tcl").write_text("\n".join(plan) + "\n")

        hw.preflight()
        log = open(cap_dir / "ila_capture.stdout.txt", "w")
        proc = subprocess.Popen(hw.vivado_cmd(hw.ROOT / "flow" / "ila_capture.tcl",
                                              [self.board["cable_serial"], str(ltx), str(cap_dir),
                                               str(cap_dir / "plan.tcl")],
                                              cap_dir / "ila_capture.log"),
                                cwd=cap_dir, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        results: dict[str, Any] = {}

        def wait_for(path: Path, timeout: float) -> bool:
            t0 = time.monotonic()
            while not path.exists():
                if proc.poll() is not None or time.monotonic() - t0 > timeout:
                    return False
                time.sleep(0.1)
            return True

        try:
            with FpgaShell.open(self.board["uart"]) as sh:
                sh.write(p.REG_SCRATCH, SENTINEL)
                for c in checks.CAPTURES:
                    c.setup(sh)
                    (cap_dir / f"{c.name}.go").write_text("go\n")
                    if not wait_for(cap_dir / f"{c.name}.armed", 300):
                        raise StepFailed(f"{c.name}: the ILA was never armed (see ila_capture.stdout.txt)")
                    time.sleep(0.2)
                    c.stimulus(sh)
                    t0 = time.monotonic()
                    while not (cap_dir / f"{c.name}.done").exists():
                        if (cap_dir / f"{c.name}.timeout").exists() or proc.poll() is not None \
                                or time.monotonic() - t0 > 180:
                            raise StepFailed(f"{c.name}: no capture (trigger never fired or Vivado stopped)")
                        time.sleep(0.1)
                    samples = ila.load_capture(cap_dir / f"{c.name}.csv", build / "probe_map.txt",
                                               cap_dir / "hw_probes.txt")
                    r = c.check(samples)
                    r["trigger"] = {"condition": c.condition, "position": c.position, "compares": c.compares}
                    results[c.name] = r
                checks.restore(sh)
            rc = proc.wait(timeout=300)
        finally:
            if proc.poll() is None:
                # the vivado wrapper runs the real binary as a child: stop the whole group
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            log.close()
        text = (cap_dir / "ila_capture.stdout.txt").read_text(errors="replace")
        (cap_dir / "ila_capture.stdout.txt").write_text(self.scrub(text))
        if rc != 0 or "FDA-CAPTURE-DONE" not in text:
            raise StepFailed(f"ila_capture.tcl exit {rc}")
        if self.keep:
            dest = RESULTS / "captures"
            dest.mkdir(parents=True, exist_ok=True)
            for c in checks.CAPTURES:
                for ext in ("csv", "vcd"):
                    shutil.copy(cap_dir / f"{c.name}.{ext}", dest / f"{self.name}_{c.name}.{ext}")
            shutil.copy(cap_dir / "hw_probes.txt", dest / f"{self.name}_hw_probes.txt")
            shutil.copy(build / "probe_map.txt", dest / f"{self.name}_probe_map.txt")
            shutil.copy(cap_dir / "plan.tcl", dest / f"{self.name}_plan.tcl")
        return {"pass": all(r["pass"] for r in results.values()), "captures": results,
                "rule": (checks.__doc__ or "").split("Comparison rules", 1)[-1].split("USB power")[0].strip()}

    def still_alive(self) -> dict[str, Any]:
        with FpgaShell.open(self.board["uart"]) as sh:
            ident = sh.identify()
            scratch = sh.read(p.REG_SCRATCH)
            status = sh.status()
        ok = (f"{ident['build_stamp']:08x}" == self.res["build_stamp"] and scratch == SENTINEL
              and not any(status.values()))
        return {"pass": ok, "build_stamp": f"{ident['build_stamp']:08x}", "scratch_kept": scratch == SENTINEL,
                "status": status}

    # --- whole run ------------------------------------------------------------------------
    def run(self) -> int:
        t0 = time.monotonic()
        # one hw_server for the whole run (started here unless one is running; stopped at the end)
        server = hw.HwServer(self.log_dir)
        try:
            server.__enter__()
            self.step("power_ok_usb", self.power)
            self.step("discover", self.discover)
            self.step("program_base", lambda: self.program("base"))
            self.step("uart_tests", self.uart_tests)
            self.step("program_ila", lambda: self.program("ila"))
            self.step("ila_captures", self.ila_captures)
            self.step("still_alive", self.still_alive)
            self.res["pass"] = True
        except StepFailed as e:
            self.res["failed_step"] = str(e)
        except hw.HwError as e:
            self.res["failed_step"] = "hw_server"
            self.res["why"] = self.scrub(str(e))
        finally:
            server.__exit__(None, None, None)
        self.res["seconds"] = round(time.monotonic() - t0, 1)
        self.res["tools"] = tool_versions(self.res.get("vivado_version"))
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "runs").mkdir(exist_ok=True)
        text = self.scrub(json.dumps(self.res, indent=2, default=str)) + "\n"
        (RESULTS / f"{self.name}_bringup.json").write_text(text)
        (RESULTS / "runs" / f"{self.name}_{self.stamp_time}.json").write_text(text)
        (self.log_dir / "bringup.json").write_text(text)
        if self.keep:
            shutil.copy(self.log_dir / "uart_tests.txt", RESULTS / "captures" / f"{self.name}_uart_tests.txt")
        print(f"bringup: {'PASS' if self.res['pass'] else 'FAIL'} in {self.res['seconds']} s; "
              f"results/f0b/{self.name}_bringup.json; logs {self.log_dir}")
        return 0 if self.res["pass"] else 1


def tool_versions(vivado: str | None) -> dict[str, str | None]:
    import pytest
    import serial
    return {"vivado": vivado, "python": platform.python_version(), "pyserial": serial.VERSION,
            "pytest": pytest.__version__}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("design", type=Path)
    ap.add_argument("--board")
    ap.add_argument("--keep-captures", action="store_true",
                    help="copy this run's CSV/VCD captures and test log to results/f0b/captures/")
    a = ap.parse_args(argv)
    design = (hw.ROOT / a.design).resolve() if not a.design.is_absolute() else a.design
    return Run(design, a.board, a.keep_captures).run()


if __name__ == "__main__":
    sys.exit(main())
