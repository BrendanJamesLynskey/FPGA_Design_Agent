#!/usr/bin/env python3
"""Program a design's bitstream into the attached board's SRAM (the runner mode for flow/program.tcl).

    python3 flow/program.py designs/<name> [base|ila] [--board nexys_a7_100t] [--json out.json]
    flow/run_vivado.sh designs/<name> program|program-ila          (the same thing)

Before Vivado touches the board it checks, and refuses with the reason if any fails:
- ``--flash`` (or any flash request) is refused outright: this flow writes volatile SRAM only;
- the board was discovered (``flow/hw_discover.py``) and is in the local board file;
- the bitstream (and, for ``ila``, the ``.ltx``) exists and was built from the current
  sources (its ``prepare.json`` build stamp equals the stamp of the files in the tree);
- **power_ok_usb**: the build's ``report_power`` total on-chip power is at most 0.5 W,
  because the board is powered from its USB cable only.
Then it runs ``flow/program.tcl`` (open the target by serial, check the device is an
xc7a100t, program SRAM, attach the ``.ltx``) under the memory-safe Vivado settings.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flow import hw  # noqa: E402

FLASH_REFUSAL = ("refused: this flow programs the FPGA's volatile SRAM only. Writing the configuration "
                 "flash (QSPI) needs the owner's explicit yes and is not supported by flow/program.py.")


def build_info(design: Path, variant: str) -> dict[str, Any]:
    """Bitstream paths of a build, its build stamp, and the stamp of the sources in the tree now."""
    bdir = design / "build" / variant
    prep_file = bdir / "prepare.json"
    if not prep_file.is_file():
        raise hw.HwError(f"no {variant} build in {bdir} (run flow/run_vivado.sh {design.relative_to(hw.ROOT)} {variant})")
    prep = json.loads(prep_file.read_text())
    top = prep["top"]
    now = json.loads(subprocess.run(
        [sys.executable, str(hw.ROOT / "flow" / "prepare.py"), str(design), "--variant", variant,
         "--out", str(hw.ROOT / "build" / "hw" / "stamp_check")],
        capture_output=True, text=True, check=True).stdout)
    return {"dir": bdir, "bit": bdir / f"{top}.bit", "ltx": bdir / f"{top}.ltx", "top": top,
            "build_stamp": prep["build_stamp"], "tree_stamp": now["build_stamp"]}


def program(design: Path, variant: str, board: str | None = None, log_dir: Path | None = None) -> dict[str, Any]:
    t0 = time.monotonic()
    b = hw.load_board(board)
    info = build_info(design, variant)
    res: dict[str, Any] = {"variant": variant, "build_stamp": info["build_stamp"],
                           "cable_serial": hw.redact(b["cable_serial"])}
    if not info["bit"].is_file():
        raise hw.HwError(f"no bitstream {info['bit']}")
    if variant == "ila" and not info["ltx"].is_file():
        raise hw.HwError(f"no probes file {info['ltx']}")
    if info["build_stamp"] != info["tree_stamp"]:
        raise hw.HwError(f"stale bitstream: built from sources with stamp {info['build_stamp']}, "
                         f"the tree now has {info['tree_stamp']}; rebuild first")
    res["power_ok_usb"] = hw.power_ok_usb(info["dir"])
    if not res["power_ok_usb"]["pass"]:
        raise hw.HwError(f"power_ok_usb: {res['power_ok_usb']['why']}; not programming")
    args = [b["cable_serial"], str(info["bit"])] + ([str(info["ltx"])] if variant == "ila" else [])
    log_dir = log_dir or hw.ROOT / "build" / "hw" / "program"
    with hw.HwServer(log_dir):
        text = hw.run_vivado_tcl(hw.ROOT / "flow" / "program.tcl", args, log_dir, f"program_{variant}",
                                 timeout_s=600)
    line = next((l for l in text.splitlines() if l.startswith("FDA-PROGRAMMED")), "")
    if not line:
        raise hw.HwError("program.tcl did not report FDA-PROGRAMMED")
    kv = dict(f.split("=", 1) for f in line.split()[1:])
    res.update({"pass": kv.get("done_pin") == "1", "device": kv.get("device"), "part": kv.get("part"),
                "done_pin": kv.get("done_pin"), "program_ms": int(kv.get("program_ms", 0)),
                "ila_cores": int(kv.get("ilas", 0)), "vivado_version": hw.vivado_version(text),
                "seconds": round(time.monotonic() - t0, 1)})
    if variant == "ila" and res["ila_cores"] < 1:
        res["pass"] = False
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("design", type=Path)
    ap.add_argument("variant", nargs="?", default="base", choices=["base", "ila"])
    ap.add_argument("--board")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--flash", action="store_true", help="always refused (SRAM only)")
    a = ap.parse_args(argv)
    if a.flash:
        print(f"program.py: {FLASH_REFUSAL}", file=sys.stderr)
        return 2
    design = (hw.ROOT / a.design).resolve() if not a.design.is_absolute() else a.design
    try:
        r = program(design, a.variant, a.board)
        rc = 0 if r["pass"] else 1
    except hw.HwError as e:
        r, rc = {"pass": False, "variant": a.variant, "why": str(e)}, 2
    print(json.dumps(r, indent=2, default=str))
    if a.json:
        a.json.write_text(json.dumps(r, indent=2, default=str) + "\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
