"""The JTAG-side reading of the XADC (Vivado hardware manager), for cross-checking the fabric DRP readout."""
from __future__ import annotations

import re
from pathlib import Path

from flow import hw

TCL = Path(__file__).with_name("sysmon_read.tcl")


def read(out_dir: Path, board: str | None = None) -> dict[str, float]:
    """Run sysmon_read.tcl on the owner's board (selected by cable serial) and return degC and volts."""
    b = hw.load_board(board)
    with hw.HwServer(out_dir):
        text = hw.run_vivado_tcl(TCL, [b["cable_serial"]], out_dir, "sysmon_read", timeout_s=300)
    line = next((l for l in text.splitlines() if l.startswith("FDA-SYSMON")), "")
    kv = dict(re.findall(r"(\w+)=([-\d.eE+]+)", line))
    if not kv:
        raise hw.HwError("sysmon_read.tcl printed no FDA-SYSMON line")
    return {"tj_c": float(kv["TEMPERATURE"]), "vccint_v": float(kv["VCCINT"]), "vccaux_v": float(kv["VCCAUX"]),
            "vccbram_v": float(kv["VCCBRAM"])}
