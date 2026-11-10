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
    "__end__": ("end", "The run stops: every stage passed, or a limit was reached."),
}
EDGE_WORDS = {
    ("__start__", "work"): "spec.md",
    ("work", "gate"): "files written",
    ("gate", "review"): "gate JSON",
    ("review", "advance"): "snapshot, approval",
    ("advance", "work"): "next stage, or repair",
    ("advance", "__end__"): "done, or give up",
}
INNER_WORDS = {
    "__start__": "the role's prompt and files", "PatchToolCallsMiddleware.before_agent": "tidy unanswered tool calls",
    "model": "model call", "tools": "tool calls", "_ParentNotifierMiddleware.after_agent": "report back",
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
    "clarify": ("Clarify", "Turns the plain-English request into a structured spec, asking about what it leaves open."),
    "model": ("Blind model", "Writes a short Python model of the design from the spec alone. Never sees the RTL."),
    "tests": ("Test writer", "Writes the tests and the test plan from the spec and the model. Never sees the RTL."),
    "rtl": ("RTL writer", "Writes the SystemVerilog and constraints, and repairs what the later stages find."),
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
     "at": "the RTL writer", "status": "not yet measured"},
    {"id": "A4", "name": "Plan and decompose", "adds": "a split into modules with contracts, built in parallel and then integrated",
     "at": "the plan", "status": "not yet measured"},
    {"id": "A5", "name": "Retrieve, then adapt", "adds": "a search for the closest verified component, which is adapted instead of writing from nothing",
     "at": "the RTL writer", "status": "not yet measured"},
    {"id": "A6", "name": "Constraints critic", "adds": "a narrow agent that reviews timing exceptions against known rules",
     "at": "the constraints stage", "status": "not yet measured"},
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
    register_harness_profile("fda", HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)))
    seen = {}

    def client(msgs, tools=None):
        seen["tools"] = [t["function"]["name"] for t in (tools or [])]
        return Reply(text="done", tool_calls=[])
    a = create_deep_agent(model=chat_model(client, Meter(run_limits={"turns": 3}), []), tools=[], system_prompt="x",
                          backend=StateBackend())
    a.invoke({"messages": [{"role": "user", "content": "x"}]})
    g = a.get_graph()
    return {"nodes": list(g.nodes), "edges": sorted({(e.source, e.target, bool(e.conditional)) for e in g.edges}),
            "builtin_tools": seen["tools"], "todo_tool": "write_todos" in seen["tools"], "subagent_tool": "task" in seen["tools"]}


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
    """'Test writer' -> 'test writer'; 'RTL writer' stays."""
    return label if label[:2].isupper() else label[0].lower() + label[1:]


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
                                            " and ".join(_low(ROLE_WORDS[x][0]) for x in nxt_roles) + "'s work.")}
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
    }
