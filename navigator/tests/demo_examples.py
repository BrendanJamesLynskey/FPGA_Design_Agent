"""Screenshot fixture for the Examples page (brief 195): the navigator on a temporary handoff directory with a FAKE spawner (no run is started). Finished runs are planted in the
scratch run directory: the ``example_result.json`` of a real reference run, copied from ``results/195_repro_examples``, so the comparison is made with real numbers (each is itself
one of the references).

    python3 -m navigator.tests.demo_examples --port 8794 --workdir /tmp/x
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from agent.repro import registry as R
from navigator import health as H
from navigator import server as SV
from navigator.tests import demo_stage2 as D
from navigator.tests import test_103s2_navigator as T


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8794)
    ap.add_argument("--workdir", type=Path, required=True)
    a = ap.parse_args()
    w = a.workdir
    handoff, cfg, runs = w / "handoff", w / "cfg", w / "runs"
    for d in (handoff, runs):
        d.mkdir(parents=True, exist_ok=True)
    (handoff / "usage_log.txt").write_text("")
    T.write_boards(cfg)
    for i, name in enumerate(["gray_stepper", "elevator_fsm", "median3x3"]):
        f = R.RESULTS / name / "ref_1.json"
        if f.is_file():
            rd = runs / f"20261123-1{i}0000-demo"
            rd.mkdir(parents=True, exist_ok=True)
            (rd / "config.json").write_text(json.dumps({"name": f"ex_{name}"}))
            (rd / "example_result.json").write_text(f.read_text())
    runner = D.Mixed(handoff, 46)
    hl = H.Health(T.ROOT, handoff, runner, config_dir=cfg, sysfs_usb=w / "usb")
    hl._cache["models_view"] = (time.monotonic() + 1e6, T.MODELS)
    app = SV.App(T.ROOT, handoff, runs, gate=lambda e: "demo", health=hl, state_dir=w / "state", config_dir=cfg, spawner=T.FakeSpawner(), transport=T.FakeTransport(handoff, T.KR + T.SYS_OK + T.REGS))
    srv = SV.make_server(app, port=a.port)
    print(f"demo: http://127.0.0.1:{app.port}/?t={app.token}")
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
