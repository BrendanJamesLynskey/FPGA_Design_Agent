"""CLI for the Deep Agents agent (brief 05b).

    python -m agent run <spec.md> --board nexys_a7_100t [--interview on|oracle|off] [--review on|off]
                        [--model openai/gpt-6-luna] [--hidden-spec <full spec>] [--replies <json>]
    python -m agent resume <run-id> [--rewind N] [--reply '<json>'] [--replies <json>]

A paused run (an interview question or a stage review) prints what it waits for; answer with ``resume --reply``
({"answer": ...} for a question; {"decision": "approve"|"edit"|"rewind", "note": ..., "to": N} for a review).
``--replies`` is a JSON list of such replies fed in order (scripted reviewer: the planner's smokes).
``--rewind N`` restores the files and .dcp of the end of stage N (hash-checked) and the LangGraph checkpoint
saved there, then continues from stage N.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent.core.session import ROOT


def _drive(graph, rt, cfg_lg, first_input, replies: list) -> dict:
    from langgraph.types import Command

    from agent.graph.run import summary
    inp = first_input
    while True:
        graph.invoke(inp, cfg_lg)
        snap = graph.get_state(cfg_lg)
        pending = [i.value for t in snap.tasks for i in (t.interrupts or [])]
        if not pending:
            break
        if not replies:
            print(json.dumps({"paused": pending[0], "run_id": rt.run_id}, indent=1))
            return {"paused": pending[0]}
        reply = replies.pop(0)
        print(json.dumps({"interrupt": pending[0].get("kind"), "stage": pending[0].get("stage"), "reply": reply}))
        inp = Command(resume=reply)
    s = summary(rt, snap.values)
    (rt.run_dir / "summary.json").write_text(json.dumps(s, indent=1))
    print(json.dumps(s, indent=1))
    return s


def _client(model: str, replay: str | None, record: str | None):
    from agent.graph.llm import OpenRouterClient, Recorder, Replay
    if replay:
        return Replay(Path(replay))
    c = OpenRouterClient(model)
    return Recorder(c, Path(record)) if record else c


def _oracle(client):
    def llm(system, user):
        r = client([{"role": "system", "content": system}, {"role": "user", "content": user}])
        try:
            return json.loads(r.text.strip().removeprefix("```json").removesuffix("```"))
        except ValueError:
            return {"answer": "not specified", "quote": None}
    return llm


def main(argv: list[str] | None = None) -> int:
    from agent.graph.run import Config, build_graph, checkpointer_for, new_runtime
    ap = argparse.ArgumentParser(prog="python -m agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("spec", type=Path)
    r.add_argument("--board", default="nexys_a7_100t")
    r.add_argument("--name")
    r.add_argument("--interview", choices=["on", "oracle", "off"], default="off")
    r.add_argument("--review", choices=["on", "off"], default="off")
    r.add_argument("--model", default="openai/gpt-6-luna")
    r.add_argument("--hidden-spec", type=Path)
    r.add_argument("--stop-after", type=int)
    r.add_argument("--harness", choices=["deepagents", "claude_code"], default="deepagents",
                   help="claude_code: each sub-agent turn is a headless `claude -p` on the Max plan (05c)")
    r.add_argument("--cc-model", default="claude-haiku-5-5", help="Claude Code model id (--harness claude_code)")
    r.add_argument("--cc-effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    r.add_argument("--max-usd", type=float, help="run cost cap (provider-reported); default RUN_LIMITS")
    r.add_argument("--verif-level", choices=["V1", "V2", "V3"], default="V3",
                   help="verification stage stage 2 must reach (default V3, the methodology; V1/V2 only while the agent "
                        "has no tool that produces V2/V3 evidence: multi-seed runs, formal, coverage, mutation)")
    for p in (r, sub.add_parser("resume")):
        p.add_argument("--replies", type=Path)
        p.add_argument("--reply")
        p.add_argument("--replay", help="LLM replay fixture (no network)")
        p.add_argument("--record", help="record LLM calls to this fixture")
    rs = sub._name_parser_map["resume"]
    rs.add_argument("run_id")
    rs.add_argument("--rewind", type=int)
    rs.add_argument("--max-usd", type=float, help="cost cap for this resumed process (the meter starts at 0)")
    a = ap.parse_args(argv)
    replies = json.loads(a.replies.read_text()) if a.replies else []
    if a.reply:
        replies.insert(0, json.loads(a.reply))
    if a.cmd == "run":
        if a.interview == "oracle" and not a.hidden_spec:
            ap.error("--interview oracle needs --hidden-spec")
        name = a.name or a.spec.resolve().parent.name
        cfg = Config(spec_md=a.spec, name=name, board=a.board, interview=a.interview, review=a.review,
                     model=a.model, hidden_spec=a.hidden_spec, stop_after=a.stop_after,
                     harness=a.harness, cc_model=a.cc_model, cc_effort=a.cc_effort,
                     verif_level=a.verif_level)
        if a.max_usd is not None:
            cfg.run_limits["usd"] = a.max_usd
        client = _client(a.model, a.replay, a.record)
        rt = new_runtime(cfg, client, oracle_llm=_oracle(client))
        graph = build_graph(checkpointer_for(rt.run_dir))
        _drive(graph, rt, {"configurable": {"thread_id": rt.run_id}},
               {"run_id": rt.run_id, "stage": 0, "visits": {}, "history": []}, replies)
        return 0
    # resume
    run_dir = ROOT / "runs" / a.run_id
    c = json.loads((run_dir / "config.json").read_text())
    cfg = Config(spec_md=Path(c["spec_md"]), name=c["name"], board=c["board"], interview=c["interview"],
                 review=c["review"], model=c["model"],
                 hidden_spec=Path(c["hidden_spec"]) if c.get("hidden_spec") not in (None, "None") else None,
                 stop_after=None if c.get("stop_after") in (None, "None") else int(c["stop_after"]),
                 harness=c.get("harness", "deepagents"), cc_model=c.get("cc_model", "claude-haiku-5-5"),
                 cc_effort=c.get("cc_effort", "medium"), verif_level=c.get("verif_level", "V3"))
    if a.max_usd is not None:
        cfg.run_limits["usd"] = a.max_usd
    client = _client(cfg.model, a.replay, a.record)
    rt = new_runtime(cfg, client, run_id=a.run_id, oracle_llm=_oracle(client))
    graph = build_graph(checkpointer_for(run_dir))
    lg = {"configurable": {"thread_id": a.run_id}}
    from langgraph.types import Command
    first = Command(resume=replies.pop(0)) if replies else None
    if a.rewind is not None:
        res = rt.snaps.rewind(a.rewind)
        print(json.dumps({"rewind": a.rewind, "verified": res["verified"], "commit": res["commit"]}))
        if not res["verified"]:
            return 2
        # the LangGraph checkpoint taken just after stage N's review: continue from there, at stage N
        target = None
        for st in graph.get_state_history(lg):
            h = st.values.get("history") or []
            if h and h[-1]["n"] == a.rewind and st.next == ("advance",):
                target = st
                break
        if target is None:
            print("no checkpoint for that stage", file=sys.stderr)
            return 2
        lg = graph.update_state(target.config, {"stage": a.rewind, "fails": [], "stop": None}, as_node="advance")
        first = None
    _drive(graph, rt, lg, first, replies)
    return 0


if __name__ == "__main__":
    sys.exit(main())
