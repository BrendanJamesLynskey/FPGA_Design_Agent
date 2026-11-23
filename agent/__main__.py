"""CLI for the Deep Agents agent (brief 05b).

    python -m agent run <spec.md> --board nexys_a7_100t [--interview on|oracle|off] [--review on|off]
                        [--model openai/gpt-6-luna] [--hidden-spec <full spec>] [--replies <json>]
    python -m agent resume <run-id> [--rewind N] [--reply '<json>'] [--replies <json>]
    python -m agent resume <design-dir> ["<change request>"] [--kind K] [--from-stage N] [--dry-run] [--stop-after N]
                                                                   (brief 68 D: pick up older work from its handover)
    python -m agent review <design-dir> [--out DIR] [--intent FILE] [--improvements FILE] [--no-judge]   (brief 84: review an existing design, read-only)
    python -m agent document <run-dir> [--cc-model M] [--replay doc_calls.jsonl]   (brief 68 C: the DOC step on a finished run)
    python -m agent project check|status|hash|gen-tests <dir> ...     (the project layer, project/cli.py)
    python -m agent improve <design-dir> "<request>" [--more | --edit N "<change>" | --choose N]   (brief 104: analysis, then strategy options; --choose runs one)

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

from agent.core.boards import board_arg, board_name
from agent.core.session import ROOT


def scope_for_record(design: Path) -> dict | None:
    """The scope block of a run record (brief 102F): the selected, selectable, frozen and excluded components, the manifest hash and the
    waiver grant (``managed.scope_record``); None for a design that has no scope file."""
    from agent.core import managed
    try:
        proj = managed.load(design)
    except ValueError:
        proj = None
    if proj is not None:
        return managed.scope_record(proj)
    f = Path(design) / "build" / "managed" / "scope.json"
    if f.is_file():
        sc = json.loads(f.read_text())
        return {k: sc[k] for k in ("components", "source", "request", "note", "plan", "time") if k in sc}
    return None


def record_scope_in_config(run_dir: Path, design: Path) -> dict | None:
    """Put the run's scope block into its config.json (brief 102F), so a later ``resume <run>`` can re-check it."""
    sc = scope_for_record(design)
    f = Path(run_dir) / "config.json"
    if sc is not None and f.is_file():
        f.write_text(json.dumps({**json.loads(f.read_text()), "scope": sc}, indent=1))
    return sc


def with_scope(s: dict, design: Path) -> dict:
    """Brief 102: the request's scope (build/managed/scope.json of the run's design copy) is part of the run record, summary.json."""
    sc = scope_for_record(Path(design))
    if sc is not None:
        s = {**s, "scope": sc}
    from flow.options.cli import strategy_for_run      # brief 104: the strategy the request came from (analysis, options offered, the choice), when `agent improve` made it
    st = strategy_for_run(Path(design))
    if st is not None:
        s = {**s, "strategy": st}
    return s


def _drive(graph, rt, cfg_lg, first_input, replies: list) -> dict:
    from langgraph.types import Command

    from agent.graph.run import summary
    inp = first_input
    while True:
        graph.invoke(inp, cfg_lg)
        snap = graph.get_state(cfg_lg)
        pending = [i.value for t in snap.tasks for i in (t.interrupts or [])]
        if not pending:
            (rt.run_dir / "pending.json").unlink(missing_ok=True)
            break
        if not replies:
            (rt.run_dir / "pending.json").write_text(json.dumps({"paused": pending[0], "run_id": rt.run_id}, indent=1))     # brief 182: the navigator shows a pending question
            print(json.dumps({"paused": pending[0], "run_id": rt.run_id}, indent=1))
            return {"paused": pending[0]}
        reply = replies.pop(0)
        (rt.run_dir / "pending.json").unlink(missing_ok=True)
        print(json.dumps({"interrupt": pending[0].get("kind"), "stage": pending[0].get("stage"), "reply": reply}))
        inp = Command(resume=reply)
    if snap.values.get("doc") and (rt.run_dir / "summary.json").is_file():    # brief 68 C: frozen by the document node
        s = {**json.loads((rt.run_dir / "summary.json").read_text()), "doc": snap.values["doc"]}
    else:
        s = summary(rt, snap.values)
    s = with_scope(s, Path(rt.design))
    (rt.run_dir / "summary.json").write_text(json.dumps(s, indent=1))
    print(json.dumps(s, indent=1))
    return s


def task_no_shell(hidden_spec: Path | None) -> bool:
    """07a2-prep: a benchmark task's hidden/bench.yaml says ``no_shell: true`` (the subject is the USB-UART itself)."""
    import yaml
    b = hidden_spec.resolve().parent / "bench.yaml" if hidden_spec else None
    return bool(b and b.is_file() and (yaml.safe_load(b.read_text()) or {}).get("no_shell"))


def task_data_dir(spec_md: Path) -> Path | None:
    """07a2-prep: the task's ``data/`` directory, next to its spec.md (the benchmark task layout), when it exists."""
    d = spec_md.resolve().parent / "data"
    return d if d.is_dir() else None


#: the model flags that, when given on the command line, override the user and project model files (brief 108 aliases)
MODEL_FLAGS = {"--harness": "harness", "--cc-model": "cc_model", "--cc-effort": "cc_effort", "--model": "model", "--oracle": "oracle",
               "--oracle-cc-model": "oracle_cc_model", "--spectest-model": "spectest_model", "--router-model": "router_model"}


def model_kwargs(a, argv: list[str]) -> dict:
    """The Config fields of the model configuration: the project file, ``--model-config``, which model flags were given, the owner's Fable flag."""
    from agent.models.config import parse_cli_json
    given = tuple(sorted({v for f, v in MODEL_FLAGS.items() if any(x == f or x.startswith(f + "=") for x in argv)}))
    return dict(models_file=getattr(a, "models_file", None), model_config=parse_cli_json(getattr(a, "model_config", None)) or None,
                explicit=given, allow_fable=bool(getattr(a, "allow_fable", False)), replay_run=bool(getattr(a, "replay", None)))


def tape_spec_from(a, cfg) -> dict | None:
    """Brief 107: the record/replay tape of this run from ``--deterministic``, ``--tape``, ``--record-tape`` and ``--replay-tape``.
    ``--deterministic`` replays the tape (level 2) when there is one, else runs live at temperature 0 and records one (level 1); it raises
    DeterminismError, before any model call, when neither is possible. It never falls back to sampling."""
    from agent.models import determinism as D
    from agent.models.tape import DeterminismError, Tape
    if sum(bool(x) for x in (getattr(a, "deterministic", False), getattr(a, "record_tape", None), getattr(a, "replay_tape", None))) > 1:
        raise DeterminismError("choose one of --deterministic, --record-tape, --replay-tape")

    def replay(d: Path, note: str) -> dict:
        cfg.level1_seed = Tape.open(d, "replay").header.get("level1_seed")      # the table must be the recorded one
        cfg.replay_run = True
        return {"dir": d, "mode": "replay", "level": 2, "note": note}
    if getattr(a, "replay_tape", None):
        return replay(Path(a.replay_tape), "explicit --replay-tape")
    if getattr(a, "record_tape", None):
        return {"dir": Path(a.record_tape), "mode": "record", "level": 0, "note": "recording only: the calls are sampled as configured"}
    if getattr(a, "deterministic", False):
        d = D.tape_dir_for(cfg, getattr(a, "tape", None))
        if (d / "tape.jsonl").is_file():
            return replay(d, "--deterministic: a recording exists, so level 2")
        cfg.level1_seed = D.SEED
        D.check_level1(cfg.model_table(), cfg)
        return {"dir": d, "mode": "record", "level": 1, "note": "--deterministic: no recording, so level 1 (temperature 0, recorded for replay)"}
    return None


def project_models_file(spec: Path) -> Path | None:
    """The project layer: ``models.yaml`` next to the spec, when there is one."""
    f = spec.resolve().parent / "models.yaml"
    return f if f.is_file() else None


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
                  harness_arms=c.get("harness_arms", "") if c.get("harness_arms") not in (None, "None") else "",
                  hdl=c.get("hdl", "sv") or "sv",
                  design_plan=flag("design_plan"), closure=c.get("closure", "off") or "off",     # closure loop
                  docs=c.get("docs", "off") or "off",                                            # brief 68 C
                  models_file=Path(c["models_file"]) if c.get("models_file") not in (None, "None") else None,   # brief 108
                  model_config=c.get("model_config") or None, explicit=tuple(c.get("explicit") or ()),
                  allow_fable=str(c.get("allow_fable", False)) == "True",
                  level1_seed=int(c["level1_seed"]) if c.get("level1_seed") not in (None, "None") else None)


def models_cmd(a, argv: list[str]) -> int:
    """Brief 108: ``agent models show`` prints the resolved table and where each value came from; ``check`` validates it (the table is
    validated whenever it is built, so a bad table fails here) and, with ``--probe``, spends one minimal call per endpoint in use."""
    from agent.graph.run import Config
    from agent.models import Resolver
    from agent.models.config import ConfigError
    try:
        cfg = Config(spec_md=Path("spec.md"), name="models", **model_kwargs(a, argv))
        table = cfg.model_table()
    except ConfigError as e:
        print(f"models: {e}", file=sys.stderr)
        return 2
    if a.action == "show":
        print(json.dumps(table.record(), indent=1) if a.json else table.show())
        return 0
    print(table.show())
    print(f"\nthe table is valid ({len(table.entries())} entries, hash {table.hash})")
    if not a.probe:
        print("no endpoint was called; add --probe for one minimal call per endpoint (spends tokens)")
        return 0
    rows = Resolver(table).probe()
    for r in rows:
        print(f"{'ok  ' if r['ok'] else 'FAIL'} {r['purpose']:<11} {r['endpoint']:<14} {r['model']}  {r['detail']}  {r['seconds']}s")
    return 0 if all(r["ok"] for r in rows) else 1


def document_cmd(a) -> int:
    """Brief 68 C: the DOC step on a finished run (its summary.json gives the gates and the stop reason)."""
    from agent.graph import document
    rd = a.run_dir.resolve()
    s = json.loads((rd / "summary.json").read_text())
    log = rd / "doc_calls.jsonl"
    if a.replay:
        llm = document.replay_llm(a.replay)
        log = None if a.replay.resolve() == log else log
    else:
        from agent.models import resolver_for
        given = {k: v for k, v in (("model", a.cc_model), ("options", {"effort": a.cc_effort} if a.cc_effort else None)) if v}
        llm = resolver_for("doc", **given, run_dir=rd, command={"purposes": {"doc": {
            "endpoint": "claude_code", "model": "claude-sonnet-5-5", "options": {"effort": "medium"}}}},
            ).text("doc", label="doc", claude_log=rd / "doc_claude_code_calls.jsonl")
    res = document.document(rd / s["design"], rd, llm, run_id=s["run_id"], board=a.board, gates_last=s.get("gates_last"),
                            stop=s.get("stop"), verif_level=a.verif_level, resumed_from=s.get("resumed_from"),
                            carried=s.get("gates_carried"), log=log)
    gl, car = s.get("gates_last") or {}, s.get("gates_carried") or []
    res["signed_off"] = bool(res["ok"] and all(gl.get(n) is True or n in car for n in document.STAGE_NAMES))
    (rd / "doc.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return 0 if res["ok"] else 1


def pickup_cmd(a) -> int:
    """Brief 68 D: resume a design from its handover (agent.graph.pickup)."""
    from agent.graph import pickup
    from agent.graph.role_models import parse_roles
    from agent.graph.run import Config, build_graph, checkpointer_for, new_runtime
    ddir = Path(a.run_id).resolve()
    try:
        ld = pickup.load(ddir)
    except pickup.PickupError as e:
        print(f"resume: {e}", file=sys.stderr)
        return 2
    fresh = ld["fresh"]
    report = {"design": fresh["design"], "agent_md_tokens": ld["agent_tokens"], "design_files_tokens": ld["files_tokens"],
              "errors": fresh["errors"], "stale": fresh["stale"], "changed_files": fresh["changed_files"],
              "added_files": fresh.get("added_files"),
              "kb_pin": fresh["kb_pin"], "vivado": fresh["vivado"], "build_id": fresh.get("build_id")}
    if fresh["errors"]:
        print(json.dumps({**report, "resume": "refused: the handover has errors; fix them first"}, indent=1))
        return 2
    try:
        entry = pickup.entry_stage(ld["handover"], fresh, a.change, a.kind, a.from_stage)
    except pickup.PickupError as e:
        print(f"resume: {e}", file=sys.stderr)
        return 2
    report["entry"] = {"stage": entry["stage"], "kind": entry["kind"], "notes": entry.get("notes") or [],
                       "reasons": [{"stage": s, "why": w} for s, w in entry["reasons"]]}
    scope = None
    from agent.core import managed
    mproj = managed.load(ddir)
    if mproj is not None:                            # brief 102: a managed project: the request is scoped (--scope or resolved from the text)
        res = managed.resolve_request(mproj, a.change or "", [x for x in (a.scope or "").split(",") if x] or None)
        if res.question or res.scope is None:
            print(json.dumps({**report, "resume": "refused: " + (res.question or "the request names no component"), "question": res.question}, indent=1))
            return 2
        scope = res.scope
        report["scope"] = {**scope.as_dict(), "notes": res.notes}
    if a.dry_run or entry["stage"] >= pickup.DOC_ONLY:
        report["resume"] = "dry run" if a.dry_run else "nothing to re-run: the handover is current"
        print(json.dumps(report, indent=1))
        return 0
    hb = (ld["handover"].get("target") or {}).get("board")
    board = a.board or (hb if hb and (ROOT / "boards" / str(hb)).is_dir() else "nexys_a7_100t")
    ar = ld["handover"].get("agent_run") or {}
    old_cfg = (ROOT / ar["record"]).parent / "config.json" if ar.get("record") else None
    verif = a.verif_level or (json.loads(old_cfg.read_text()).get("verif_level") if old_cfg and old_cfg.is_file() else None) or "V3"
    report["settings"] = {"board": board, "verif_level": verif}
    cfg = Config(spec_md=ddir / "spec.md", name=ddir.name, board=board, model=a.model, stop_after=a.stop_after,
                 harness=a.harness, cc_model=a.cc_model, cc_effort=a.cc_effort, verif_level=verif,
                 profile=a.profile, roles=parse_roles(a.roles), docs=a.docs, **model_kwargs(a, sys.argv[1:]))
    cfg.role_models()
    if a.max_usd is not None:
        cfg.run_limits["usd"] = a.max_usd
    rt = new_runtime(cfg, None, replay=a.replay, record=a.record)
    try:
        state = pickup.prepare(ddir, rt, entry, a.change)
    except pickup.PickupError as e:
        print(f"resume: {e}", file=sys.stderr)
        return 2
    report["run_id"] = rt.run_id
    if scope is not None:                            # the scope and the plan go to the run's design copy, where its tools read them
        managed.start_run(managed.load(Path(rt.design)), scope)
        report["scope_record"] = record_scope_in_config(rt.run_dir, Path(rt.design))      # config.json (and summary.json at the end) carry it
    if getattr(a, "strategy_file", None):            # brief 104: the options the request was chosen from go with the run
        import shutil
        _st = json.loads(Path(a.strategy_file).read_text())
        _ch = _st.get("choice") or {}
        if not _ch or _ch.get("options_hash") != (_st.get("current") or {}).get("options_hash") or (scope is not None and list(scope.components) != list(_ch.get("scope") or [])):
            print("resume: the strategy file does not match this request (no choice, a changed options list, or another scope)", file=sys.stderr)
            return 2
        dst = Path(rt.design) / "build" / "managed" / "strategy.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(a.strategy_file, dst)
        shutil.copyfile(a.strategy_file, rt.run_dir / "strategy.json")
        report["strategy"] = {"file": "strategy.json", "chosen": (json.loads(Path(a.strategy_file).read_text()).get("choice") or {}).get("chosen")}
    (rt.run_dir / "resume.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    replies = json.loads(a.replies.read_text()) if a.replies else []
    graph = build_graph(checkpointer_for(rt.run_dir), routing=cfg.skill_routing != "off")
    _drive(graph, rt, {"configurable": {"thread_id": rt.run_id}}, state, replies)
    return 0


def live_cmd(a) -> int:
    """Brief 182: status, ask and request. The navigator's Live page calls the same code (navigator/summary.py, console.py, ask.py; agent/graph/requests.py)."""
    import time as _t
    from navigator import ask as nask
    from navigator import console as ncon
    from navigator import summary as nsum
    rd = Path(a.run_dir).resolve()
    runs, rid = rd.parent, rd.name
    if a.cmd == "status":
        def show() -> dict | None:
            s = nsum.summarise(runs, rid)
            if s is None:
                print("no such run directory", file=sys.stderr)
                return None
            print(json.dumps(s, indent=1, default=str) if a.json else s["sentence"] + "\n" + "".join(f"  request {r['id']} ({r['label']}): {r['status']}" + (f", {r['reason']}" if r["reason"] else "") + "\n" for r in s["requests"]), end="")
            return s
        if a.console:
            lst = ncon.steps(runs, rid)
            if lst is None:
                print("no such run directory", file=sys.stderr)
                return 2
            for x in lst["steps"]:
                print(f"{x['id']:<34} {x['label']:<26} {'running' if x['active'] else 'ended  '} {x['size']:>9} bytes  {x['source']}")
            if lst["restriction"]:
                print("(" + lst["restriction"] + ")")
            pick = a.step or next((x["id"] for x in reversed(lst["steps"]) if x["active"]), (lst["steps"][-1]["id"] if lst["steps"] else None))
            out = ncon.read(runs, rid, pick) if pick else None
            if out:
                print(f"--- {out['label']} ({out['source']}), last {len(out['lines'])} lines ---")
                print("\n".join(out["lines"][-60:]))
            return 0
        s = show()
        if s is None:
            return 2
        while a.follow and s and s["status"] != "finished":
            last = s["sentence"]
            _t.sleep(5)
            s = nsum.summarise(runs, rid)
            if s and s["sentence"] != last:
                show()
        return 0
    if a.cmd == "ask":
        try:
            r = nask.ask(runs, rid, a.question)
        except nask.AskError as e:
            print("ask refused: " + str(e), file=sys.stderr)
            return 2
        print(r["a"])
        print(f"\nrecords given: {', '.join(r['records_read'])}; cited: {', '.join(r['cited']) or 'none'}" + (f"; cites records it was not given: {', '.join(r['cites_unknown'])}" if r["cites_unknown"] else ""))
        print(f"model {r['model']}; cost {r['plan_estimate_usd'] if r['cost_usd'] is None else r['cost_usd']} ({r['cost_note']}); this run's questions: {r['qa_spent_usd']} of {r['qa_cap_usd']} USD, {r['qa_count']} of {r['qa_max']}")
        return 0
    from agent.core.session import STAGES
    from agent.graph import requests as rq
    ctl, stage = (None, None)
    if a.control:
        ctl = a.control[0]
        if len(a.control) > 2 or (ctl.replace("-", "_") == "stop_after") != (len(a.control) == 2):
            print("request refused: use --control pause | abort | stop-after N", file=sys.stderr)
            return 2
        try:
            stage = int(a.control[1]) if len(a.control) == 2 else None
        except ValueError:
            print("request refused: N must be a stage number", file=sys.stderr)
            return 2
    try:
        r = rq.submit(rd, control=ctl, stage=stage, design=a.design, stages=tuple(STAGES))
    except rq.RequestError as e:
        print("request refused: " + str(e), file=sys.stderr)
        return 2
    print(f"request {r['id']} queued: {rq.describe(r)}\n  applies: {r['applies']}\n  affects: {r['affects']}")
    return 0


def review_cmd(a) -> int:
    from flow.review import review
    from flow.review.judge import UNSET as J_UNSET
    reqs = [l.strip().lstrip("-*0123456789. ").strip() for l in a.improvements.read_text().splitlines() if l.strip() and not l.startswith("#")] if a.improvements else None
    out = a.out or ROOT / "runs" / "review_out" / a.design.resolve().name
    rep = review(a.design, out, intent_file=a.intent, improvements=reqs, use_judge=not a.no_judge, model=a.model, effort=a.effort if a.effort else J_UNSET,
                 claude_bin=a.claude_bin, tag=a.design.resolve().name)
    cnt = {s: sum(1 for f in rep["findings"] if f["severity"] == s) for s in ("critical", "major", "minor", "info")}
    print(json.dumps({"review": str(out / "REVIEW.md"), "agent_version": str(out / "REVIEW_AGENT.md"), "findings": cnt,
                      "design_unchanged": rep["design"]["unchanged"], "judge_ran": rep["judge"]["ran"]}, indent=1))
    return 0 if rep["design"]["unchanged"] else 2


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["project"]:                      # brief 27B: the project layer (project/), not part of the agent graph
        from project.cli import main as project_main
        return project_main(args[1:])
    from agent.access import require_or_exit      # brief 94: run, resume and document all start here
    require_or_exit("python -m agent")
    from agent.graph.role_models import parse_roles
    from agent.graph.run import Config, build_graph, checkpointer_for, new_runtime
    ap = argparse.ArgumentParser(prog="python -m agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("spec", type=Path)
    r.add_argument("--board", default="nexys_a7_100t", type=board_arg,
                   help="a board id or the words of a request (boards/catalogue.yaml; docs/board_catalogue.md)")
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
                                   "roles (record keys): clarify (Clarifier), model (Modeller), tests (Verifier), rtl (Designer)")
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
    r.add_argument("--harness-arm", default="H1",
                   help="brief 42: comma-separated harness arms, default H1 (owner decision 2026-11-12, made after the data): "
                        "H1 = context management (offload of large tool results, earlier summarisation), "
                        "H2 = hang protection (unbounded-wait check, wall limit from the bench's sim-time budget, structured "
                        "hang result), H9 = typed digests; A0 = the baseline with no arm (pin it for comparisons with earlier runs)")
    r.add_argument("--router-k", type=int, default=8, help="brief 36: skills in the router's shortlist")
    r.add_argument("--design-plan", action="store_true",
                   help="plan before building: stage 1 lists the datapaths, and the timing plan maps each operation to a DSP slice, "
                        "block RAM, carry chain or LUTs and picks the pipeline depth (needs a delay model for the device family)")
    r.add_argument("--closure", choices=["on", "off"], default="off",
                   help="after the build, loop on timing, area and power, re-checking simulation after every change, until all hold "
                        "or the loop stalls (stage 6; tested with fakes only; default off)")
    r.add_argument("--docs", choices=["on", "off"], default="on",
                   help="brief 68: at the end of the run the Designer writes handover.yaml and the flow renders README.md and "
                        "AGENT.md; the DOC gate (flow/handover.py checks) must pass for sign-off (doc.json)")
    r.add_argument("--models-file", type=Path,
                   help="brief 108: the project's model table (default: models.yaml next to the spec); layers over ~/.config/fpga_design_agent/models.yaml")
    r.add_argument("--model-config", help="brief 108: JSON in the models.yaml format, the command-line layer of the model table "
                                          "(purposes: interpret, oracle, model, tests, spectest, rtl, constraints, closure, latency, review, doc, route)")
    r.add_argument("--allow-fable", action="store_true", help="the owner's flag: permits Fable on a claude_code endpoint (no file can set it)")
    r.add_argument("--hdl", choices=["sv", "vhdl"], default="sv",
                   help="the design language; vhdl = VHDL-2008 RTL (GHDL lint, GHDL netlist or GHDL simulation, "
                        "read_vhdl -vhdl2008 in Vivado); the test shell stays SystemVerilog")
    for p in (r, sub.add_parser("resume")):
        p.add_argument("--replies", type=Path)
        p.add_argument("--reply")
        p.add_argument("--replay", help="LLM replay fixture (no network)")
        p.add_argument("--record", help="record LLM calls to this fixture")
        p.add_argument("--deterministic", action="store_true",
                       help="brief 107: replay the recorded tape (level 2) when there is one, else run at temperature 0 and record one (level 1); "
                            "fails before the first call when neither is possible; never samples")
        p.add_argument("--tape", help="with --deterministic: the tape directory (default ~/.local/share/fpga_design_agent/tapes/<design name>)")
        p.add_argument("--record-tape", help="brief 107: record every model call to this tape directory (private; outside the repo or git-ignored)")
        p.add_argument("--replay-tape", help="brief 107: serve every model call from this tape directory (level 2); a missing call is an error")
    rs = sub._name_parser_map["resume"]
    rs.add_argument("run_id", help="a run id under runs/, or a design directory with handover.yaml (brief 68 D)")
    rs.add_argument("change", nargs="?", help="design resume: the change request")
    rs.add_argument("--rewind", type=int)
    rs.add_argument("--max-usd", type=float, help="cost cap for this resumed process (the meter starts at 0)")
    rs.add_argument("--kind", choices=sorted(__import__("agent.graph.pickup", fromlist=["x"]).STAGE_OF_KIND),
                    help="design resume: the change's class, instead of the keyword classifier")
    rs.add_argument("--from-stage", type=int, help="design resume: enter at this stage, overriding the rule")
    rs.add_argument("--dry-run", action="store_true", help="design resume: report the freshness and the entry stage only")
    rs.add_argument("--scope", help="design resume of a managed project: the components or hierarchy paths this request may touch "
                                    "(comma separated; default: resolved from the change text, else every owned component)")
    rs.add_argument("--strategy-file", type=Path, help="design resume: the strategy.json `agent improve --choose` saved (the options offered and the choice go into the run record)")
    rs.add_argument("--stop-after", type=int)
    rs.add_argument("--board", type=board_name, help="design resume: default the handover's target.board when it names a board directory")
    rs.add_argument("--model", default="openai/gpt-6-luna")
    rs.add_argument("--harness", choices=["deepagents", "claude_code"], default="deepagents")
    rs.add_argument("--cc-model", default="claude-haiku-5-5")
    rs.add_argument("--cc-effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    rs.add_argument("--profile", default="single")
    rs.add_argument("--roles")
    rs.add_argument("--verif-level", choices=["V1", "V2", "V3"], help="design resume: default the original run's, else V3")
    rs.add_argument("--docs", choices=["on", "off"], default="on")
    rs.add_argument("--models-file", type=Path, help="design resume: the project's model table (a run resume reads the run's own)")
    rs.add_argument("--model-config", help="design resume: JSON command-line layer of the model table")
    rs.add_argument("--allow-fable", action="store_true", help="the owner's flag: permits Fable on a claude_code endpoint")
    rs.add_argument("--allow-model-change", action="store_true", help="resume a run although its model table hash has changed")
    dc = sub.add_parser("document", help="brief 68 C: the DOC step on a finished run directory")
    dc.add_argument("run_dir", type=Path)
    dc.add_argument("--board", default="nexys_a7_100t", type=board_name)
    dc.add_argument("--cc-model", help="the doc purpose's model (default: the model table; built in: claude-sonnet-5-5 on claude_code)")
    dc.add_argument("--cc-effort", help="the doc purpose's effort (default: the model table; built in: medium)")
    dc.add_argument("--verif-level", help="default: the run's config.json, else V3")
    dc.add_argument("--replay", type=Path, help="replay the replies of a recorded doc_calls.jsonl (no model call)")
    rv = sub.add_parser("review", help="brief 84: review an existing design (read-only); findings, understanding, verification gap")
    rv.add_argument("design", type=Path, help="a directory with RTL, tests, constraints and docs")
    rv.add_argument("--out", type=Path, help="output directory (default runs/review_out/<design>)")
    rv.add_argument("--intent", type=Path, help="a statement of intent (default: spec.md or INTENT.md in the design)")
    rv.add_argument("--improvements", type=Path, help="a plain-English list, one request per line: restate, assess and order them (a plan only)")
    rv.add_argument("--no-judge", action="store_true", help="the check suite alone (the benchmark's baseline)")
    rv.add_argument("--model", help="the review purpose's model (default: the model table; built in: claude-sonnet-5-5)")
    rv.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"], help="default: the model table (built in: medium)")
    rv.add_argument("--claude-bin", default="claude", help="the pinned Claude Code binary")
    md = sub.add_parser("models", help="brief 108: show or check the model table (which endpoint, model and options each purpose uses)")
    md.add_argument("action", choices=["show", "check"])
    md.add_argument("--models-file", type=Path, help="the project's models.yaml")
    md.add_argument("--model-config", help="JSON command-line layer")
    md.add_argument("--allow-fable", action="store_true")
    md.add_argument("--json", action="store_true", help="show: the resolved table as JSON (the run-record form)")
    md.add_argument("--probe", action="store_true", help="check: also make one minimal call per endpoint in use (spends tokens)")
    st = sub.add_parser("status", help="brief 182: a run's status in plain words (no model call); --console for the live console")
    st.add_argument("run_dir", type=Path)
    st.add_argument("--follow", action="store_true", help="print the status again whenever it changes, until the run ends")
    st.add_argument("--console", action="store_true", help="list the console steps and show the tail of one (--step ID, default the running or latest)")
    st.add_argument("--step")
    st.add_argument("--json", action="store_true")
    ak = sub.add_parser("ask", help="brief 182: ask a read-only model a question about a run, answered from that run's records only (logged in qa.jsonl)")
    ak.add_argument("run_dir", type=Path)
    ak.add_argument("question")
    rq_ = sub.add_parser("request", help="brief 182: queue a mid-run request, applied at the run's next safe point (a stage boundary)")
    rq_.add_argument("run_dir", type=Path)
    g_ = rq_.add_mutually_exclusive_group(required=True)
    g_.add_argument("--control", nargs="+", metavar=("ACTION", "N"), help="pause | abort | stop-after N")
    g_.add_argument("--design", help="free text: a change for the design, e.g. 'use block RAM for the FIFO' (refused for a scored run)")
    from agent.graph.latency_loop import add_parser as _latency_parser    # brief 97
    _latency_parser(sub)
    from flow.options.cli import add_parser as _improve_parser           # brief 104
    _improve_parser(sub)
    a = ap.parse_args(argv)
    if a.cmd in ("status", "ask", "request"):
        return live_cmd(a)
    if a.cmd == "models":
        return models_cmd(a, args)
    if a.cmd == "latency":
        from agent.graph.latency_loop import latency_cmd
        return latency_cmd(a)
    if a.cmd == "improve":
        from flow.options.cli import improve_cmd
        return improve_cmd(a, main)
    if a.cmd == "review":
        return review_cmd(a)
    if a.cmd == "document":
        return document_cmd(a)
    if a.cmd == "resume" and (Path(a.run_id) / "handover.yaml").is_file():
        return pickup_cmd(a)
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
                     harness_arms=a.harness_arm, hdl=a.hdl,
                     design_plan=a.design_plan, closure=a.closure, docs=a.docs,          # closure loop; brief 68 C
                     **{**model_kwargs(a, args), "models_file": a.models_file or project_models_file(a.spec)})
        cfg.role_models()                                     # fail early on an unknown profile, role or forbidden model
        if a.max_usd is not None:
            cfg.run_limits["usd"] = a.max_usd
        from agent.models.tape import DeterminismError
        try:
            tspec = tape_spec_from(a, cfg)
            rt = new_runtime(cfg, None, replay=a.replay, record=a.record, tape_spec=tspec)
        except DeterminismError as e:
            print(f"deterministic: {e}", file=sys.stderr)
            return 2
        graph = build_graph(checkpointer_for(rt.run_dir), routing=cfg.skill_routing != "off")
        _drive(graph, rt, {"configurable": {"thread_id": rt.run_id}},
               {"run_id": rt.run_id, "stage": 0, "visits": {}, "history": []}, replies)
        return 0
    # resume
    run_dir = ROOT / "runs" / a.run_id
    c = json.loads((run_dir / "config.json").read_text())
    cfg = config_from_json(c)
    cfg.replay_run = bool(a.replay)
    if a.max_usd is not None:
        cfg.run_limits["usd"] = a.max_usd
    was = (c.get("models") or {}).get("hash")                # brief 108: resume on the same model table the run started with
    if was and was != cfg.model_table().hash and not a.allow_model_change:
        print(f"resume: the model configuration changed since the run started (table hash {was} then, {cfg.model_table().hash} now); "
              "restore the models.yaml files, or pass --allow-model-change", file=sys.stderr)
        return 2
    from agent.models.tape import DeterminismError
    try:
        tspec = tape_spec_from(a, cfg)
        rt = new_runtime(cfg, None, run_id=a.run_id, replay=a.replay, record=a.record, tape_spec=tspec)
    except DeterminismError as e:
        print(f"deterministic: {e}", file=sys.stderr)
        return 2
    from agent.core import managed                    # brief 102F: a managed project's run continues the request it started with
    try:
        mproj = managed.load(Path(rt.design))
    except ValueError as e:
        print(f"resume: {e}", file=sys.stderr)
        return 2
    if mproj is not None:
        bad = managed.check_resume(mproj, c.get("scope"), [x for x in (a.scope or "").split(",") if x] or None)
        if bad:
            print("resume refused (scope): " + "; ".join(bad), file=sys.stderr)
            return 2
        cf = run_dir / "config.json"                  # new_runtime rewrote config.json: keep the scope the run started with
        cf.write_text(json.dumps({**json.loads(cf.read_text()), "scope": c["scope"]}, indent=1))
    elif a.scope:
        print("resume: --scope is for a managed project; this run's design has no project.yaml", file=sys.stderr)
        return 2
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
