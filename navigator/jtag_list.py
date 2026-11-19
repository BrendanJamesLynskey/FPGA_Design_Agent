"""The hardware-server listing behind the health panel's JTAG button: ``python -m navigator.jtag_list``.

Read-only: it starts the local hw_server, runs ``flow/hw_list.tcl`` (which opens each target to read its chain and programs nothing) and prints one
line per target and device, serials cut to their last 4 characters. It never writes ``boards.yaml``, never programs, and does not take the board lock
(the navigator refuses to start it while the lock is held).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    from agent.access import require_or_exit
    require_or_exit("python -m navigator.jtag_list")
    from flow import hw, hw_discover
    with tempfile.TemporaryDirectory(prefix="fda_jtag_list_") as d:
        with hw.HwServer(Path(d)):
            text = hw.run_vivado_tcl(ROOT / "flow" / "hw_list.tcl", [], Path(d), "hw_list")
    for uid, t in hw_discover.parse_list(text).items():
        print(f"target {hw.redact(hw_discover.cable_serial(uid))} {t.get('error') or 'ok'}")
        for dv in t["devices"]:
            print(f"device {dv['device']} {dv['part']} idcode {dv['idcode']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
