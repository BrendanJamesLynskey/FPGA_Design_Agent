#!/usr/bin/env python3
"""Brief 108: replayed episodes give byte-identical tool calls before and after the model-configuration refactor.

Run it in a checkout (``python tools/model_config_replay_check.py OUT.json``); run it in a checkout of the commit before the
refactor and in the refactored one, then compare the two files (``--compare A B``). It runs:

1. the scripted T1 episode of ``agent/tests/test_episode.py`` (interview, review, a rewind, hardware approval) through the whole
   stage graph with a deterministic scripted model, and hashes (a) every model reply's tool calls in order and (b) every tool call
   the core dispatched (``build/audit.jsonl``: tool, arguments, role, stage, whether refused), with times removed;
2. the six recorded plain-English debug requests of ``debug_core/tests/fixtures/llm`` replayed through ``debug_core.request.parse``,
   hashing each parsed intent. After the refactor the replayed client is the one the resolver builds from the table.

The hashes depend only on the scripted and recorded replies and on the agent's behaviour, so any change in what the agent asks its
tools to do would change them. No network, no model call, no spend.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def episode() -> dict:
    from agent import access
    from agent.graph import run as gr
    from agent.tests import test_episode as E
    access._TEST_BYPASS, access.CURRENT = True, None            # as the test suite's conftest does: the episode runs without the key
    from flow import hw
    replies: list = []
    orig = E.scripted_client

    def recording(seen, where):
        inner = orig(seen, where)

        def client(messages, tools=None):
            r = inner(messages, tools)
            replies.append({"tool_calls": r.tool_calls, "text": r.text})
            return r
        return client
    E.scripted_client = recording
    runs = ROOT / "runs" / f"_replaycheck_{uuid.uuid4().hex[:8]}"
    real = (gr.RUNS, hw.load_board, hw.power_ok)
    gr.RUNS = runs
    hw.load_board = lambda b: {"cable_serial": "TEST0000"}
    hw.power_ok = lambda d, b: {"pass": True, "total_w": 0.15, "junction_c": 42.7, "source": "wall"}
    tmp = Path(tempfile.mkdtemp(prefix="replaycheck_"))
    try:
        rt = E._episode(tmp, runs)
        audit = [json.loads(l) for l in (rt.design / "build" / "audit.jsonl").read_text().splitlines()]
        keep = [{k: a.get(k) for k in ("tool", "args", "arguments", "role", "stage", "refused", "rule", "ok")} for a in audit]
        # a path inside the run directory carries the run's temporary name: neutralise it
        text = json.dumps(keep, sort_keys=True).replace(str(runs), "<runs>").replace(runs.name, "<run>").replace(str(tmp), "<tmp>")
        rtext = json.dumps(replies, sort_keys=True).replace(str(runs), "<runs>").replace(runs.name, "<run>").replace(str(tmp), "<tmp>")
        return {"model_replies": len(replies), "model_reply_tool_calls_sha256": hashlib.sha256(rtext.encode()).hexdigest(),
                "core_tool_calls": len(keep), "core_tool_calls_sha256": hashlib.sha256(text.encode()).hexdigest()}
    finally:
        gr.RUNS, hw.load_board, hw.power_ok = real
        E.scripted_client = orig
        shutil.rmtree(runs, ignore_errors=True)
        shutil.rmtree(tmp, ignore_errors=True)


def nl_requests() -> dict:
    from agent.graph.llm import Replay
    from debug_core.request import parse
    fix = ROOT / "debug_core" / "tests" / "fixtures"
    reqs = json.loads((fix / "requests.json").read_text())
    out = {}
    for name in sorted(reqs):
        f = fix / "llm" / f"{name}.json"
        try:
            from agent.models import resolver_for
            client = resolver_for("interpret", replay=f).chat("interpret")     # after the refactor: the resolver's replayed client
        except ImportError:
            client = Replay(f)                                                    # before it: the replay directly
        intent, meta = parse(reqs[name]["request"], Path(reqs[name]["design"]), client=client)
        out[name] = {"intent_sha256": sha(intent), "attempts": meta["attempts"], "replies_sha256": sha(meta["replies"])}
    return out


def main(argv: list[str]) -> int:
    if argv[:1] == ["--compare"]:
        a, b = (json.loads(Path(p).read_text()) for p in argv[1:3])
        same = a == b
        print(json.dumps({"identical": same, "episode": a["episode"] == b["episode"], "nl_requests": a["nl_requests"] == b["nl_requests"]}))
        return 0 if same else 1
    res = {"episode": episode(), "nl_requests": nl_requests()}
    Path(argv[0]).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(json.dumps(res, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
