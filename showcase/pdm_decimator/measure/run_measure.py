#!/usr/bin/env python3
"""Runner for the PDM audio-path measurements.

    python3 showcase/pdm_decimator/measure/run_measure.py --dry-run --out showcase/pdm_decimator/records/dry_run_2026-11-14.json
    python3 showcase/pdm_decimator/measure/run_measure.py --port /dev/ttyUSB1 --confirm-owner-warned --out RECORD.json   # phase 3, board.lock first

A real run needs the board powered, the audio-path bitstream loaded (SRAM, over JTAG, by the board flow), ``_handoff/board.lock`` taken, and
the owner warned that test tones will play from the PC loudspeaker (start low). Operating conditions (die temperature and VCCINT, VCCAUX,
VCCBRAM from the XADC) go into the record when ``--conditions-cmd`` prints them as JSON.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from showcase.pdm_decimator.measure import pdm_measure as pm  # noqa: E402

DESIGN_ID = 0x504D4432          # "PMD2"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="no board, no audio device: the simulated board and room")
    ap.add_argument("--port", help="the UART device of the Nexys A7")
    ap.add_argument("--confirm-owner-warned", action="store_true", help="required for a real run: test tones will play")
    ap.add_argument("--records", type=int, default=120, help="captures per point (a real run)")
    ap.add_argument("--conditions-cmd", help="a command that prints the XADC conditions as JSON")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    if a.dry_run:
        res = pm.dry_run()
    else:
        if not a.port or not a.confirm_owner_warned:
            raise SystemExit("a real run needs --port and --confirm-owner-warned (and board.lock, taken by the caller)")
        board = pm.ShellBoard(a.port)
        ident = board.shell.identify().get("design_id")
        if ident != DESIGN_ID:
            raise SystemExit(f"design ID {ident!r}, expected 0x{DESIGN_ID:08X}: the audio-path bitstream is not loaded")
        cond = (lambda: json.loads(subprocess.run(a.conditions_cmd, shell=True, check=True, capture_output=True, text=True).stdout)) \
            if a.conditions_cmd else None
        res = pm.measure(board, a.records, speaker=pm.loudspeaker, conditions=cond)
        res["dry_run"] = False
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=1) + "\n")
    print(f"wrote {a.out}: noise floor {res['noise_floor_dbfs']} dBFS, dry_run={res['dry_run']}")
    return 0 if res.get("dry_run_pass", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
