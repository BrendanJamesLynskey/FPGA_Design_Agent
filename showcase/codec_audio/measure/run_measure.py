#!/usr/bin/env python3
"""Run the codec audio path measurements and write a record (brief 78).

    python3 showcase/codec_audio/measure/run_measure.py --dry-run [--out records/dry_run.json]
    python3 showcase/codec_audio/measure/run_measure.py --play-device plughw:CODEC --record-device plughw:CODEC \\
        --confirm-owner-warned --baseline records/pc_loopback.json [--controller-cmd "python3 host_ctl.py"]

A dry run needs no audio device and no board: it runs every analyser against the simulated rig (SimRig) and marks the record
`"dry_run": true`; its numbers describe the model's settings, not the hardware. A real run plays a tone through the owner's
interface, so it refuses to start without --confirm-owner-warned (the line-out is started at a low level, -30 dBFS by default,
with a fade in, and the owner is warned before anything plays through headphones). Operating conditions (the PC interface,
levels, the board's die temperature and rail voltages when `--conditions-cmd` prints them as JSON) go into the record.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from showcase.codec_audio.measure import audio_measure as M  # noqa: E402


def _controller(cmd: str | None):
    if not cmd:
        return None

    def run(op: str, ch: int, value: int) -> None:
        subprocess.run([*cmd.split(), op, str(ch), str(value)], check=True, timeout=10)
    return run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="simulated rig; no audio device, no board")
    ap.add_argument("--play-device")
    ap.add_argument("--record-device")
    ap.add_argument("--confirm-owner-warned", action="store_true", help="the owner has been told a test tone is about to play")
    ap.add_argument("--level-db", type=float, default=-30.0, help="first level played, dBFS peak (default -30: low)")
    ap.add_argument("--baseline", type=Path, help="a record taken with the PC interface alone (line out to line in)")
    ap.add_argument("--datasheet", type=Path, help="JSON with the codec's figures: thd_n_db, noise_floor_dbfs, crosstalk_db")
    ap.add_argument("--controller-cmd", help="command that writes the board: <cmd> gain|mute CH VALUE")
    ap.add_argument("--conditions-cmd", help="command that prints the board's temperature and rails as JSON")
    ap.add_argument("--quick", action="store_true", help="shorter tones (the dry-run tests use this)")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)

    plan = M.Plan(level_db=a.level_db)
    if a.quick:
        plan.tone_s, plan.silence_s, plan.freqs = 0.5, 0.6, (100, 1000, 10000)
    if a.dry_run:
        rig = M.SimRig()
    else:
        if not (a.play_device and a.record_device):
            ap.error("a real run needs --play-device and --record-device (or use --dry-run)")
        if not a.confirm_owner_warned:
            ap.error("refusing to play a tone: pass --confirm-owner-warned once the owner has been warned (headphones)")
        rig = M.AlsaRig(a.play_device, a.record_device, _controller(a.controller_cmd))
    load = lambda p: json.loads(p.read_text()) if p else None          # noqa: E731
    base = load(a.baseline)
    base = None if base is None else {"thd_n_db": base["thd_n"]["thd_n_db"], "noise_floor_dbfs": max(base["noise_floor_dbfs"].values()),
                                      "crosstalk_db": max(base["crosstalk_db"].values())}
    cond_start = _conditions(a.conditions_cmd)
    res = M.run_all(rig, plan, base, load(a.datasheet))
    res.update({"dry_run": bool(a.dry_run), "rig": rig.kind, "rig_settings": rig.settings(), "date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "host": platform.node() if not a.dry_run else "dry run", "format": "24-bit, 48 kHz, stereo",
                "conditions": {"start": cond_start, "end": _conditions(a.conditions_cmd)}})
    text = json.dumps(res, indent=1, sort_keys=True) + "\n"
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text)
    print(text)
    return 0


def _conditions(cmd: str | None):
    if not cmd:
        return None
    return json.loads(subprocess.run(cmd.split(), capture_output=True, text=True, timeout=20, check=True).stdout)


if __name__ == "__main__":
    raise SystemExit(main())
