#!/usr/bin/env python3
"""Program a design's bitstream into the attached board's SRAM (the runner mode for flow/program.tcl).

    python3 flow/program.py designs/<name> [base|ila] [--board nexys_a7_100t] [--json out.json]
    flow/run_vivado.sh designs/<name> program|program-ila          (the same thing)

Before Vivado touches the board it checks, and refuses with the reason if any fails:
- ``--flash`` (or any flash request) is refused outright: this flow writes volatile SRAM only;
- the board was discovered (``flow/hw_discover.py``) and is in the local board file;
- the bitstream (and, for ``ila``, the ``.ltx``) exists and was built from the current
  sources (its ``prepare.json`` build stamp equals the stamp of the files in the tree);
- **power_ok**: the build's ``report_power`` total on-chip power and junction temperature are
  within the limits for the board's power source (``power_source`` in the local board file:
  usb 0.5 W, wall 2.0 W interim; Tj <= 85 C in still air; usb if unrecorded), see flow/hw.py.
Then it runs ``flow/program.tcl`` (open the target by serial, check the device is an
xc7a100t, program SRAM, attach the ``.ltx``) under the memory-safe Vivado settings.

**Build ID (brief 54).** After programming, program.tcl reads the device's USR_ACCESS register over JTAG; it must equal
the ``build_id`` of the build's ``manifest.json`` (flow/manifest.py), or the run stops (``HwError``) before any board
test. Over the UART, :func:`check_shell_build_id` compares the shell's BUILD_STAMP register (0x02) with the stamp the
manifest recorded (``settings.build_stamp``, which the build ID covers); flow/board_check.py and flow/bringup.py call it
right after programming. The shell has no register for the build ID itself: its register map is frozen with the
benchmark (benchmark/GRADER_DEPS.json shell fingerprint), so adding one needs a dated benchmark amendment. A build made
before brief 54 has no manifest: it is programmed with a note, and nothing is compared. program.tcl also logs the
operating conditions (XADC temperature, VCCINT, VCCAUX, VCCBRAM, the latched min/max and the alarm flags), with a verdict
against the Artix-7 -1 recommended operating conditions (AMD DS181 table 2) and the board's 85 C junction limit.
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

# Artix-7 -1 recommended operating conditions (AMD DS181 v1.27 table 2; the knowledge bank's artix7-speed-grade-limits) and
# the Nexys A7's own junction limit (house rules: 85 C)
ROC = {"VCCINT": (0.95, 1.05), "VCCAUX": (1.71, 1.89), "VCCBRAM": (0.95, 1.05), "TEMPERATURE": (None, 85.0)}

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
    mf = bdir / "manifest.json"
    man = json.loads(mf.read_text()) if mf.is_file() else {}
    build_id = man.get("build_id")
    manifest_stamp = (man.get("settings") or {}).get("build_stamp")
    return {"dir": bdir, "bit": bdir / f"{top}.bit", "ltx": bdir / f"{top}.ltx", "top": top,
            "build_stamp": prep["build_stamp"], "tree_stamp": now["build_stamp"], "build_id": build_id,
            "manifest_stamp": manifest_stamp}


def parse_conditions(text: str) -> dict[str, Any]:
    """The FDA-COND lines of program.tcl: now, latched max and min, alarm flags, and the verdict against ROC."""
    cond: dict[str, Any] = {}
    for line in text.splitlines():
        if line.startswith("FDA-COND FLAGS"):
            cond["flags"] = line.split()[-1]
            continue
        parts = line.split()
        if len(parts) > 2 and parts[0] == "FDA-COND":
            cond[parts[1].lower()] = {k: float(v) for k, v in (f.split("=", 1) for f in parts[2:])}
    if "now" not in cond:
        return {"read": False}
    outside = []
    for which in ("now", "max", "min"):
        for k, (lo, hi) in ROC.items():
            v = (cond.get(which) or {}).get(k)
            if v is None:
                continue
            if (lo is not None and v < lo) or (hi is not None and v > hi):
                outside.append(f"{which} {k} {v}")
    return {"read": True, **cond, "inside_roc": not outside, "outside": outside,
            "limits": {k: list(v) for k, v in ROC.items()},
            "note": "XADC through JTAG at programming time; min/max are latched since this configuration; the XADC "
                    "samples at about 1 MSPS across channels, so nanosecond supply droop is not visible to it"}


def check_build_id(expected: str | None, got: str | int | None, where: str) -> dict[str, Any]:
    """Compare a read-back build ID with the manifest's. ``expected`` None: a build without a manifest (before brief 54)."""
    if expected is None:
        return {"checked": False, "where": where, "note": "no manifest.json: built before brief 54, nothing to compare"}
    if isinstance(got, int):
        got = f"{got:08x}"
    g = (got or "").lower().removeprefix("0x")
    ok = g == expected.lower()
    return {"checked": True, "where": where, "expected": expected, "read": g or None, "match": ok}


def check_shell_build_id(ident: dict[str, Any], manifest_stamp: str | None) -> dict[str, Any]:
    """The shell's BUILD_STAMP (register 0x02) against the stamp in the manifest (``settings.build_stamp``, covered by
    the build ID). Raises HwError on a mismatch: no board test runs."""
    if ident.get("build_stamp") is None:
        return {"checked": False, "where": "uart", "note": "no shell"}
    r = check_build_id(manifest_stamp, ident["build_stamp"], "uart")
    r["register"] = "BUILD_STAMP (0x02)"
    if r["checked"] and not r["match"]:
        raise hw.HwError(f"build stamp mismatch over the UART shell: the board reports {r['read']}, the manifest says "
                         f"{manifest_stamp}; stopping before any board test")
    return r


def program(design: Path, variant: str, board: str | None = None, log_dir: Path | None = None) -> dict[str, Any]:
    t0 = time.monotonic()
    b = hw.load_board(board)
    info = build_info(design, variant)
    res: dict[str, Any] = {"variant": variant, "build_stamp": info["build_stamp"], "build_id": info["build_id"],
                           "manifest_stamp": info["manifest_stamp"],
                           "cable_serial": hw.redact(b["cable_serial"])}
    if not info["bit"].is_file():
        raise hw.HwError(f"no bitstream {info['bit']}")
    if variant == "ila" and not info["ltx"].is_file():
        raise hw.HwError(f"no probes file {info['ltx']}")
    if info["build_stamp"] != info["tree_stamp"]:
        raise hw.HwError(f"stale bitstream: built from sources with stamp {info['build_stamp']}, "
                         f"the tree now has {info['tree_stamp']}; rebuild first")
    res["power_ok"] = hw.power_ok(info["dir"], b["name"])
    if not res["power_ok"]["pass"]:
        raise hw.HwError(f"power_ok: {res['power_ok']['why']}; not programming")
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
    res["conditions"] = parse_conditions(text)
    res["build_id_jtag"] = check_build_id(info["build_id"], kv.get("usr_access"), "jtag")
    if variant == "ila" and res["ila_cores"] < 1:
        res["pass"] = False
    if res["build_id_jtag"]["checked"] and not res["build_id_jtag"]["match"]:
        raise hw.HwError(f"build ID mismatch over JTAG: USR_ACCESS reads {res['build_id_jtag']['read']}, the manifest "
                         f"says {info['build_id']}; stopping before any board test")
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
