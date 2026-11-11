"""CLI for the Deep Agents agent (brief 05b).

    python -m agent run <spec.md> --board nexys_a7_100t [--interview on|oracle|off] [--review on|off]
                        [--model openai/gpt-6-luna] [--hidden-spec <full spec>] [--replies <json>]
    python -m agent resume <run-id> [--rewind N] [--reply '<json>'] [--replies <json>]
    python -m agent project check|status|hash|gen-tests <dir> ...     (the project layer, project/cli.py)

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


def task_no_shell(hidden_spec: Path | None) -> bool:
    """07a2-prep: a benchmark task's hidden/bench.yaml says ``no_shell: true`` (the subject is the USB-UART itself)."""
    import yaml
    b = hidden_spec.resolve().parent / "bench.yaml" if hidden_spec else None
    return bool(b and b.is_file() and (yaml.safe_load(b.read_text()) or {}).get("no_shell"))


def task_data_dir(spec_md: Path) -> Path | None:
    """07a2-prep: the task's ``data/`` directory, next to its spec.md (the benchmark task layout), when it exists."""
    d = spec_md.resolve().parent / "data"
    return d if d.is_dir() else None


def _no_openrouter(model):
    raise RuntimeError("--oracle claude_code: no OpenRouter call is allowed in this run")


class _NoOpenRouter:
    """The run client when nothing may use OpenRouter (Claude Code arm and a Claude Code oracle): any call is an error."""
    def __call__(self, *a, **k):
        raise RuntimeError("--oracle claude_code: no OpenRouter call is allowed in this run")


def _clients(cfg, a):
    if cfg.oracle == "claude_code":
        if cfg.harness != "claude_code":
            raise SystemExit("--oracle claude_code needs --harness claude_code (no OpenRouter at all)")
        return _NoOpenRouter(), None
    client = _client(cfg.model, a.replay, a.record)
    return client, _oracle(client)


def config_from_json(c: dict):
    """The Config of a run from its config.json (``resume``); runs from before 05f have no profile: ``single``."""
    from agent.graph.run import Config
    def flag(k: str) -> bool:
        return str(c.get(k, False)) == "True"
    return Config(spec_md=Path(c["spec_md"]), name=c["name"], board=c["board"], interview=c["interview"],
                  review=c["review"], model=c["model"],
                  hidden_spec=Path(c["hidden_spec"]) if c.get("hidden_spec") not in (None, "None") else None,
                  stop_after=None if c.get("stop_after") in (None, "None") else int(c["stop_after"]),
                  harness=c.get("harness", "deepagents"), cc_model=c.get("cc_model", "claude-haiku-5-5"),
                  cc_effort=c.get("cc_effort", "medium"), verif_level=c.get("verif_level", "V3"),
                  profile=c.get("profile", "single"), roles=c.get("roles") or None,
                  no_shell=flag("no_shell"),
                  data_dir=Path(c["data_dir"]) if c.get("data_dir") not in (None, "None") else None,
                  oracle=c.get("oracle", "openrouter"), oracle_cc_model=c.get("oracle_cc_model", "claude-haiku-5-5"),
                  spec_tests=flag("spec_tests"), spectest_model=c.get("spectest_model", "claude-sonnet-5-5"),
                  spectest_effort=c.get("spectest_effort", "medium"), spectest_max_loops=int(c.get("spectest_max_loops", 2)),
                  skill_routing=c.get("skill_routing", "off"),
                  router_model=c.get("router_model") if c.get("router_model") not in (None, "None") else None,
                  router_k=int(c.get("router_k", 8)),
                  harness_arms=c.get("harness_arms", "") if c.get("harness_arms") not in (None, "None") else "")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["project"]:                      # brief 27B: the project layer (project/), not part of the agent graph
        from project.cli import main as project_main
        return project_main(args[1:])
    from agent.graph.role_models import parse_roles
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
    r.add_argument("--profile", default="single",
                   help="per-role model routing (05f): single (today: one harness and model for every role) | cvdp "
                        "(RTL on Claude Code + Opus 5.5; model, tests, clarify on Claude Code + Sonnet 5.5). "
                        "The interview oracle always runs on --model.")
    r.add_argument("--roles", help='JSON of role overrides on top of the profile, for example '
                                   '\'{"rtl": {"harness": "claude_code", "model": "claude-opus-5-5", "effort": null}}\'; '
                                   "roles: clarify, model, tests, rtl")
    r.add_argument("--no-shell", action="store_true",
                   help="the subject is the USB-UART itself: build, lint and simulate without the test shell "
                        "(07a2-prep; also set when --hidden-spec sits next to a bench.yaml with no_shell: true)")
    r.add_argument("--data-dir", type=Path,
                   help="the task's data/ files (weights, images ...), copied to <design>/data (07a2-prep; default: "
                        "data/ next to spec.md, when it exists)")
    r.add_argument("--oracle", choices=["openrouter", "claude_code"], default="openrouter",
                   help="where the interview oracle runs: openrouter (--model) or claude_code (a headless `claude -p` on the "
                        "Max plan; no OpenRouter call at all, 07a2-prep)")
    r.add_argument("--oracle-cc-model", default="claude-haiku-5-5", help="model of --oracle claude_code")
    r.add_argument("--spec-tests", action="store_true",
                   help="08f (eval-2): after V2/V3, an independent bench written from spec.md alone must also pass (agent.graph.spectest)")
    r.add_argument("--spectest-model", default="claude-sonnet-5-5", help="Claude Code model of the spec-test role and its triage")
    r.add_argument("--spectest-max-loops", type=int, default=2, help="design_wrong round trips per run before 'unresolved'")
    r.add_argument("--max-usd", type=float, help="run cost cap (provider-reported); default RUN_LIMITS")
    r.add_argument("--verif-level", choices=["V1", "V2", "V3"], default="V3",
                   help="verification stage stage 2 must reach (default V3, the methodology; V1/V2 only for a cheaper run: "
                        "V3 needs multi-seed runs; the graph itself runs the Verilator coverage run and the mutation run)")
    r.add_argument("--skill-routing", choices=["off", "router"], default="off",
                   help="brief 36: router = a skill shortlist before each stage, skill_index/skill_excerpt, ranked load_skill")
    r.add_argument("--router-model", help="brief 36: OpenRouter model of the router's section classifier (default: rules only)")
    r.add_argument("--harness-arm", default="",
                   help="brief 42: comma-separated harness arms, default none (the baseline): H1 = context management "
                        "(offload of large tool results, earlier summarisation), H2 = hang protection (unbounded-wait check, "
                        "wall limit from the bench's sim-time budget, structured hang result)")
    r.add_argument("--router-k", type=int, default=8, help="brief 36: skills in the router's shortlist")
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
                     verif_level=a.verif_level, profile=a.profile, roles=parse_roles(a.roles),
                     no_shell=a.no_shell or task_no_shell(a.hidden_spec), data_dir=a.data_dir or task_data_dir(a.spec),
                     oracle=a.oracle, oracle_cc_model=a.oracle_cc_model, spec_tests=a.spec_tests,
                     spectest_model=a.spectest_model, spectest_max_loops=a.spectest_max_loops,
                     skill_routing=a.skill_routing, router_model=a.router_model, router_k=a.router_k,
                     harness_arms=a.harness_arm)
        cfg.role_models()                                     # fail early on an unknown profile, role or forbidden model
        if a.max_usd is not None:
            cfg.run_limits["usd"] = a.max_usd
        client, oracle_llm = _clients(cfg, a)
        rt = new_runtime(cfg, client, oracle_llm=oracle_llm)
        rt.client_for = (lambda m: _client(m, a.replay, None)) if cfg.oracle == "openrouter" else _no_openrouter
        if cfg.oracle == "claude_code":
            from agent.claude_code_arm.oracle import cc_oracle
            rt.oracle_llm = cc_oracle(cfg.oracle_cc_model, rt.run_dir / "oracle_calls.jsonl")
        graph = build_graph(checkpointer_for(rt.run_dir), routing=cfg.skill_routing != "off")
        _drive(graph, rt, {"configurable": {"thread_id": rt.run_id}},
               {"run_id": rt.run_id, "stage": 0, "visits": {}, "history": []}, replies)
        return 0
    # resume
    run_dir = ROOT / "runs" / a.run_id
    c = json.loads((run_dir / "config.json").read_text())
    cfg = config_from_json(c)
    if a.max_usd is not None:
        cfg.run_limits["usd"] = a.max_usd
    client, oracle_llm = _clients(cfg, a)
    rt = new_runtime(cfg, client, run_id=a.run_id, oracle_llm=oracle_llm)
    rt.client_for = (lambda m: _client(m, a.replay, None)) if cfg.oracle == "openrouter" else _no_openrouter
    if cfg.oracle == "claude_code":
        from agent.claude_code_arm.oracle import cc_oracle
        rt.oracle_llm = cc_oracle(cfg.oracle_cc_model, rt.run_dir / "oracle_calls.jsonl")
    graph = build_graph(checkpointer_for(run_dir), routing=cfg.skill_routing != "off")
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
