#!/usr/bin/env python3
"""Find the attached board: its JTAG cable serial and its UART device.

    python3 flow/hw_discover.py [--board nexys_a7_100t] [--json out.json]

1. Starts hw_server (or uses the one on localhost:3121), runs flow/hw_list.tcl in
   Vivado with the memory-safe settings, and reads the targets and their devices.
2. Refuses to guess: exactly one Digilent target must be present, with exactly one
   device on its chain, of the board's part (boards/<board>/board.yaml).
3. Finds the UART: the FTDI FT2232 (0403:6010) whose USB serial matches the JTAG
   target's, on USB interface 1 (interface 0 is the JTAG channel).
4. Writes both to ~/.config/fpga_design_agent/boards.yaml (outside the repo), and
   prints/returns a summary in which the serial is cut to its last 4 characters.

Exit 0 when one board was found and recorded, 2 when discovery refused, 1 on error.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flow import hw  # noqa: E402

FTDI_VID, FT2232_PID = 0x0403, 0x6010


def parse_list(text: str) -> dict[str, dict[str, Any]]:
    """FDA-TARGET / FDA-DEVICE lines from hw_list.tcl into {uid: {name, devices: [...]}}."""
    targets: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        f = line.split()
        if not f:
            continue
        if f[0] == "FDA-TARGET" and len(f) >= 3:
            targets[f[1]] = {"name": f[2], "devices": [], "error": None}
        elif f[0] == "FDA-TARGET-ERROR" and len(f) >= 2:
            targets.setdefault(f[1], {"name": "", "devices": []})["error"] = " ".join(f[2:])
        elif f[0] == "FDA-DEVICE" and len(f) >= 5:
            targets.setdefault(f[1], {"name": "", "devices": [], "error": None})["devices"].append(
                {"device": f[2], "part": f[3], "idcode": f[4]})
    if "FDA-LIST-DONE" not in text:
        raise hw.HwError("hw_list.tcl did not finish (no FDA-LIST-DONE)")
    return targets


def cable_serial(uid: str) -> str:
    """'Digilent/210292XXXXXXA' -> '210292XXXXXXA' (the serial hw_server shows)."""
    return uid.split("/", 1)[1] if "/" in uid else uid


def usb_serial(cable: str) -> str:
    """Digilent's JTAG target serial is the FTDI USB serial plus the channel letter (A)."""
    return cable[:-1] if cable and cable[-1].isalpha() and cable[:-1].isalnum() else cable


def find_uart(usb_ser: str, ports: list[Any] | None = None) -> list[str]:
    """Device paths of interface 1 of the FT2232 with this USB serial (stable by-id path if there is one)."""
    if ports is None:
        from serial.tools import list_ports
        ports = list(list_ports.comports())
    hits = []
    for pt in ports:
        if pt.vid != FTDI_VID or pt.pid != FT2232_PID or pt.serial_number != usb_ser:
            continue
        if not (pt.location or "").endswith(".1"):
            continue
        by_id = sorted(Path("/dev/serial/by-id").glob(f"*{usb_ser}-if01-port0")) \
            if Path("/dev/serial/by-id").is_dir() else []
        hits.append(str(by_id[0]) if by_id else pt.device)
    return hits


def decide(targets: dict[str, dict[str, Any]], part: str) -> tuple[str, dict[str, Any]]:
    """The one Digilent target, or HwError saying why discovery refuses to guess."""
    digilent = {u: t for u, t in targets.items() if u.startswith("Digilent/")}
    if len(digilent) != 1:
        found = ", ".join(hw.redact(cable_serial(u)) or "?" for u in targets) or "none"
        raise hw.HwError(f"expected exactly one Digilent JTAG target, found {len(digilent)} "
                         f"(all targets: {found}); refusing to guess")
    uid, t = next(iter(digilent.items()))
    if t.get("error"):
        raise hw.HwError(f"target {hw.redact(cable_serial(uid))} could not be opened: {t['error']}")
    parts = [d["part"] for d in t["devices"]]
    if parts != [part]:
        raise hw.HwError(f"target {hw.redact(cable_serial(uid))} has devices {parts}, expected exactly [{part}]")
    return uid, t


def discover(board: str, log_dir: Path) -> dict[str, Any]:
    cfg = yaml.safe_load((hw.ROOT / "boards" / board / "board.yaml").read_text())
    part = cfg["part"].split("csg")[0].split("-")[0] if "part" in cfg else "xc7a100t"
    t0 = time.monotonic()
    with hw.HwServer(log_dir):
        text = hw.run_vivado_tcl(hw.ROOT / "flow" / "hw_list.tcl", [], log_dir, "hw_list", timeout_s=300)
    targets = parse_list(text)
    uid, t = decide(targets, part)
    cable = cable_serial(uid)
    uarts = find_uart(usb_serial(cable))
    if len(uarts) != 1:
        raise hw.HwError(f"expected one UART (FT2232 interface 1) for cable {hw.redact(cable)}, found {len(uarts)}")
    hw.save_board(board, {"cable_serial": cable, "jtag_uid": uid, "uart": uarts[0], "part": part,
                          "device": t["devices"][0]["device"], "idcode": t["devices"][0]["idcode"],
                          "discovered": time.strftime("%Y-%m-%dT%H:%M:%S")})
    return {"pass": True, "board": board, "cable_serial": hw.redact(cable), "part": part,
            "idcode": t["devices"][0]["idcode"], "uart": "FT2232 interface 1 (found)",
            "targets_seen": len(targets), "vivado_version": hw.vivado_version(text),
            "seconds": round(time.monotonic() - t0, 1)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--board", default="nexys_a7_100t")
    ap.add_argument("--log-dir", type=Path, default=hw.ROOT / "build" / "hw" / "discover")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    try:
        r = discover(a.board, a.log_dir)
        rc = 0
    except hw.HwError as e:
        r, rc = {"pass": False, "board": a.board, "why": str(e)}, 2
    print(json.dumps(r, indent=2))
    if a.json:
        a.json.write_text(json.dumps(r, indent=2) + "\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
