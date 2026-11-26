"""CLI for the Deep Agents agent (brief 05b).

    python -m agent run <spec.md> --board nexys_a7_100t [--interview on|oracle|off] [--review on|off]
                        [--model openai/gpt-6-luna] [--hidden-spec <full spec>] [--replies <json>]
    python -m agent resume <run-id> [--rewind N] [--reply '<json>'] [--replies <json>]
    python -m agent resume <design-dir> ["<change request>"] [--kind K] [--from-stage N] [--dry-run] [--stop-after N]
                                                                   (brief 68 D: pick up older work from its handover)
    python -m agent review <design-dir> [--out DIR] [--intent FILE] [--improvements FILE] [--no-judge]   (brief 84: review an existing design, read-only)
    python -m agent document <run-dir> [--cc-model M] [--replay doc_calls.jsonl]   (brief 68 C: the DOC step on a finished run)
    python -m agent project check|status|hash|gen-tests <dir> ...     (the project layer, project/cli.py)
    python -m agent ip search|rank|show|use ...                  (brief 150: the IP library, `python -m agent ip --help`)
    python -m agent example list | run <name> | compare <run_dir> | tools <name>   (brief 195: reproducible examples with reference runs)
    python -m agent improve <design-dir> "<request>" [--more | --edit N "<change>" | --choose N]   (brief 104: analysis, then strategy options; --choose runs one)

    python -m agent doctor [--json] [--no-probe]        (brief 157: what this machine is missing before a first run; no key needed)
    python -m agent models show                          (brief 157: the model table; no key needed)

Without the access key only these run: ``--help`` at any level, ``doctor``, ``models show`` and ``resume <design-dir> ... --dry-run``
(``agent/newcomer.py``, the single place that decides it; ``agent/tests/test_157_newcomer_cli.py`` proves everything else still stops at
the gate). Every other command exits 2 with one line naming FDA_ACCESS_KEY.

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

ROOT = Path(__file__).resolve().parents[1]           # the checkout (agent.core.session.ROOT is the same path; no import, so --help and doctor need no extras)


def newcomer_is_design_resume(run_id: str) -> bool:
    from agent.newcomer import is_design_resume
    return is_design_resume(run_id)


def board_arg(text: str):
    """``--board``: a board id or the words of a request (agent.core.boards, imported when the option is used)."""
    from agent.core.boards import board_arg as f
    return f(text)


def board_name(text: str):
    from agent.core.boards import board_name as f
    return f(text)


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


NEEDS_PERMISSION = "needs_permission"
EXIT_NEEDS_PERMISSION, EXIT_PERMISSION_DENIED = 3, 4        # brief 222: distinct from success (0) and a usage error (2)


def drive_exit(res: dict) -> int:
    """The exit code of a driven run: 3 when it stopped to ask for a permission nobody was there to give, 4 when a permission was refused, else 0."""
    if res.get("status") == NEEDS_PERMISSION:
        return EXIT_NEEDS_PERMISSION
    if str(res.get("stop") or "").startswith("permission denied"):
        return EXIT_PERMISSION_DENIED
    return exit_status(res)         # brief 210: 3 as well when the run stopped on unresolved requirements (both mean "a person has to answer"; the JSON on stdout says which)


def permission_spec(a, name: str | None, ap) -> dict:
    """The run's permission policy from the command line and the config file (the command line wins); a bad name is a usage error."""
    from agent.core import permissions as _perm
    try:
        return _perm.resolve(a.permissions, a.allow, a.deny, a.ask_above_usd, project=name, cli_ask=a.ask)
    except ValueError as e:
        ap.error(str(e))


def resume_permissions(a, rt, c: dict) -> int | None:
    """On ``resume``: flags on the command line change the run's policy (a new mode drops what the old one was granted); a higher cost cap needs
    ``raise_budget``. Returns an exit code when the resume must not go on, else None."""
    from agent.core import permissions as _perm
    pol = getattr(rt, "policy", None)
    if pol is None:                                           # a runtime without a policy (a test double): nothing to change or check
        return None
    if a.permissions or a.allow or a.deny or a.ask or a.ask_above_usd is not None:
        spec = pol.spec()
        if a.permissions and a.permissions != pol.mode:
            spec.update(mode=a.permissions, overrides={})
        spec["source"] = "command line (resume)"
        for n in a.ask:
            spec["overrides"][n] = _perm.ASK
        for n in a.allow:
            spec["overrides"][n] = _perm.ALLOW
        for n in a.deny:
            spec["overrides"][n] = _perm.DENY
        if a.ask_above_usd is not None:
            spec["ask_above_usd"] = a.ask_above_usd
        pol.change_mode(spec)
        print(json.dumps({"permissions": {"mode": pol.mode, "overrides": pol.overrides, "source": pol.source}}))
    prior = (c.get("run_limits") or {}).get("usd")
    prior_scale = float((c.get("models") or {}).get("budget_scale") or 1.0)
    raising = (a.max_usd is not None and prior is not None and float(a.max_usd) > float(prior)) or (a.budget_scale is not None and float(a.budget_scale) > prior_scale)
    if raising:
        d = pol.decide("raise_budget", None, f"cost cap {prior} -> {a.max_usd}, scale {prior_scale} -> {a.budget_scale}")
        if d.result == _perm.DENY:
            print(json.dumps({"status": "permission_denied", "needs": ["raise_budget"], "why": d.by, "run_id": rt.run_id}, indent=1))
            return EXIT_PERMISSION_DENIED
        if d.result == _perm.ASK:
            print(json.dumps({"status": NEEDS_PERMISSION, "needs": ["raise_budget"], "run_id": rt.run_id,
                              "how": f"python -m agent resume {rt.run_id} --allow raise_budget --max-usd {a.max_usd}" if a.max_usd is not None else
                              f"python -m agent resume {rt.run_id} --allow raise_budget --budget-scale {a.budget_scale}"}, indent=1))
            return EXIT_NEEDS_PERMISSION
        if d.by.startswith("override") or d.by.startswith("mode"):
            pol.grant(["raise_budget"], d.by, None, "a higher cost cap")
    return None


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
            if pending[0].get("kind") == "review" and pending[0].get("hardware"):      # brief 219 fix 7: a pause for the programming approval leaves the run record
                from agent.graph.run import write_paused_record
                write_paused_record(rt, snap.values, pending[0])
            out = {"paused": pending[0], "run_id": rt.run_id}
            if pending[0].get("kind") == "permission":                                      # brief 222: a headless run stops here, on purpose, with what it needs
                out = {"status": NEEDS_PERMISSION, **out, "needs": pending[0].get("needs"), "how": pending[0].get("resume"),
                       "or": "python -m agent resume " + rt.run_id + " --allow <action> (or --permissions auto|full)"}
            print(json.dumps(out, indent=1))
            return {"paused": pending[0], **({"status": NEEDS_PERMISSION} if pending[0].get("kind") == "permission" else {})}
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


def exit_status(summary: dict | None) -> int:
    """0, or ``agent.graph.requirements.EXIT_REQUIREMENTS`` (3) when the run stopped because requirements are unresolved: not a crash,
    and distinct from usage errors (2), so a script can tell "answer these questions" from "the command was wrong" (brief 210)."""
    from agent.graph import requirements as RQ
    return RQ.EXIT_REQUIREMENTS if RQ.is_requirements_stop((summary or {}).get("stop")) else 0


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
    mc = parse_cli_json(getattr(a, "model_config", None))
    if getattr(a, "budget_scale", None) is not None:          # brief 209b: --budget-scale is one more key of the command-line layer
        mc = parse_cli_json({**mc, "budget_scale": a.budget_scale})
    return dict(models_file=getattr(a, "models_file", None), model_config=mc or None,
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


def _literal(v):
    """brief 194: config.json stores every field with str(); a dict field comes back through literal_eval (None for absent or 'None')."""
    import ast
    if v in (None, "None", ""):
        return None
    return v if isinstance(v, dict) else ast.literal_eval(v)


def config_from_json(c: dict):
    """The Config of a run from its config.json (``resume``); runs from before 05f have no profile: ``single``."""
    from agent.graph.run import Config
    def flag(k: str) -> bool:
        return str(c.get(k, False)) == "True"
    return Config(spec_md=Path(c["spec_md"]), name=c["name"], board=c["board"], interview=c["interview"], requirements=c.get("requirements") or "",
                  review=c["review"], model=c["model"],
                  hidden_spec=Path(c["hidden_spec"]) if c.get("hidden_spec") not in (None, "None") else None,
                  stop_after=None if c.get("stop_after") in (None, "None") else int(c["stop_after"]),
                  harness=c.get("harness", "deepagents"), cc_model=c.get("cc_model", "claude-haiku-5-5"),
                  cc_effort=c.get("cc_effort", "medium"), verif_level=c.get("verif_level", "V3"),
                  verif_profile=c.get("verif_profile", "standard"), verif_sets=_literal(c.get("verif_sets")),
                  settings_file=Path(c["settings_file"]) if c.get("settings_file") not in (None, "None", "") else None, settings_flags=_literal(c.get("settings_flags")),
                  profile=c.get("profile", "single"), roles=c.get("roles") or None,
                  no_shell=flag("no_shell"), block_shell=c.get("block_shell") if c.get("block_shell") not in (None, "None") else "",
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
                  coverage_loop=c.get("coverage_loop", "off") or "off", req_sva=c.get("req_sva", "off") or "off",   # brief 218
                  readiness=c.get("readiness", "off") or "off", readiness_limits=dict(_literal(c.get("readiness_limits")) or {}),   # brief 227
                  models_file=Path(c["models_file"]) if c.get("models_file") not in (None, "None") else None,   # brief 108
                  model_config=c.get("model_config") or None, explicit=tuple(c.get("explicit") or ()),
                  allow_fable=str(c.get("allow_fable", False)) == "True",
                  level1_seed=int(c["level1_seed"]) if c.get("level1_seed") not in (None, "None") else None,
                  permissions=_literal(c.get("permissions")))                                    # brief 222


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
    from agent.access import require_or_exit      # brief 157: `check` (and --probe, which spends tokens) is not the exempt `show`
    require_or_exit("python -m agent models check")
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
        entry = getattr(a, "entry_override", None) or pickup.entry_stage(ld["handover"], fresh, a.change, a.kind, a.from_stage)   # brief 159: revise gives its own
    except pickup.PickupError as e:
        print(f"resume: {e}", file=sys.stderr)
        return 2
    if entry.get("question"):                        # brief 149: nothing matched; a question, not stage 0
        print(json.dumps({**report, "resume": "no entry stage: a question", "question": entry["question"]}, indent=1))
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
    from agent.access import require_or_exit      # brief 157: past the dry run this resume calls models and writes a run: the gate again,
    require_or_exit("python -m agent resume")     # in case main() let the command line through without a key
    hb = (ld["handover"].get("target") or {}).get("board")
    board = a.board or (hb if hb and (ROOT / "boards" / str(hb)).is_dir() else "nexys_a7_100t")
    ar = ld["handover"].get("agent_run") or {}
    old_cfg = (ROOT / ar["record"]).parent / "config.json" if ar.get("record") else None
    verif = a.verif_level or (json.loads(old_cfg.read_text()).get("verif_level") if old_cfg and old_cfg.is_file() else None) or "V3"
    report["settings"] = {"board": board, "verif_level": verif}
    cfg = Config(spec_md=ddir / "spec.md", name=ddir.name, board=board, model=a.model, stop_after=a.stop_after,
                 harness=a.harness, cc_model=a.cc_model, cc_effort=a.cc_effort, verif_level=verif,
                 profile=a.profile, roles=parse_roles(a.roles), docs=a.docs, permissions=permission_spec(a, ddir.name, build_parser()),
                 **model_kwargs(a, sys.argv[1:]))
    cfg.role_models()
    if a.max_usd is not None:
        cfg.run_limits["usd"] = a.max_usd
    from agent.core.permissions import NeverRefused
    try:
        rt = new_runtime(cfg, None, replay=a.replay, record=a.record)
    except NeverRefused as e:                                # brief 222: a cost cap above the hard cap
        print(f"resume: {e}", file=sys.stderr)
        return 2
    try:
        state = pickup.prepare(ddir, rt, entry, a.change)
        if getattr(a, "revise_goals", None) is not None:           # brief 159: the typed goals (and a retarget) go into the run's copy, never the source
            from agent.graph import revise as _rv
            report["revise_written"] = _rv.write_goals(Path(rt.design), a.revise_goals, getattr(a, "revise_retarget", None),
                                                       (ld["handover"].get("target") or {}).get("part"))
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
    return drive_exit(_drive(graph, rt, {"configurable": {"thread_id": rt.run_id}}, state, replies))


def revise_cmd(a) -> int:
    """Brief 159: ``agent revise <design> --goal ... [--retarget ...]``: the plan (agent.graph.revise), then, unless --dry-run, the run."""
    from agent.graph import goals as G
    from agent.graph import pickup
    from agent.graph import revise as R
    ddir = Path(a.design).resolve()
    try:
        goals = [G.parse_goal(t, source=a.source) for t in a.goal]
        ld = pickup.load(ddir)
        pl = R.plan(ddir, ld, goals, a.retarget)
    except (G.GoalError, R.ReviseError, pickup.PickupError) as e:
        print(f"revise: {e}", file=sys.stderr)
        return 2
    if ld["fresh"]["errors"]:
        print(json.dumps({"revise": "refused: the handover has errors; fix them first", "errors": ld["fresh"]["errors"]}, indent=1))
        return 2
    out = R.public(pl)
    if a.dry_run or pl["entry"]["stage"] >= pickup.DOC_ONLY:
        out["revise"] = "dry run" if a.dry_run else "nothing to re-run: the committed evidence already meets every goal and the handover is current"
        print(json.dumps(out, indent=1, default=str))
        return 0
    print(json.dumps(out, indent=1, default=str))
    text = "; ".join([c["goal"] for c in out["changes"]] + ([f"retarget to {a.retarget}"] if a.retarget else []))
    b = argparse.Namespace(**vars(a))
    b.run_id, b.change, b.kind, b.from_stage, b.scope, b.strategy_file, b.rewind, b.stop_after = (
        str(ddir), "revise: " + text, None, None, None, None, None, getattr(a, "stop_after", None))
    b.entry_override = {"stage": pl["entry"]["stage"], "kind": pl["entry"]["kind"],
                        "reasons": [(r["stage"], r["why"]) for r in pl["entry"]["reasons"]], "notes": pl["entry"]["notes"]}
    b.revise_goals = pl["_after"]
    b.revise_retarget = (pl["retarget"] or {}).get("to") if pl["retarget"] and pl["retarget"].get("stage") is not None else None
    if b.revise_retarget and b.revise_retarget.get("board") and not getattr(a, "board", None):
        b.board = b.revise_retarget["board"]
    return pickup_cmd(b)


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


def build_parser() -> argparse.ArgumentParser:
    """The command line. Building it reads no key and no private file; ``--help`` is argparse's own, so it prints and exits 0 before the
    access gate (brief 157). Which commands need the key is in ``agent.newcomer.COMMANDS`` and in the epilog."""
    from agent import newcomer
    ap = argparse.ArgumentParser(prog="python -m agent", description=newcomer.TOP_DESCRIPTION, epilog=newcomer.TOP_EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="command")
    r = sub.add_parser("run", help=newcomer.COMMANDS["run"][0], description=newcomer.COMMANDS["run"][1], epilog=newcomer.RUN_EPILOG,
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    r.add_argument("spec", type=Path, help="the plain-English spec (spec.md); a task directory's data/ and bench.yaml sit beside it")
    r.add_argument("--board", default="nexys_a7_100t", type=board_arg,
                   help="a board id or the words of a request (boards/catalogue.yaml; docs/board_catalogue.md)")
    r.add_argument("--name", help="the design's name (default: the spec's directory name)")
    r.add_argument("--interview", choices=["on", "oracle", "off"], default="off",
                   help="on: the clarifier asks a person questions; oracle: a model answers them from --hidden-spec; off (default): it assumes")
    r.add_argument("--requirements", choices=["loose", "standard", "strict"], default=None,
                   help="how strict the interview is about unanswered questions (brief 210). loose: every gap is defaulted and listed in the handover; "
                        "standard: a high-risk question must be answered or waived, else the run stops at clarify (exit 3); strict: every question must "
                        "be answered or waived. Default: the request's own 'Requirements: <level>' line, else the design package, else the built-in "
                        "default (docs/agent.md)")
    r.add_argument("--review", choices=["on", "off"], default="off", help="on: pause for a person's decision after every stage")
    r.add_argument("--model", default="openai/gpt-6-luna", help="the OpenRouter model of the default endpoint (see `models show` for every purpose)")
    r.add_argument("--hidden-spec", type=Path, help="the full spec an interview oracle answers from (evaluation runs)")
    r.add_argument("--stop-after", type=int, metavar="N",
                   help="stop after stage N passes; stages count from 0: 0 clarify, 1 board-and-device-planning, 2 rtl-design-creation, "
                        "3 constraints, 4 synthesis, 5 implementation, 6 timing-closure, 7 power-closure, 8 drc-closure, "
                        "9 configuration-and-debug. 0-2 need no Vivado; the default (no flag) runs to 9")
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
                        "(07a2-prep; also set when --hidden-spec sits next to a bench.yaml with no_shell: true, and for a board "
                        "with no UART such as the KR260, from its board file: brief 209a)")
    r.add_argument("--block-for-shell", nargs="?", const="shell.yaml", default="", metavar="SHELL_FILE",
                   help="goal kind 'block for a shell' (brief 235): the design is a block inside a supplied shell (for example the Red Pitaya vendor shell), not a "
                        "board top. The constraints gate then checks the block's ports against boards/<board>/shell/SHELL_FILE (default shell.yaml) and "
                        "refuses pins, clocks and timing commands in design.xdc, which may stay empty. Implies --no-shell")
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
    r.add_argument("--budget-scale", type=float, help="brief 209b: multiplies every stage USD budget and the default run cap (for a dearer model; "
                   "default 1, or `budget_scale:` in a models file); an explicit --max-usd stays as given")
    r.add_argument("--verif-level", choices=["V1", "V2", "V3"], default="V3",
                   help="verification stage stage 2 must reach (default V3, the methodology; V1/V2 only for a cheaper run: "
                        "V3 needs multi-seed runs; the graph itself runs the Verilator coverage run and the mutation run)")
    r.add_argument("--verif-profile", choices=["prototype", "standard", "thorough", "ip_release", "high_dependability", "low_latency"],
                   help="brief 194: the verification profile, a preset of per-method switches (docs/assurance.md). Not --profile, which is the "
                        "model routing of brief 05f. Default: standard (today's behaviour); with --interview on or oracle and no profile given, "
                        "the interview proposes one")
    r.add_argument("--settings", type=Path, metavar="FILE",
                   help="brief 194: a proposed_settings.yaml (agent propose <folder>). Each setting becomes a question of the spec interview, whose default "
                        "is the proposed value and whose reason names its source; the run cannot leave the interview with an unconfirmed setting. An "
                        "explicit --board or --verif-profile becomes the proposed value")
    r.add_argument("--set", dest="verif_set", action="append", default=[], metavar="SWITCH=VALUE",
                   help="brief 194: override one switch of the profile, e.g. --set seeds=5 --set timing_sim=on (repeatable); --verif-level and "
                        "--spec-tests are overrides of their switches and are recorded as such")
    r.add_argument("--skill-routing", choices=["off", "router"], default="off",
                   help="brief 36: router = a skill shortlist before each stage, skill_index/skill_excerpt, ranked load_skill")
    r.add_argument("--router-model", help="brief 36: OpenRouter model of the router's section classifier (default: rules only)")
    r.add_argument("--harness-arm", default="H1",
                   help="brief 42: comma-separated harness arms, default H1 (owner decision 2026-11-12, made after the data): "
                        "H1 = context management (offload of large tool results, earlier summarisation), "
                        "H2 = hang protection (unbounded-wait check, wall limit from the bench's sim-time budget, structured "
                        "hang result), H9 = typed digests; brief 213 repair feedback, off unless named: R1 = the first failing check "
                        "(RTL values over the last cycles, the model's value, the transaction in flight, the driver cone) in place of the raw "
                        "simulator log tail, R2 = the failure ledger of earlier stage-2 visits, R3 = the fresh-stimulus regrade after stage 2 "
                        "passes; A0 = the baseline with no arm (pin it for comparisons with earlier runs)")
    r.add_argument("--router-k", type=int, default=8, help="brief 36: skills in the router's shortlist")
    r.add_argument("--design-plan", action="store_true",
                   help="plan before building: stage 1 lists the datapaths, and the timing plan maps each operation to a DSP slice, "
                        "block RAM, carry chain or LUTs and picks the pipeline depth (needs a delay model for the device family)")
    r.add_argument("--closure", choices=["on", "off"], default="off",
                   help="after the build, loop on timing, area and power, re-checking simulation after every change, until all hold "
                        "or the loop stalls (stage 6; tested with fakes only; default off)")
    r.add_argument("--coverage-loop", choices=["on", "off"], default="off",
                   help="brief 218: at V3, when only stimulus-owned checks fail (bins, cover properties, line, toggle, mutation survivors), run rounds "
                        "of coverage-directed stimulus inside the gate (the tests role is shown just the holes, the V3 evidence is rerun) until a "
                        "plateau (no hole closed in two rounds), convergence or the round limit; every round is recorded (default off: today's V3)")
    r.add_argument("--req-sva", choices=["on", "off"], default="off",
                   help="brief 218: once V2 passes, write an SVA property for each checkable requirement from its text and the port list, "
                        "read it back in English with a different model, compare in code, and prove or bounded-check it with a reachable "
                        "cover of its trigger; a proved property becomes evidence on the requirement's row (needs sby; default off)")
    r.add_argument("--readiness", choices=["on", "off"], default="off",
                   help="brief 227: stage 0 iterates until the requirements are ready, then freezes them. Each round: the mechanical checks, the requirements "
                        "reviewer, a probe set that two fresh readers answer from the requirements alone (a disagreement or a gap is a question), and, at "
                        "--requirements strict, a third reader's structured layer. Questions go to the oracle (--interview oracle) or to "
                        "requirements_answers.yaml; with nobody to answer, or at the round or call limit, the run stops with REQUIREMENTS_NEEDED.md "
                        "(exit status 3) and never guesses (default off)")
    r.add_argument("--readiness-rounds", type=int, default=4, help="brief 227: the stage-0 round limit (default 4)")
    r.add_argument("--readiness-calls", type=int, default=60, help="brief 227: the stage-0 budget of model calls (default 60)")
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
    for p in (r, sub.add_parser("resume", help=newcomer.COMMANDS["resume"][0], description=newcomer.COMMANDS["resume"][1],
                                epilog=newcomer.RESUME_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)):
        p.add_argument("--replies", type=Path, help="a JSON list of replies fed in order to the questions and reviews that pause the run")
        p.add_argument("--reply", help="one JSON reply to the question or review the run is paused on")
        p.add_argument("--replay", help="LLM replay fixture (no network)")
        p.add_argument("--record", help="record LLM calls to this fixture")
        p.add_argument("--deterministic", action="store_true",
                       help="brief 107: replay the recorded tape (level 2) when there is one, else run at temperature 0 and record one (level 1); "
                            "fails before the first call when neither is possible; never samples")
        p.add_argument("--tape", help="with --deterministic: the tape directory (default ~/.local/share/fpga_design_agent/tapes/<design name>)")
        p.add_argument("--record-tape", help="brief 107: record every model call to this tape directory (private; outside the repo or git-ignored)")
        p.add_argument("--replay-tape", help="brief 107: serve every model call from this tape directory (level 2); a missing call is an error")
        from agent.core import permissions as _perm
        p.add_argument("--permissions", choices=list(_perm.MODE_ORDER), metavar="MODE",
                       help="brief 222: what the run may do without asking: plan | ask | auto | full (default: the config file's mode, else auto). "
                            "Plan reads and plans only; Ask runs simulation itself and asks before every other gated action; Auto asks only before the board, "
                            "registers, instruments and a higher budget; Full also does those, inside the lab file's limits. Flash, boot images, eFUSE, BBRAM and keys are never allowed. See docs/agent.md")
        p.add_argument("--allow", action="append", default=[], choices=list(_perm.ACTION_NAMES), metavar="ACTION",
                       help="brief 222: allow one gated action whatever the mode says (repeatable; the actions are listed in docs/agent.md)")
        p.add_argument("--ask", action="append", default=[], choices=list(_perm.ACTION_NAMES), metavar="ACTION",
                       help="brief 222: ask before one gated action whatever the mode says (repeatable)")
        p.add_argument("--deny", action="append", default=[], choices=list(_perm.ACTION_NAMES), metavar="ACTION",
                       help="brief 222: deny one gated action whatever the mode says (repeatable); a run that needs it stops with the reason")
        p.add_argument("--ask-above-usd", type=float, metavar="N", help="brief 222: ask before spending model money past this run total in USD (default 1.00)")
    rs = sub._name_parser_map["resume"]
    rs.add_argument("run_id", help="a run id under runs/, or a design directory containing handover.yaml; a name that is not such a "
                                   "directory is taken as a run id")
    rs.add_argument("change", nargs="?", help="design resume: the change request, in plain words. Its class sets the entry stage (earliest match wins): "
                    "spec 0; area, latency, retarget, arch 1; language, mapping, rtl 2; fmax, power, constraints 3; timing 6; board 9. "
                    "A request that matches no class is a question (exit 2), not stage 0; documentation-only is never guessed (use --kind docs). "
                    "--dry-run shows the class, the stage and the matched words")
    rs.add_argument("--rewind", type=int, metavar="N", help="run resume: restore the end of stage N (files, .dcp, checkpoint; hash-checked) and continue there")
    rs.add_argument("--max-usd", type=float, help="cost cap for this resumed process (the meter starts at 0)")
    rs.add_argument("--kind", choices=sorted(__import__("agent.graph.pickup", fromlist=["x"]).STAGE_OF_KIND),
                    help="design resume: the change's class, instead of the keyword classifier (each class has a fixed entry stage; "
                         "`resume ... --dry-run` prints the class, the stage and the matched words)")
    rs.add_argument("--from-stage", type=int, help="design resume: enter at this stage, overriding the rule")
    rs.add_argument("--dry-run", action="store_true",
                    help="design resume only: report the freshness and the entry stage, then stop; needs no key, writes nothing, calls no model. "
                         "For a run id it does nothing (the run continues, with the key)")
    rs.add_argument("--scope", help="design resume of a managed project: the components or hierarchy paths this request may touch "
                                    "(comma separated; default: resolved from the change text, else every owned component)")
    rs.add_argument("--strategy-file", type=Path, help="design resume: the strategy.json `agent improve --choose` saved (the options offered and the choice go into the run record)")
    rs.add_argument("--stop-after", type=int, metavar="N", help="stop after stage N passes (stages count from 0; see `run --help`)")
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
    rs.add_argument("--budget-scale", type=float, help="brief 209b: multiplies every stage USD budget and the default run cap")
    rs.add_argument("--allow-fable", action="store_true", help="the owner's flag: permits Fable on a claude_code endpoint")
    rs.add_argument("--allow-model-change", action="store_true", help="resume a run although its model table hash has changed")
    from agent.graph.revise import add_parser as _revise_parser         # brief 159
    _revise_parser(sub)
    rvp = sub._name_parser_map["revise"]
    for act in rs._actions:                                             # the run options are the resume command's, shared
        if act.dest in ("max_usd", "board", "stop_after", "model", "harness", "cc_model", "cc_effort", "profile", "roles", "verif_level", "docs",
                        "models_file", "model_config", "allow_fable", "allow_model_change", "budget_scale"):
            rvp._add_action(act)
    for act in sub._name_parser_map["resume"]._actions:
        if act.dest in ("replies", "reply", "replay", "record", "deterministic", "tape", "record_tape", "replay_tape"):
            rvp._add_action(act)
    pp = sub.add_parser("propose", help="brief 194: read an input folder and write proposed_settings.yaml (board, part, clocks, I/O standards, PHYs, interfaces, "
                                        "profile), each value with its source. It is the interview's input (agent run --settings FILE); nothing is confirmed here")
    pp.add_argument("folder", type=Path)
    pp.add_argument("--board", help="a catalogue board to use when the folder does not name one")
    pp.add_argument("--out", type=Path, help="default: <folder>/proposed_settings.yaml")
    
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
    from agent.repro.cli import add_parser as _example_parser            # brief 195
    _example_parser(sub)
    sub.add_parser("doctor", help=newcomer.COMMANDS["doctor"][0], description=newcomer.COMMANDS["doctor"][1],
                   add_help=False)                      # dispatched in main() before this parser: listed here so --help shows it
    sub.add_parser("project", help=newcomer.COMMANDS["project"][0], add_help=False)
    sub.add_parser("ip", help="the IP library: search, rank, show, use (brief 150; plain Python, no model, no Vivado; needs the key)", add_help=False)   # dispatched in main()
    return ap


def _run_main(a, args: list[str], ap: argparse.ArgumentParser) -> int:
    """Everything after the access gate (or after an exemption): the parsed command line ``a`` runs."""
    from agent.graph.role_models import parse_roles
    from agent.graph.run import Config, build_graph, checkpointer_for, new_runtime
    if a.cmd in ("status", "ask", "request"):
        return live_cmd(a)
    if a.cmd == "example":
        from agent.repro.cli import main as example_main
        return example_main(a)
    if a.cmd == "models":
        return models_cmd(a, args)
    if a.cmd == "latency":
        from agent.graph.latency_loop import latency_cmd
        return latency_cmd(a)
    if a.cmd == "improve":
        from flow.options.cli import improve_cmd
        return improve_cmd(a, main)
    if a.cmd == "propose":
        from agent.graph import settings as _st
        try:
            out = _st.propose(a.folder, a.board)
        except _st.SettingsError as e:
            ap.error(str(e))
        dest = _st.write(a.folder, out, a.out)
        print(f"wrote {dest}: " + ", ".join(f"{k}={e['status']}" for k, e in out["settings"].items()))
        return 0
    if a.cmd == "review":
        return review_cmd(a)
    if a.cmd == "document":
        return document_cmd(a)
    if a.cmd == "revise":
        return revise_cmd(a)
    if a.cmd == "resume" and newcomer_is_design_resume(a.run_id):
        return pickup_cmd(a)
    replies = json.loads(a.replies.read_text()) if a.replies else []
    if a.reply:
        replies.insert(0, json.loads(a.reply))
    if a.cmd == "run":
        if a.interview == "oracle" and not a.hidden_spec:
            ap.error("--interview oracle needs --hidden-spec")
        name = a.name or a.spec.resolve().parent.name
        from agent.graph import profiles as _prof
        settings_doc = None
        if a.settings:                                        # brief 194: the proposals are the interview's input
            from agent.graph import settings as _st
            try:
                settings_doc = _st.apply_flags(_st.load_proposals(a.settings), a.board if any(x.startswith("--board") for x in args) else None, a.verif_profile)
            except (_st.SettingsError, OSError) as e:
                ap.error(str(e))
            sb = settings_doc["settings"]["board"]["value"]
            if sb and not any(x.startswith("--board") for x in args):
                a.board = sb
        if a.block_for_shell and not (ROOT / "boards" / a.board / "shell" / Path(a.block_for_shell).name).is_file():      # brief 235
            ap.error(f"--block-for-shell: boards/{a.board}/shell/{Path(a.block_for_shell).name} does not exist (this board has no supplied shell)")
        try:                                                  # brief 194: a bad profile or switch fails before anything runs
            vp = _prof.from_cli(a.verif_profile, a.verif_set, a.verif_level if any(x.startswith("--verif-level") for x in args) else None, a.spec_tests)
        except _prof.ProfileError as e:
            ap.error(str(e))
        cfg = Config(spec_md=a.spec, name=name, board=a.board, interview=a.interview, review=a.review, requirements=a.requirements or "",
                     verif_profile=vp["profile"], verif_sets={k: v["value"] for k, v in vp["overrides"].items()},
                     verif_ask=a.verif_profile is None and a.interview in ("on", "oracle"), settings_file=a.settings,
                     settings_flags=({k: v for k, v in (('board', a.board if any(x.startswith('--board') for x in args) else None), ('profile', a.verif_profile)) if v} or None),
                     model=a.model, hidden_spec=a.hidden_spec, stop_after=a.stop_after,
                     harness=a.harness, cc_model=a.cc_model, cc_effort=a.cc_effort,
                     verif_level=vp['cfg']['verif_level'], profile=a.profile, roles=parse_roles(a.roles),
                     no_shell=a.no_shell or task_no_shell(a.hidden_spec), block_shell=a.block_for_shell, data_dir=a.data_dir or task_data_dir(a.spec),
                     oracle=a.oracle, oracle_cc_model=a.oracle_cc_model, spec_tests=vp['cfg']['spec_tests'],
                     spectest_model=a.spectest_model, spectest_max_loops=a.spectest_max_loops,
                     skill_routing=a.skill_routing, router_model=a.router_model, router_k=a.router_k,
                     harness_arms=a.harness_arm, hdl=a.hdl,
                     design_plan=a.design_plan, closure=a.closure, docs=a.docs,          # closure loop; brief 68 C
                     permissions=permission_spec(a, name, ap),                          # brief 222
                     coverage_loop=a.coverage_loop, req_sva=a.req_sva,                   # brief 218
                     readiness=a.readiness, readiness_limits={"max_rounds": a.readiness_rounds, "max_calls": a.readiness_calls},   # brief 227
                     **{**model_kwargs(a, args), "models_file": a.models_file or project_models_file(a.spec)})
        cfg.role_models()                                     # fail early on an unknown profile, role or forbidden model
        if a.max_usd is not None:
            cfg.run_limits["usd"] = a.max_usd
        from agent.core.permissions import NeverRefused
        from agent.models.tape import DeterminismError
        try:
            tspec = tape_spec_from(a, cfg)
            rt = new_runtime(cfg, None, replay=a.replay, record=a.record, tape_spec=tspec)
        except DeterminismError as e:
            print(f"deterministic: {e}", file=sys.stderr)
            return 2
        except NeverRefused as e:                             # brief 222: a cost cap above the hard cap, never allowed in any mode
            print(f"run: {e}", file=sys.stderr)
            return 2
        graph = build_graph(checkpointer_for(rt.run_dir), routing=cfg.skill_routing != "off")
        return drive_exit(_drive(graph, rt, {"configurable": {"thread_id": rt.run_id}},
                                 {"run_id": rt.run_id, "stage": 0, "visits": {}, "history": []}, replies))
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
    from agent.core.permissions import NeverRefused
    from agent.models.tape import DeterminismError
    try:
        tspec = tape_spec_from(a, cfg)
        rt = new_runtime(cfg, None, run_id=a.run_id, replay=a.replay, record=a.record, tape_spec=tspec)
    except DeterminismError as e:
        print(f"deterministic: {e}", file=sys.stderr)
        return 2
    except NeverRefused as e:                                 # brief 222: a cost cap above the hard cap
        print(f"resume: {e}", file=sys.stderr)
        return 2
    stop_code = resume_permissions(a, rt, c)                  # brief 222: flags that change the mode; a higher cost cap needs raise_budget
    if stop_code is not None:
        return stop_code
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
    return drive_exit(_drive(graph, rt, lg, first, replies))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["project"]:                      # brief 27B: the project layer (project/), not part of the agent graph
        from project.cli import main as project_main
        return project_main(args[1:])
    from agent import newcomer
    if args[:1] == ["ip"]:                           # brief 150: the IP-library retriever (plain Python: no model, no Vivado); its own --help prints before the gate
        from agent.ip_cmd import main as ip_main
        if not (set(args[1:2]) & {"-h", "--help"}):
            from agent.access import require_or_exit
            require_or_exit("python -m agent ip")
        return ip_main(args[1:])
    if args[:1] == ["doctor"]:                       # brief 157: reads no private file without the key; never prints the key
        return newcomer.doctor_main(args[1:])
    try:
        ap = build_parser()
        a = ap.parse_args(args)                      # --help and usage errors end here, before the gate: they print text only
    except ImportError as e:                         # an extra is not installed: help still answers; anything else is gated first
        if not newcomer.is_missing_package(e):
            raise                                    # a first-party import error is a bug: keep its traceback
        return newcomer.without_extras(args, e)
    from agent.access import require_or_exit      # brief 94: run, resume and document all start here
    why = newcomer.ungated(a)                        # brief 157: the only commands that run without a key, each with its reason
    if why is None:
        require_or_exit("python -m agent")
    try:
        return _run_main(a, args, ap)
    except ImportError as e:
        if not newcomer.is_missing_package(e):
            raise
        return newcomer.missing_extra(a, e)


if __name__ == "__main__":
    sys.exit(main())
