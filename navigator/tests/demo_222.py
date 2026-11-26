"""Screenshot fixture for brief 222 (permission modes), after stage 2 (brief 103S2): a temporary configuration directory (permission settings are saved there, never in the owner's own) and one synthetic run paused on a permission question.

The stage 2 fixture: the navigator on a temporary handoff directory with a FAKE spawner and a FAKE board transport, so the Start, Live and
Board pages can be shot without starting the agent, Vivado or touching a board. The Live page shows one clearly named synthetic run (planted in the scratch run directory) so an active run has something to show.

    python3 -m navigator.tests.demo_222 --port 8795 --workdir /tmp/x

Prints the address with the session token and the workdir's handoff path (shoot_stage2.js writes board.lock there to show a refusal).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from navigator import health as H
from navigator import server as SV
from navigator.tests import test_103s2_navigator as T


class Mixed(T.FakeRunner):
    """The usage check and slot script are fakes (they would otherwise run the owner's real scripts); everything else is the real fixed-argv runner."""

    def run(self, argv, timeout=20, cwd=None, env=None):
        if argv[0] == "bash" or "models show" in " ".join(argv):
            return super().run(argv, timeout, cwd, env)
        return H.Runner.run(self, argv, timeout, cwd, env)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8795)
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument("--runs", type=Path)
    a = ap.parse_args()
    w = a.workdir
    handoff, cfg, runs = w / "handoff", w / "cfg", w / "runs"
    for d in (handoff, runs):
        d.mkdir(parents=True, exist_ok=True)
    (handoff / "usage_log.txt").write_text("")
    T.write_boards(cfg)
    T.make_run(runs, "20261120-170000-demo")
    pend = {"paused": {"kind": "permission", "stage": 3, "stage_name": "constraints", "mode": "ask", "needs": ["run_vivado"],
                       "actions": [{"action": "run_vivado", "label": "Run Vivado synthesis and implementation",
                                    "plain": "Run Vivado builds (synthesis, place and route, bitstream) in a heavy slot. Takes minutes to hours and a large share of this machine's memory."}],
                       "resume": "python -m agent resume 20261120-170000-demo --reply '{\"decision\": \"allow\"}'"}, "run_id": "20261120-170000-demo"}
    (runs / "20261120-170000-demo" / "pending.json").write_text(json.dumps(pend))
    run_dir = a.runs if a.runs else runs
    runner = Mixed(handoff, 46)
    hl = H.Health(T.ROOT, handoff, runner, config_dir=cfg, sysfs_usb=w / "usb")
    hl._cache["models_view"] = (time.monotonic() + 1e6, {"table": [{"name": "rtl", "kind": "claude_code", "model": "claude-sonnet-5-5", "endpoint": "claude_code", "options": {}, "key_state": "no key needed", "from": "builtin"},
                                                                  {"name": "oracle", "kind": "openrouter", "model": "openai/gpt-6-luna", "endpoint": "openrouter", "options": {}, "key_state": "key present", "from": "builtin"}], "hash": "demo", "layers": []})
    app = SV.App(T.ROOT, handoff, run_dir, gate=lambda e: "demo", health=hl, state_dir=w / "state", config_dir=cfg, spawner=T.FakeSpawner(),
                 transport=T.FakeTransport(handoff, T.KR + T.SYS_OK + T.REGS))
    srv = SV.make_server(app, port=a.port)
    print(f"demo: http://127.0.0.1:{app.port}/?t={app.token}")
    print(f"handoff: {handoff}")
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
