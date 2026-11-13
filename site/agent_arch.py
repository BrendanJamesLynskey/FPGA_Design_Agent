"""Data for agent.html (brief 43): the agent's own structure, read from the code and the run records.

    from agent_arch import build; build(replay)   # called by site/export.py -> site/data/agent_graph.json

- ``graph``: the top-level LangGraph, compiled from ``agent.graph.run.build_graph`` and exported with ``get_graph()``.
- ``inner``: one Deep Agents role agent as ``agent.graph.run`` builds it (``create_deep_agent`` with the ``fda`` harness
  profile and the agent's own chat model over a fake client that is never sent anywhere): its compiled graph and the
  built-in tools it is offered.
- ``stages``: ``agent.graph.stages.MACHINE`` (gates, repair targets, limits, visit limits) and, per stage, the roles
  ``node_work`` runs and the tools ``effective_tools`` gives each.
- ``roles``: ``agent.graph.roles`` (what each role may read and write).
- ``runs``: which harness and model each committed run record used.
- ``replays``: two recorded runs, visit by visit, for the page's player.

Plain words for nodes, edges and gates are written here; site/tests/test_site.py fails if the code has a node, edge or
gate that has no words here (or the other way round), so a change to the graph cannot go undrawn.
Needs the ``graph`` extra (langgraph, deepagents); the site CI job installs it.
"""
from __future__ import annotations

import glob
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NODE_WORDS = {
    "__start__": ("start", "A run begins at the interview."),
    "work": ("work", "The stage's role agents act: each writes only the files its role owns."),
    "gate": ("gate", "The flow's own checks run: lint, simulation, Vivado reports, the stage gates. No model decides."),
    "review": ("review", "A snapshot of the design is taken; a person may approve, edit or rewind. Always pauses before the board."),
    "advance": ("advance", "Code picks the next stage from the gate result: the next stage, or the stage that owns the failure."),
    "document": ("document", "The Designer writes the handover's prose; code fills every number from the run's records and "
                             "renders README.md and AGENT.md. The DOC gate must pass for the run to be signed off."),
    "__end__": ("end", "The run stops: every stage passed, or a limit was reached."),
}
EDGE_WORDS = {
    ("__start__", "work"): "spec.md",
    ("work", "gate"): "files written",
    ("gate", "review"): "gate JSON",
    ("review", "advance"): "snapshot, approval",
    ("advance", "work"): "next stage, or repair",
    ("advance", "document"): "done, or give up",
    ("document", "__end__"): "handover, DOC gate",
}
INNER_WORDS = {
    "__start__": "the role's prompt and files", "PatchToolCallsMiddleware.before_agent": "tidy unanswered tool calls",
    "model": "model call", "tools": "tool calls", "_ParentNotifierMiddleware.after_agent": "notify a parent (unused here)",
    "__end__": "back to the controller",
}
STAGE_WORDS = ["Interview", "Plan", "RTL and tests", "Constraints", "Synthesis", "Implementation", "Timing closure",
               "Power closure", "Design-rule closure", "Board and debug"]
GATE_WORDS = {
    "spec_signed": "spec signed off, no open questions",
    "arch_note": "architecture note written",
    "arch_yaml": "architecture file valid",
    "inventory": "pins and clocks match the board",
    "arch_approved": "architecture approved",
    "lint": "lint clean",
    "model_contract": "golden model keeps its contract",
    "simulate": "tests pass against the model",
    "standards_rtl": "design standards on the RTL",
    "verif_v3": "verification V0 to V3",
    "stage_rtl": "RTL methodology checks",
    "constraints_post_synth": "every timing endpoint constrained",
    "stage_post_synth": "post-synthesis gates",
    "standards_post_synth": "design standards on the netlist",
    "stage_post_place": "post-place gates",
    "stage_post_route": "post-route gates",
    "timing": "setup and hold met",
    "power": "power and junction temperature",
    "drc": "DRC, CDC and methodology clean",
    "bitstream_base": "bitstream built",
    "bitstream_ila": "debug bitstream built",
    "bringup_ready": "bring-up files ready",
    "bringup": "board tests pass",
    "signoff": "every requirement has evidence",
}
#: which roles node_work runs in each stage (agent/graph/run.py node_work: stage 0 clarify; stage 2 model, tests, rtl;
#: stage 9 rtl then tests for the bring-up files; every other stage rtl). Checked against the recorded turn traces.
ROLE_STAGES = {0: ["clarify"], 2: ["model", "tests", "rtl"], 9: ["rtl", "tests"]}
ROLE_WORDS = {
    "clarify": ("Clarifier", "Turns the plain-English request into a structured spec, asking about what it leaves open."),
    "model": ("Modeller", "Writes a short Python reference model of the design from the spec alone. Blind to the RTL: never sees it."),
    "tests": ("Verifier", "Writes the tests and the test plan from the spec and the model. Never sees the RTL. Its own tests never decide a result; the hidden tests do."),
    "rtl": ("Designer", "Writes the architecture, SystemVerilog, constraints and probes, and does every repair. Vivado implementation is run by the deterministic flow, not by this role."),
}
TOOL_GROUPS = [
    ("Files", ["read_file", "write_file", "list_files"]),
    ("Knowledge", ["search_docs", "load_skill"]),
    ("Verification", ["lint", "simulate", "formal", "spec_items"]),
    ("Vivado", ["board_constraints", "check_constraints", "build", "gates", "report"]),
    ("Board", ["program", "bringup"]),
]
TOOL_WORDS = {
    "read_file": "read a file in the design", "write_file": "write a file the role owns", "list_files": "list the design",
    "search_docs": "search the frozen documents", "load_skill": "load know-how from the bank",
    "lint": "Verilator lint", "simulate": "cocotb tests on a simulator", "formal": "SymbiYosys proofs",
    "spec_items": "the spec items to trace", "board_constraints": "pins from the board file",
    "check_constraints": "check the XDC", "build": "run Vivado to a stage", "gates": "parse reports into gates",
    "report": "read a Vivado report", "program": "program the board (harness only)", "bringup": "board tests (harness only)",
}
#: brief 42's experimental arms, as variants of the pipeline. No arm has a result yet.
ARMS = [
    {"id": "A1", "name": "Skill router", "adds": "a step that shortlists skills before each role, which then loads them on demand",
     "at": "before work", "status": "not yet measured"},
    {"id": "A2", "name": "Independent spec reviewer", "adds": "a second agent, on another model, that challenges the signed-off spec before any RTL",
     "at": "after the interview", "status": "not yet measured"},
    {"id": "A3", "name": "Best of N", "adds": "several RTL candidates in parallel; the agent's own gates pick one (hidden tests never)",
     "at": "the Designer", "status": "not yet measured"},
    {"id": "A4", "name": "Plan and decompose", "adds": "a split into modules with contracts, built in parallel and then integrated",
     "at": "the plan", "status": "not yet measured"},
    {"id": "A5", "name": "Retrieve, then adapt", "adds": "a search for the closest verified component, which is adapted instead of writing from nothing",
     "at": "the Designer", "status": "not yet measured"},
    {"id": "A6", "name": "Constraints critic", "adds": "a narrow agent that reviews timing exceptions against known rules",
     "at": "the constraints stage", "status": "not yet measured"},
]

#: brief 47: plain words for each middleware in a role agent's stack, in the stack's order (a test fails on a new one).
MIDDLEWARE_WORDS = {
    "FilesystemMiddleware": "the built-in file tools on the jailed folder; moves a tool result of {evict_tool_result_chars:,} characters or more to a file",
    "_ParentNotifierMiddleware": "wakes a parent agent that started this one in the background; does nothing here",
    "SummarizationMiddleware": "summarises older turns once the transcript reaches about {summarise_trigger_tokens:,} tokens, keeping the last {summarise_keep_messages} messages; before that, cuts file contents the model wrote (over {truncate_args_over_chars:,} characters) out of all but the last {truncate_args_keep_messages} messages",
    "PatchToolCallsMiddleware": "answers any tool call left without a result, so the transcript stays valid",
    "AnthropicPromptCachingMiddleware": "prompt caching, for Anthropic chat models only; other models pass straight through",
    "UnsupportedContentMiddleware": "replaces content the model cannot take, such as images",
}
#: brief 42's harness arms (addendum, 2026-11-11). Each `evidence` number must occur in its `source` file (checked in build).
HARNESS_ARMS = [
    {"id": "H1", "name": "Context management", "source": "results/36_skill_routing/e2e.md",
     "change": "Large tool results, such as Vivado reports and simulation logs, go to a file in the jail and the model gets a head, a tail and the path; older turns are summarised much earlier.",
     "evidence": "Token totals are dominated by long repair visits: one 80-turn visit of the Designer used 6.6 M tokens."},
    {"id": "H2", "name": "Hang protection", "source": "results/24_fsm/drills/run_b1.meta.json",
     "change": "A per-test simulation limit from the test's own simulated-time budget, a result that says where a test hung, and a check that refuses tests with unbounded waits before they run.",
     "evidence": "In one drill run three simulate calls each ran to the 1800 s limit on the agent's own tests, which waited on conditions that never came."},
    {"id": "H3", "name": "Diagnose before repair", "source": None,
     "change": "Before each repair visit the role writes a short hypothesis, its evidence and the planned change; the repair visit receives it.",
     "evidence": "Repair visits that edit without stating what they think is wrong."},
    {"id": "H4", "name": "Budget and stall rule", "source": None,
     "change": "A token budget per stage; the same gate failing the same way three times sends the stage back to its plan instead of another edit.",
     "evidence": "Repair loops whose cost has no limit but the visit count."},
    {"id": "H5", "name": "Prompts and tool descriptions", "source": "results/36_skill_routing/e2e.md",
     "change": "Stage prompts aligned with the skill shortlist; every tool description says when to use it and when not to.",
     "evidence": "In the skill-routing runs the roles hardly used the new skill tools and kept loading whole sections."},
    {"id": "H6", "name": "Report reader", "source": None,
     "change": "A narrow, read-only helper agent reads a Vivado report and returns a structured finding instead of the raw text.",
     "evidence": "Raw reports in the main transcript."},
    {"id": "H7", "name": "Prompt caching", "source": None,
     "change": "Prompt caching on the OpenRouter models that support it.",
     "evidence": "The caching in the stack today acts on Anthropic chat models only, and every turn resends the whole prompt."},
    {"id": "H8", "name": "To-do list", "source": None,
     "change": "A to-do list tool for the Designer.",
     "evidence": "Planning on long stages; the role agents are offered no to-do tool today."},
    {"id": "H9", "name": "Typed digests", "source": None,
     "change": "A large build, gates, simulation or lint result is replaced by a short typed digest made by code from the gate parsers, plus the path of the full result.",
     "evidence": "Raw logs and reports fill the transcript that every turn resends."},
]
#: brief 42 round 1 (results/42_workflows/analysis.md, written by analyze.py): the paired table is read from that file.
HARNESS_RESULTS = "results/42_workflows/analysis.md"
#: each arm's pre-registered primary metrics (results/42_workflows/prereg.md): H2 is judged on wall time, the others on tokens and cost
PRIMARY = {"H2": ("wall_s",), "H1": ("tokens", "cost_usd"), "H9": ("tokens", "cost_usd")}
#: fixes already made from harness findings, each with its evidence (repository paths and the pull request).
HARNESS_FIXES = [
    {"name": "Whole skills from load_skill", "pr": 115, "files": ["agent/core/tools.py", "agent/tests/test_36_skill_routing.py"],
     "text": "When a role loaded several skills at once, the tool layer's output limit cut the middle out of them without saying so. "
             "load_skill now returns whole skills up to the limit and names the ones it held back, so the role can load each by name."},
    {"name": "The debug core's own timing exceptions", "pr": 120, "files": ["flow/exceptions_check.py", "flow/tests/test_45_ila_exceptions.py"],
     "text": "The exceptions gate failed every build with a logic analyser in it, because the analyser core brings timing exceptions "
             "that Vivado ignores. The gate now reports those as information and still fails on the design's own."},
    {"name": "A build cache for Vivado", "pr": 118, "files": ["flow/build_cache.py", "results/33_vivado_speed_2026_1/summary.json"],
     "text": "A repeated build of an unchanged design now comes from a cache, and a later stage resumes from the last checkpoint. "
             "One agent run's build sequence on the c10 task took {with_cache_s} s instead of a modelled {without_cache_model_s} s, with the same result."},
]


def _imports():
    sys.path.insert(0, str(ROOT))
    import agent.core.tools  # noqa: F401  (registers the tools)
    from agent.core.registry import TOOLS
    from agent.graph import roles as roles_mod
    from agent.graph import run
    from agent.graph.role_models import PROFILES
    from agent.graph.stages import MACHINE, RUN_LIMITS, visit_limit
    return TOOLS, roles_mod, run, PROFILES, MACHINE, RUN_LIMITS, visit_limit


def graph_from_code():
    """The top-level graph as the code compiles it: nodes in insertion order, edges sorted."""
    _, _, run, *_ = _imports()
    g = run.build_graph(None).get_graph()
    nodes = list(g.nodes)
    edges = sorted({(e.source, e.target, bool(e.conditional), e.data) for e in g.edges})
    return nodes, edges


def inner_from_code():
    """One Deep Agents role agent, built as _run_subagent builds it, with a client that answers 'done' locally."""
    _, _, run, *_ = _imports()
    from deepagents import HarnessProfile, create_deep_agent, register_harness_profile
    from deepagents.backends import StateBackend
    from deepagents.profiles.harness.harness_profiles import GeneralPurposeSubagentProfile

    from agent.graph.llm import Meter, Reply, chat_model
    import deepagents.graph as dg
    register_harness_profile("fda", HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)))
    seen, stack = {}, {}

    def client(msgs, tools=None):
        seen["tools"] = [t["function"]["name"] for t in (tools or [])]
        seen["msgs"] = [(m.get("role"), m.get("content")) for m in msgs if isinstance(m, dict)]
        return Reply(text="done", tool_calls=[])

    real = dg.create_agent

    def spy(*a, **k):                      # brief 47: the whole middleware stack, not only the ones that are graph nodes
        stack["mw"] = list(k.get("middleware") or [])
        return real(*a, **k)
    dg.create_agent = spy
    try:
        a = create_deep_agent(model=chat_model(client, Meter(run_limits={"turns": 3}), []), tools=[], system_prompt="ROLE PROMPT",
                              backend=StateBackend())
    finally:
        dg.create_agent = real
    a.invoke({"messages": [{"role": "user", "content": "x"}]})
    g = a.get_graph()
    return {"nodes": list(g.nodes), "edges": sorted({(e.source, e.target, bool(e.conditional)) for e in g.edges}),
            "builtin_tools": seen["tools"], "todo_tool": "write_todos" in seen["tools"], "subagent_tool": "task" in seen["tools"],
            "middleware": [m.name for m in stack["mw"]],
            "system_prompt_only_ours": [r for r, c in seen["msgs"] if r == "system"] == ["system"]
                                       and dict(seen["msgs"])["system"] == "ROLE PROMPT"}


def harness_settings():
    """The settings that decide how a Deep Agents role agent handles its context, read from the libraries and our code."""
    TOOLS, _, run, *_ = _imports()
    import deepagents.graph as dg
    from deepagents.backends import StateBackend
    from deepagents.middleware import filesystem as fsm
    from deepagents.middleware.summarization import create_summarization_middleware

    from agent.core import tools as core_tools
    from agent.core.registry import MAX_OUTPUT
    from agent.graph.llm import Meter, Reply, chat_model
    model = chat_model(lambda m, tools=None: Reply(text="", tool_calls=[]), Meter(run_limits={"turns": 1}), [])
    sm = create_summarization_middleware(model, StateBackend())   # as create_deep_agent builds it for this model
    trig, keep = sm._lc_helper.trigger, sm._lc_helper.keep
    fs = fsm.FilesystemMiddleware(backend=StateBackend())
    assert dg.create_summarization_middleware is create_summarization_middleware
    rec = [int(x) for x in re.findall(r'"recursion_limit": (\d+)', (ROOT / "agent/graph/run.py").read_text())]
    assert len(rec) == 2                                 # rtl first (the real folder), then the other roles
    assert trig[0] == "tokens" and keep[0] == "messages" and sm._truncate_args_trigger[0] == "messages"
    return {"summarise_trigger_tokens": trig[1], "summarise_keep_messages": keep[1],
            "truncate_args_after_messages": sm._truncate_args_trigger[1], "truncate_args_keep_messages": sm._truncate_args_keep[1],
            "truncate_args_over_chars": sm._max_arg_length,
            "model_profile": model.profile is not None,
            "evict_tool_result_chars": fsm.NUM_CHARS_PER_TOKEN * fs._tool_token_limit_before_evict,
            "registry_clip_chars": MAX_OUTPUT,
            "recursion_limit": {"rtl": rec[0], "others": rec[1]},
            "sim_timeout_s": {"default": core_tools.SIM_TIMEOUT_DEFAULT, "min": core_tools.SIM_TIMEOUT_MIN, "max": core_tools.SIM_TIMEOUT_MAX}}


def versions():
    py = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["optional-dependencies"]
    pins = {}
    for spec in py["graph"] + py["agent"]:
        m = re.match(r"([\w-]+)==([\w.]+)", spec)
        if m:
            pins[m.group(1)] = m.group(2)
    return pins


def _harness_of(r):
    if r.get("harness"):
        return r["harness"]
    hs = sorted({v["harness"] for v in (r.get("role_models") or {}).values()})
    if hs:
        return hs[0] if len(hs) == 1 else "mixed"
    return "deepagents" if "/" in str(r.get("model", "")) else None


def _models_of(r):
    ms = sorted({v["model"] for v in (r.get("role_models") or {}).values()})
    return ms or ([r["model"]] if r.get("model") else [])


def runs_table():
    """Which harness and models each committed run record used: the development tasks and the T1 agent smokes."""
    rows = {}
    for p in sorted(glob.glob(str(ROOT / "results/course/*/run_*.json"))):
        r = json.loads(Path(p).read_text())
        if r.get("split") != "dev":
            continue
        k = ("Development tasks", r["harness"], ", ".join(_models_of(r)))
        rows.setdefault(k, []).append(f'{r["task"]} run {r["run"]}')
    for p in sorted(glob.glob(str(ROOT / "results/f2/agent_*.json"))):
        name = Path(p).stem
        if name.endswith(("_summary", "_bringup", "_resume")):
            continue                      # the same run as another file, or a step of one
        r = json.loads(Path(p).read_text())
        h = _harness_of(r)
        if not h:
            continue
        k = ("T1 smoke runs", h, ", ".join(_models_of(r)))
        rows.setdefault(k, []).append(name)
    out = [{"set": k[0], "harness": k[1], "models": k[2], "records": len(v), "files": v} for k, v in rows.items()]
    return sorted(out, key=lambda x: (x["set"], x["harness"], x["models"]))


def _stage_tools(run, n, role):
    return list(run.effective_tools(role, n, "V3"))


def stages():
    TOOLS, roles_mod, run, PROFILES, MACHINE, RUN_LIMITS, visit_limit = _imports()
    out = []
    for st in MACHINE:
        roles = ROLE_STAGES.get(st.n, ["rtl"])
        out.append({"n": st.n, "name": st.name, "label": STAGE_WORDS[st.n], "ultrafast": st.n >= 1,
                    "gates": [{"id": g, "words": GATE_WORDS[g]} for g in st.gates], "loops_to": list(st.loops_to),
                    "limits": {k: st.limits[k] for k in ("turns", "seconds", "usd")}, "visits": visit_limit(st.n, RUN_LIMITS),
                    "roles": roles, "tools": {r: _stage_tools(run, st.n, r) for r in roles},
                    "stage_tools": list(st.tools)})
    return out, dict(RUN_LIMITS)


def roles():
    _, roles_mod, *_ = _imports()
    return [{"id": r, "label": ROLE_WORDS[r][0], "what": ROLE_WORDS[r][1], "reads": list(roles_mod.ROLES[r]["read"]),
             "writes": list(roles_mod.ROLES[r]["write"]),
             "backend": "the real design folder, every path checked by the role's jail" if r == "rtl"
             else "an in-memory folder seeded with only the role's inputs; outputs copied in through the jail"}
            for r in ("clarify", "model", "tests", "rtl")]


def _tools_list():
    TOOLS, _, run, *_ = _imports()
    out = []
    for grp, names in TOOL_GROUPS:
        for n in names:
            assert n in TOOLS, n
            out.append({"name": n, "group": grp, "what": TOOL_WORDS[n], "model_may_call": n in run.FLOW_TOOLS})
    return out


def _low(label):
    """The role names are proper nouns ('Verifier', 'Designer'): kept as they are inside a sentence."""
    return label


def _plain_fail(text):
    """'lint (...) then simulate (...); owner: rtl role ...' -> the failing checks and the owner, in words."""
    checks = [w for w in ("lint", "simulate", "gates", "formal") if re.search(rf"\b{w}\b \(", text)]
    owner = re.search(r"owner: (\w+) role", text)
    words = {"lint": "lint", "simulate": "the tests against the model", "gates": "the stage gates", "formal": "formal"}
    return (" and ".join(words[c] for c in checks) or "the stage gates") + " failed" + \
        (f"; the {_low(ROLE_WORDS[owner.group(1)][0])} owns the fix" if owner else "")


def replay_pass(replay, MACHINE, run):
    """Replay A: the c14 int8 dot-product development run 5 (replay.json and its run record)."""
    r = json.loads((ROOT / "results/course/c14_int8_dot_requant/run_5.json").read_text())
    steps = replay["steps"]
    visits = []
    for i, s in enumerate(steps):
        n = s["stage_no"]
        last_of_stage = s["visit"] == s["visits"]
        roles = [{"role": x, "tools": {}, "offered": _stage_tools(run, n, x)} for x in ROLE_STAGES.get(n, ["rtl"])]
        if i == len(steps) - 1:
            gate = {"pass": None, "text": s["fact"]}
            nxt = {"kind": "end", "to": None, "text": "paused before the board, as no board was attached"}
        elif last_of_stage:
            gate = {"pass": True, "text": s["fact"]}
            nxt = {"kind": "next", "to": steps[i + 1]["stage_no"], "text": "stage passed"}
        else:
            gate = {"pass": False, "text": f"Not passed on this visit; the stage was entered {s['visits']} times in all."}
            nxt = {"kind": "repair", "to": n, "text": "visit the stage again"}
        visits.append({"stage": n, "visit": s["visit"], "visits": s["visits"], "roles": roles, "gate": gate, "next": nxt,
                       "review": "snapshot taken; approved automatically (review off)"})
    return {"id": "pass", "title": "A run that passed", "task": replay["task"], "run": replay["run"], "date": replay["date"],
            "harness": r["harness"], "model": r["model"], "claude_code": r["claude_code_version"], "oracle": r["oracle"],
            "hidden": replay["hidden"], "turns": r["agent_turns"], "wall_h": r["wall_h_total"],
            "tool_totals": {k: v for k, v in r["tool_runs"].items() if k in dict(TOOL_WORDS) and v},
            "order_recorded": False, "per_visit_tools": False, "visits": visits,
            "source": "results/course/c14_int8_dot_requant/run_5.json"}


def replay_giveup(MACHINE, run):
    """Replay B: a Deep Agents T1 run with the visit order and each role's tool calls recorded, which gave up at stage 2."""
    src = "results/f2/agent_luna_05g_run1.json"
    r = json.loads((ROOT / src).read_text())
    order, count, visits = r["stages_visited"], {}, []
    for i, n in enumerate(order):
        count[n] = count.get(n, 0) + 1
        v = count[n]
        name = MACHINE[n].name
        tr = [t for t in r["turn_trace"] if t["stage"] == name and t["visit"] == v]
        roles = [{"role": t["role"], "tools": t["tools"], "refused": t["refused"], "turns": t["turns"],
                  "allowed": t["turns_allowed"], "ended": t["ended"], "repair": t["repair"], "files": t["files_written"],
                  "offered": _stage_tools(run, n, t["role"])} for t in tr]
        nxt_n = order[i + 1] if i + 1 < len(order) else None
        if not tr:                                  # node_work stopped before any role ran: the visit limit
            gate = {"pass": None, "text": "No work: the stage had already used its visits."}
            nxt = {"kind": "end", "to": None, "text": "give up: " + r["stop"]}
        elif nxt_n is not None and nxt_n > n:
            q = r["questions"]
            gate = {"pass": True, "text": (f"Spec signed off: {q['asked']} questions asked, {q['answered']} answered by the "
                                           f"oracle, {q['defaulted']} left at their defaults." if n == 0 else "Stage gates pass.")}
            nxt = {"kind": "next", "to": nxt_n, "text": "stage passed"}
        else:
            nxt_roles = [t["role"] for t in r["turn_trace"] if t["stage"] == name and t["visit"] == v + 1 and t["repair"]]
            last = not any(t["stage"] == name and t["visit"] == v + 1 for t in r["turn_trace"])
            gate = {"pass": False, "text": (_plain_fail(r["first_failing_gate_last_visit"]) + "." if last else
                                            "Stage gates failed; the next visit repairs the " +
                                            " and the ".join(_low(ROLE_WORDS[x][0]) + "'s" for x in nxt_roles) + " work.")}
            nxt = {"kind": "repair", "to": nxt_n, "text": "repair"}
        visits.append({"stage": n, "visit": v, "visits": sum(1 for x in order if x == n), "roles": roles, "gate": gate,
                       "next": nxt, "review": "snapshot taken; approved automatically (review off)"})
    rm = r["role_models"]
    return {"id": "giveup", "title": "A run that gave up", "task": "t1_dimmer_counter", "run": r["run_id"],
            "date": f'{r["run_id"][:4]}-{r["run_id"][4:6]}-{r["run_id"][6:8]}',
            "harness": _harness_of(r), "model": ", ".join(sorted({v["model"] for v in rm.values()})),
            "oracle": r["oracle_model"], "turns": r["turns"], "wall_h": round(r["wall_s"] / 3600, 2),
            "usd": r["openrouter_cost_usd_key_usage"], "result": r["result"],
            "order_recorded": True, "per_visit_tools": True, "visits": visits, "source": src}


def bank(skills):
    """The knowledge bank as the site's skills.json has it at the pin: skills per layer (the first path part)."""
    by = {}
    for x in skills["skills"]:
        by[x["unit"].split("/")[0]] = by.get(x["unit"].split("/")[0], 0) + 1
    order = ["techniques", "functions", "vendor", "family", "device", "board", "procedures"]
    return {"pin": skills["pin"], "skills": len(skills["skills"]), "units": len({x["unit"] for x in skills["skills"]}),
            "layers": [{"layer": k, "skills": by[k]} for k in order if k in by]}


def build(replay, skills):
    TOOLS, roles_mod, run, PROFILES, MACHINE, RUN_LIMITS, visit_limit = _imports()
    nodes, edges = graph_from_code()
    st, limits = stages()
    cfg = run.Config(spec_md=Path("spec.md"), name="x")
    return {
        "versions": versions(),
        "graph": {"nodes": [{"id": n, "label": NODE_WORDS[n][0], "what": NODE_WORDS[n][1]} for n in nodes],
                  "edges": [{"source": s, "target": t, "conditional": c, "key": k, "label": EDGE_WORDS[(s, t)]}
                            for s, t, c, k in edges]},
        "inner": (inner := inner_from_code()),
        "stages": st, "run_limits": limits,
        "roles": roles(), "tools": _tools_list(),
        "defaults": {"harness": cfg.harness, "model": cfg.model, "cc_model": cfg.cc_model,
                     "profiles": {k: v for k, v in PROFILES.items()}},
        "runs": runs_table(),
        "replays": [replay_pass(replay, MACHINE, run), replay_giveup(MACHINE, run)],
        "arms": ARMS,
        "bank": bank(skills),
        "inner_words": {n: INNER_WORDS[n] for n in inner["nodes"]},
        "harness": harness(inner),
    }


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def harness_results():
    """Brief 42 round 1, read from analysis.md (written by analyze.py): per arm, the paired change against the baseline
    A0 for tokens, cost and wall time (median, 95 % bootstrap interval, both also as a percentage of A0's median), the
    pass counts, and the verdict under both readings of the pre-registered rule. Nothing here is computed but the
    percentages of the interval ends."""
    src = (ROOT / HARNESS_RESULTS).read_text()
    lines = src.splitlines()
    env = (ROOT / HARNESS_RESULTS).with_name("environment.txt").read_text()
    head = {"n_runs": int(re.search(r"Valid runs: (\d+)", src).group(1)), "blocks": int(re.search(r"(\d+) of \d+ started", src).group(1)),
            "source": HARNESS_RESULTS, "model": re.search(r"^model: (\S+)", env, re.M).group(1)}
    totals, paired, verdict, sens = {}, {}, {}, {}
    for l in lines:
        c = _cells(l) if l.startswith("|") else []
        if len(c) == 10 and re.fullmatch(r"A0|H\d", c[0]) and c[1].isdigit():
            totals[c[0]] = {"runs": int(c[1]), "hidden_passes": int(c[2]), "cost_usd": float(c[7])}
        elif len(c) == 10 and re.fullmatch(r"H\d", c[0]) and c[1] in ("tokens", "cost_usd", "wall_s"):
            lo, hi = (float(x) for x in c[6].strip("[]").split(","))
            base = float(c[3])
            paired.setdefault(c[0], {})[c[1]] = {"n": int(c[2]), "a0": base, "diff": float(c[4]), "rel_pct": float(c[5].rstrip(" %")),
                                                "lo": lo, "hi": hi, "lo_pct": round(100 * lo / base, 1), "hi_pct": round(100 * hi / base, 1),
                                                "excludes_0": c[7] == "yes"}
        elif len(c) == 6 and re.fullmatch(r"H\d", c[0]) and c[4] in ("yes", "no"):     # wall time without the censored blocks
            sens[c[0]] = {"n": int(c[1]), "diff": float(c[2]), "excludes_0": c[4] == "yes"}
        elif len(c) == 8 and re.fullmatch(r"H\d", c[0]) and c[6] in ("yes", "no"):
            verdict[c[0]] = {"reading_t": c[6] == "yes", "reading_c": c[7] == "yes"}
    words = {"tokens": "tokens", "cost_usd": "cost", "wall_s": "wall time"}
    out = {}
    for arm, m in paired.items():
        parts = []
        for k in ("cost_usd", "tokens", "wall_s"):
            x = m[k]
            lh = lambda p: f'{abs(p):g} % {"lower" if p < 0 else "higher"}'
            t = f'{words[k]} {lh(x["rel_pct"])} (95 % interval {lh(x["lo_pct"])} to {lh(x["hi_pct"])})'
            if k == "wall_s" and x["excludes_0"] and not sens[arm]["excludes_0"]:
                t += ", but the interval includes 0 once the blocks with a run stopped by the time limit are left out"
            parts.append(t)
        v = verdict[arm]
        def why(k):        # one primary metric against the rule: at least 30 % lower AND an interval that excludes 0
            x = m[k]
            if x["rel_pct"] <= -30 and x["excludes_0"]:
                return f'{words[k]} meets it ({abs(x["rel_pct"]):g} % lower, interval excludes 0)'
            if x["rel_pct"] <= -30:
                return f'{words[k]} fell {abs(x["rel_pct"]):g} % but the interval includes 0'
            if x["excludes_0"]:
                return f'{words[k]} fell {abs(x["rel_pct"]):g} %, under the 30 % bar'
            return f'{words[k]} changed by {x["rel_pct"]:+g} % with an interval that includes 0'
        prim = PRIMARY.get(arm, ("tokens", "cost_usd"))
        if v["reading_c"] and not v["reading_t"]:
            rule = ("Not adopted: " + "; ".join(why(k) for k in prim) +
                    "; the pre-registered rule did not say whether cost alone counts")
        elif v["reading_t"]:
            rule = "Meets the adopt rule"
        else:
            rule = "Not adopted against the rule (at least 30 % lower with an interval that excludes 0): " + "; ".join(why(k) for k in prim)
            if arm == "H2":
                rule += "; hangs, its other primary measure, were too rare in this round to compare"
        status = ("; ".join(parts).capitalize() + f'. Hidden-test passes {totals[arm]["hidden_passes"]} of {totals[arm]["runs"]} '
                  f'(baseline {totals["A0"]["hidden_passes"]} of {totals["A0"]["runs"]}). ' + rule + ".")
        out[arm] = {"status": status, "paired": m, "verdict": v, "wall_without_censored": sens[arm],
                    "hidden_passes": totals[arm]["hidden_passes"], "runs": totals[arm]["runs"]}
    if out:
        out["_run"] = {**head, "a0_hidden_passes": totals["A0"]["hidden_passes"], "a0_runs": totals["A0"]["runs"]}
    return out


def harness(inner):
    """Brief 47: the harness section of agent.html. Settings from the code, arms from brief 42, fixes with evidence."""
    s = harness_settings()
    from deepagents.middleware._utils import is_anthropic_chat_model

    from agent.graph.llm import Meter, Reply, chat_model
    anth = is_anthropic_chat_model(chat_model(lambda m, tools=None: Reply(text="", tool_calls=[]), Meter(run_limits={"turns": 1}), []))
    idle = {"_ParentNotifierMiddleware": True, "AnthropicPromptCachingMiddleware": not anth}    # present, but no effect here
    mw = [{"name": m, "words": MIDDLEWARE_WORDS[m].format(**s), "acts": not idle.get(m, False)} for m in inner["middleware"]]
    measured = harness_results()
    arms = []
    for a in HARNESS_ARMS:
        if a["source"]:
            src = (ROOT / a["source"]).read_text()
            for n in re.findall(r"\d+(?:\.\d+)?", a["evidence"]):
                assert n in src, (a["id"], n, a["source"])
        r = measured.get(a["id"])
        arms.append({**a, "status": r["status"] if r else "not yet measured", "result": r})
    cache = json.loads((ROOT / "results/33_vivado_speed_2026_1/summary.json").read_text())["cache"]["c10"]
    assert cache["same_result"]
    fixes = []
    for f in HARNESS_FIXES:
        for p in f["files"]:
            assert (ROOT / p).exists(), p
        fixes.append({**f, "text": f["text"].format(**cache)})
    return {"settings": s, "middleware": mw, "arms": arms, "fixes": fixes, "round1": measured.get("_run"),
            "todo_tool": inner["todo_tool"], "subagent_tool": inner["subagent_tool"],
            "system_prompt_only_ours": inner["system_prompt_only_ours"], "audit_date": "2026-11-11"}
