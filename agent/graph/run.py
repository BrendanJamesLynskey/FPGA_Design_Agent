"""The agent graph (brief 05b): LangGraph over the stage machine, Deep Agents sub-agents per stage.

Nodes, in a loop over ``agent.graph.stages.MACHINE``:

``work``   the stage's sub-agent(s) act, each through its role view (``agent.graph.roles``); stage 2 runs three
           separate sub-agents in order: blind model (sees only spec.yaml), test writer (spec.yaml + model), RTL
           writer (never the hidden spec). Restricted roles run on an in-memory file backend seeded with only
           their inputs; the graph copies their outputs into the design through the role jail.
``gate``   the flow's own checks for the stage, run by the graph (never by the model): lint, simulate (in the
           container), build, gates; then ``exit_check``. Stage 0 runs the interview here.
``review`` writes the review page, takes the snapshot (git commit + .dcp + manifest), and pauses with an
           interrupt when ``--review on`` (approve / edit with a note / rewind to stage N). Before stage 9 touches
           the board it always pauses (owner decision: hw_checks.py is not containerised).

Exit from a stage only on its gates; a failure goes to the stage ``route_failure`` names. Turn, time and cost
limits per stage visit and per run come from ``stages.MACHINE`` / ``RUN_LIMITS`` and are enforced by the Meter.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TypedDict

import yaml

from agent.core import Session, dispatch
from agent.core.runner import ContainerRunner, LocalRunner, container_available
from agent.core.session import ROOT
from agent.graph import review as rv
from agent.graph.interview import Interview, Question, SpecOracle
from agent.graph.llm import BudgetExceeded, Meter, chat_model
from agent.graph.roles import ROLES, RoleJail, role_inputs, role_session
from agent.graph.snapshot import Snapshots
from agent.graph.stages import MACHINE, RUN_LIMITS, classify, exit_check, route_failure

RUNS = ROOT / "runs"
FLOW_TOOLS = ("read_file", "list_files", "lint", "simulate", "formal", "build", "gates", "report", "check_constraints", "search_docs",
              "load_skill")


class State(TypedDict, total=False):
    detail: str
    run_id: str
    stage: int
    visits: dict
    evidence: dict
    fails: list
    note: str
    history: list
    stop: str
    interview: dict
    hw_approved: bool


@dataclass
class Config:
    spec_md: Path
    name: str
    board: str = "nexys_a7_100t"
    interview: str = "off"          # on (human) | oracle | off
    review: str = "off"             # on | off
    model: str = "openai/gpt-6-luna"
    hidden_spec: Path | None = None
    run_limits: dict = field(default_factory=lambda: dict(RUN_LIMITS))
    stop_after: int | None = None   # smokes: stop after this stage passes


@dataclass
class Runtime:
    cfg: Config
    run_id: str
    run_dir: Path
    design: Path
    session: Session
    client: Callable
    meter: Meter
    snaps: Snapshots
    oracle_llm: Callable | None = None
    llm_log: list = field(default_factory=list)
    last_build_output: str = ""


_RT: dict[str, Runtime] = {}


# --- sub-agents ---------------------------------------------------------------------------------------------------

PROMPTS = {
    "clarify": "You turn a short design request (spec.md) into spec.yaml for an FPGA design on the {board}. Write "
               "spec.yaml with: name, title, board, part, top, clocks, reset, parameters, ports (name, direction, "
               "width, board pin role), behaviour, registers, timing, resources_expected, assumptions (each with a "
               "reason), and open_questions: one entry per thing the request leaves open, each as {{question, "
               "default, reason}} (the default you propose and why). Use only spec.md and the knowledge tools.",
    "model": "You are the blind golden model writer. From spec.yaml alone write model.py: a pure-Python, cycle-level "
             "reference model of the design's externally visible behaviour (no HDL, no simulator imports).",
    "tests": "You write the cocotb tests for the design from spec.yaml and the blind model model.py (you never see "
             "the RTL). Write tests/test_{name}_rtl.py (pytest entry calling flow.cocotb_run) and the cocotb bench; "
             "import the model with sys.path.insert(0, str(Path(__file__).resolve().parents[1])); import model. "
             "Also write verif/testplan.yaml tracing every spec item to a test.",
    "rtl": "You are the RTL and implementation engineer for stage {stage} ({stage_name}) of the UltraFast flow on the "
           "{board}. Do only what this stage allows: {allowed}. The flow's gates decide when the stage is done, "
           "not you; when you think your part is complete, stop and reply DONE. Failures so far: {fails}. "
           "Reviewer note: {note}",
}


CONVENTIONS = """
Flow conventions (fixed by the repo; follow them exactly):
- Paths in build.yaml are relative to the repo root. This design's directory is {design_rel}. build.yaml:
    top: <top module>
    part: xc7a100tcsg324-1
    sources: [shell/rtl/*.sv, {design_rel}/rtl/*.sv]
    constraints: [{design_rel}/design.xdc]
    generics: {{}}
    probes: {design_rel}/probes.yaml
- The board top must instantiate the test shell `fpga_shell` (UART register window; read @shell/PROTOCOL.md and
  @shell/rtl/fpga_shell.sv with fda_read_file). fpga_shell ports: clk, rst (sync, active high), uart_rx, uart_tx,
  win_addr[6:0], win_wr, win_rd, win_wdata[31:0], win_rdata[31:0] (due one cycle after win_rd); parameters
  CLKS_PER_BIT, TIMEOUT_CYCLES, DESIGN_ID, BUILD_STAMP. The design's registers live in this window.
- design.xdc: pins and IOSTANDARDs from the board's master XDC (search_docs / load_skill), create_clock on the
  board clock port only.
- ARCHITECTURE.md must have a "## Block diagram" section with a fenced text diagram, the clock plan and the pin list.
- Tests (test writer): tests/test_{name}_rtl.py is a pytest entry that calls
  flow.cocotb_run.run(name, toplevel, sources, test_module, test_dir, parameters=..., seed=...), where
  sources = flow.cocotb_run.SHELL_RTL + sorted((design_dir / "rtl").glob("*.sv")); the cocotb bench module sits
  next to it in tests/ and checks the RTL against model.py. verif/testplan.yaml traces every spec item to a test.
"""


def _core_tools(rt: Runtime, sess: Session, allowed: tuple[str, ...]):
    from langchain_core.tools import StructuredTool

    from agent.core.registry import TOOLS
    out = []
    for name in allowed:
        if name not in FLOW_TOOLS or name not in TOOLS:
            continue
        t = TOOLS[name]

        def fn(_n=name, **kw):
            return json.dumps(dispatch(sess, _n, kw))[:20000]
        out.append(StructuredTool.from_function(func=fn, name=f"fda_{name}", description=t.description,
                                                args_schema={"type": "object", "properties": t.input_schema.get(
                                                    "properties", {}), "additionalProperties": False}))
    return out


def _jail_backend(rt: Runtime, role: str):
    """The real design directory, every path checked by the role jail (rtl role)."""
    from deepagents.backends import FilesystemBackend

    from agent.core.security import SecurityError
    jail = RoleJail(rt.session.jail, role)

    class JailBackend(FilesystemBackend):
        def _resolve_path(self, key):
            p = super()._resolve_path(key)
            rel = str(p.relative_to(rt.design)) if p != rt.design else "."
            try:
                jail.resolve(rel)
            except SecurityError as e:
                raise ValueError(str(e)) from None
            return p

        def write(self, file_path, content):
            try:
                jail.resolve(file_path.lstrip("/"), write=True)
            except SecurityError as e:
                from deepagents.backends.protocol import WriteResult
                return WriteResult(error=str(e))
            return super().write(file_path, content)

        def edit(self, file_path, old_string, new_string, replace_all=False):
            try:
                jail.resolve(file_path.lstrip("/"), write=True)
            except SecurityError as e:
                from deepagents.backends.protocol import EditResult
                return EditResult(error=str(e))
            return super().edit(file_path, old_string, new_string, replace_all)

    return JailBackend(root_dir=rt.design, virtual_mode=True)


def run_subagent(rt: Runtime, role: str, prompt: str, allowed: tuple[str, ...] = ()) -> dict[str, str]:
    """Run one Deep Agents sub-agent. Restricted roles see only their seeded inputs (in-memory backend) and
    their outputs are copied into the design through the role jail. Returns {path: content} written."""
    from deepagents import HarnessProfile, create_deep_agent, register_harness_profile
    from deepagents.backends.utils import create_file_data, file_data_to_string
    from deepagents.profiles.harness.harness_profiles import GeneralPurposeSubagentProfile

    register_harness_profile("fda", HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)))
    sess = role_session(rt.session, role)
    model = chat_model(rt.client, rt.meter, rt.llm_log)
    inputs = role_inputs(rt.session, role)
    msg = prompt + "\n\nFiles you have:\n" + "\n".join(f"--- {k} ---\n{v}" for k, v in inputs.items())
    if role == "rtl":
        agent = create_deep_agent(model=model, tools=_core_tools(rt, sess, allowed), system_prompt=prompt,
                                  backend=_jail_backend(rt, role))
        agent.invoke({"messages": [{"role": "user", "content": msg}]}, {"recursion_limit": 200})
        return {}
    agent = create_deep_agent(model=model, tools=_core_tools(rt, sess, allowed), system_prompt=prompt)
    out = agent.invoke({"messages": [{"role": "user", "content": msg}],
                        "files": {f"/{k}": create_file_data(v) for k, v in inputs.items()}},
                       {"recursion_limit": 120})
    written = {}
    for path, data in (out.get("files") or {}).items():
        rel = path.lstrip("/")
        if rel in inputs:
            continue
        r = dispatch(sess, "write_file", {"path": rel, "content": file_data_to_string(data)})
        if not r.get("refused"):
            written[rel] = r["output"]
    return written


# --- nodes --------------------------------------------------------------------------------------------------------

def _rt(state: State) -> Runtime:
    return _RT[state["run_id"]]


def node_work(state: State) -> dict:
    rt, n = _rt(state), state["stage"]
    st = MACHINE[n]
    visits = dict(state.get("visits") or {})
    visits[str(n)] = visits.get(str(n), 0) + 1
    if visits[str(n)] > rt.cfg.run_limits["visits_per_stage"]:
        return {"visits": visits, "stop": f"stage {n} visited more than {rt.cfg.run_limits['visits_per_stage']} times"}
    rt.meter.start_stage(st.limits)
    rt.session.stage = st.name
    fmt = {"board": rt.cfg.board, "name": rt.cfg.name, "stage": n, "stage_name": st.name,
           "allowed": ", ".join(st.tools), "fails": "; ".join(state.get("fails") or []) or "none",
           "note": state.get("note") or "none",
           "design_rel": str(rt.design.relative_to(ROOT))}
    conv = CONVENTIONS.format(**fmt) + ("\nLast gate output:\n" + state["detail"][:3000] if state.get("detail") else "")
    try:
        if n == 0:
            run_subagent(rt, "clarify", PROMPTS["clarify"].format(**fmt), ("search_docs", "load_skill"))
        elif n == 2:
            run_subagent(rt, "model", PROMPTS["model"].format(**fmt))
            run_subagent(rt, "tests", PROMPTS["tests"].format(**fmt) + conv, ("search_docs", "load_skill"))
            run_subagent(rt, "rtl", PROMPTS["rtl"].format(**fmt) + conv, st.tools)
        elif n != 9 or state.get("hw_approved"):
            run_subagent(rt, "rtl", PROMPTS["rtl"].format(**fmt) + conv, tuple(t for t in st.tools
                                                                         if t not in ("program", "bringup")))
    except BudgetExceeded as e:
        if str(e).startswith("run "):                      # run limit: stop the run
            return {"visits": visits, "stop": f"budget: {e}"}
        return {"visits": visits, "note": "", "detail": f"stage visit ended: {e}"}   # stage limit: gate decides
    return {"visits": visits, "note": ""}


def _spec(rt: Runtime) -> dict:
    p = rt.design / "spec.yaml"
    try:
        return yaml.safe_load(p.read_text()) or {} if p.is_file() else {}
    except yaml.YAMLError:
        return {}


def _interview(rt: Runtime, spec: dict, state: State) -> tuple[dict, dict]:
    from langgraph.types import interrupt
    iv = Interview()
    who = None
    if rt.cfg.interview == "oracle":
        who = SpecOracle(rt.cfg.hidden_spec, rt.oracle_llm)
    for i, o in enumerate(spec.get("open_questions") or []):
        q = Question(id=f"q{i + 1}", text=str(o.get("question", "")), default=str(o.get("default", "")),
                     reason=str(o.get("reason", o.get("default", ""))))
        if rt.cfg.interview == "on":                                  # one question at a time, to the human
            ans = interrupt({"kind": "question", "id": q.id, "question": q.text, "default": q.default,
                             "reason": q.reason})

            class _Human:
                name = "human"

                def answer(self, _q, a=ans):
                    return (str(a.get("answer") or "not specified") if isinstance(a, dict) else str(a)), None
            iv.ask(q, _Human())
        else:
            iv.ask(q, who)
    spec = iv.resolve_into(spec)
    (rt.design / "spec.yaml").write_text(yaml.safe_dump(spec, sort_keys=False))
    return spec, iv.summary()


_ORDER = ["synth", "place", "route", "bitstream"]


def _sources_hash(rt: Runtime) -> str:
    import hashlib
    h = hashlib.sha256()
    for p in sorted(rt.design.rglob("*")):
        rel = p.relative_to(rt.design)
        if p.is_file() and rel.parts[0] in ("rtl", "build.yaml", "design.xdc", "probes.yaml", "lint"):
            h.update(str(rel).encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def _build(rt: Runtime, until: str, variant: str = "base") -> dict:
    """Run the Vivado flow to ``until`` unless a build of the same sources already went at least that far (the
    later stages re-read the same reports; a rebuild would only cost time). Gates always re-parsed."""
    key, cache = _sources_hash(rt), rt.run_dir / f"build_cache_{variant}.json"
    c = json.loads(cache.read_text()) if cache.is_file() else {}
    if c.get("sources") == key and _ORDER.index(c.get("until", "synth")) >= _ORDER.index(until) and c.get("ok"):
        b = {"ok": True, "cached": True}
    else:
        b = dispatch(rt.session, "build", {"until": until, "variant": variant})
        if not b.get("ok"):
            rt.last_build_output = str(b.get("output", ""))[-2000:]
        cache.write_text(json.dumps({"sources": key, "until": until, "ok": bool(b.get("ok"))}))
    g = dispatch(rt.session, "gates", {"kind": "stages", "variant": variant})
    return {"build": {k: b.get(k) for k in ("ok", "refused", "returncode", "cached")}, "gates": g.get("gates")}


def node_gate(state: State) -> dict:
    rt, n = _rt(state), state["stage"]
    if state.get("stop"):
        return {}
    st, ev = MACHINE[n], dict(state.get("evidence") or {})
    out: dict[str, Any] = {}
    rt.session.stage = st.name
    detail: list[str] = []

    def d(name, r):
        if not r.get("ok"):
            detail.append(f"[{name}] " + str(r.get("output", ""))[-1500:])
        return r
    if n == 0:
        spec, summary = _interview(rt, _spec(rt), state)
        out["interview"] = summary
        ev["spec"], ev["signed_off"] = spec, not spec.get("open_questions")
    elif n == 1:
        ev["arch"] = (rt.design / "ARCHITECTURE.md").is_file()
        ev["inventory"] = {"ok": bool(d("check_constraints", dispatch(rt.session, "check_constraints", {})).get("ok"))}
    elif n == 2:
        ev["lint"] = {"ok": d("lint", dispatch(rt.session, "lint", {})).get("ok")}
        ev["simulate"] = {"ok": d("simulate", dispatch(rt.session, "simulate", {"sim": "icarus"})).get("ok")}
        ev["verif"] = d("verif_gates", dispatch(rt.session, "gates", {"kind": "verif"})).get("gates") or {}
        ev["gates_base"] = _build(rt, "synth")["gates"]
    elif n in (3, 4):
        ev["gates_base"] = _build(rt, "synth")["gates"]
    elif n == 5:
        ev["gates_base"] = _build(rt, "route")["gates"]
    elif n in (6, 7, 8):
        ev["gates_base"] = _build(rt, "route")["gates"]
    elif n == 9:
        ev["gates_base"] = _build(rt, "bitstream")["gates"]
        ev["gates_ila"] = _build(rt, "bitstream", "ila")["gates"]
        if state.get("hw_approved"):
            rt.session.stage = st.name
            br = dispatch(rt.session, "bringup", {}) or {}
            ev["bringup"] = br.get("bringup") or {"pass": False, "failed_step": br.get("rule") or "bringup",
                                                  "why": str(br.get("output", ""))[:300]}
    if rt.last_build_output:
        detail.append("[build] " + rt.last_build_output)
        rt.last_build_output = ""
    if n == 9 and not state.get("hw_approved"):
        from dataclasses import replace as _replace
        ok, fails = exit_check(_replace(st, gates=tuple(g for g in st.gates if g != "bringup")), ev)
        if ok:                                   # everything but the board passes: ask before programming
            ok, fails = False, ["hardware: awaiting approval before programming"]
    else:
        ok, fails = exit_check(st, ev)
    return {**out, "evidence": ev, "fails": [] if ok else fails, "detail": "\n".join(detail)}


def node_review(state: State) -> dict:
    from langgraph.types import interrupt
    rt, n = _rt(state), state["stage"]
    st = MACHINE[n]
    hist = list(state.get("history") or [])
    passed = not state.get("fails") and not state.get("stop")
    gates = [[f, False, ""] for f in state.get("fails") or []] or [[g, True, ""] for g in st.gates]
    info = {"gates": gates, "visits": (state.get("visits") or {}).get(str(n), 1), "used": rt.meter.stage,
            "limits": st.limits, "inputs": list(ROLES["rtl"]["read"]) if n else ["spec.md"],
            "outputs": sorted(str(p.relative_to(rt.design)) for p in rt.design.rglob("*")
                              if p.is_file() and "build" not in p.parts)[:40],
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "notes": json.dumps(state.get("interview"), indent=1) if n == 0 and state.get("interview") else ""}
    hw_pause = n == 9 and not state.get("hw_approved") and state.get("fails") == [
        "hardware: awaiting approval before programming"]
    decision = {"decision": "approve", "by": "auto", "note": ""}
    page = rv.write_page(rt.design, n, st.name, {**info, "approval": None})
    snap = rt.snaps.take(n, st.name, note="pass" if passed else "; ".join(state.get("fails") or [])[:150])
    if rt.cfg.review == "on" or hw_pause:
        reply = interrupt({"kind": "review", "stage": n, "stage_name": st.name, "page": str(page),
                           "passed": passed, "fails": state.get("fails"), "hardware": hw_pause})
        decision = {"decision": reply.get("decision", "approve"), "by": reply.get("by", "human"),
                    "note": reply.get("note", ""), "to": reply.get("to")}
    rv.write_page(rt.design, n, st.name, {**info, "approval": decision})
    hist.append({"n": n, "stage": st.name, "page": str(page), "passed": passed, "approval": decision,
                 "snapshot": snap["commit"], "visit": info["visits"], "used": dict(rt.meter.stage)})
    rv.write_index(rt.design, hist)
    with (rt.design / "BUILD_NOTE.md").open("a") as f:
        f.write(f"\n## review {n:02d} {st.name}\n\n{decision['decision']} by {decision['by']}"
                f"{': ' + decision['note'] if decision.get('note') else ''} (gates {'pass' if passed else 'fail'})\n")
    upd: dict[str, Any] = {"history": hist}
    if decision["decision"] == "rewind" and decision.get("to") is not None:
        to = int(decision["to"])
        r = rt.snaps.rewind(to)
        hist[-1]["rewind"] = {"to": to, "verified": r["verified"], "commit": r["commit"]}
        upd.update(fails=[], note=decision.get("note", ""))
        return {**upd, "history": hist, "evidence": {}}
    if decision["decision"] == "edit":
        return {**upd, "note": decision.get("note", ""), "fails": ["reviewer asked for changes"]}
    if hw_pause:
        return {**upd, "hw_approved": decision["decision"] == "approve"}
    return upd


def route(state: State) -> str:
    if state.get("stop"):
        return "end"
    return "work"


def node_advance(state: State) -> dict:
    rt, n = _rt(state), state["stage"]
    hist = state.get("history") or []
    last = hist[-1] if hist else {}
    if last.get("rewind"):
        return {"stage": last["rewind"]["to"]}
    if n == 9 and state.get("hw_approved") and not (state.get("evidence") or {}).get("bringup"):
        return {"stage": 9}                                   # approved: run stage 9 again with hardware
    fails = state.get("fails") or []
    if fails:
        if fails == ["reviewer asked for changes"]:
            return {"stage": n}
        return {"stage": route_failure(MACHINE[n], classify(MACHINE[n], fails))}
    if n == 9 or (rt.cfg.stop_after is not None and n >= rt.cfg.stop_after):
        return {"stop": "done"}
    return {"stage": n + 1}


def build_graph(checkpointer):
    from langgraph.graph import END, START, StateGraph
    g = StateGraph(State)
    g.add_node("work", node_work)
    g.add_node("gate", node_gate)
    g.add_node("review", node_review)
    g.add_node("advance", node_advance)
    g.add_edge(START, "work")
    g.add_edge("work", "gate")
    g.add_edge("gate", "review")
    g.add_edge("review", "advance")
    g.add_conditional_edges("advance", route, {"work": "work", "end": END})
    return g.compile(checkpointer=checkpointer)


# --- set-up -------------------------------------------------------------------------------------------------------

def new_runtime(cfg: Config, client: Callable, run_id: str | None = None, runner=None,
                oracle_llm: Callable | None = None) -> Runtime:
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    run_dir = RUNS / run_id
    design = run_dir / cfg.name
    first = not design.exists()
    design.mkdir(parents=True, exist_ok=True)
    if first:
        (design / "spec.md").write_text(Path(cfg.spec_md).read_text())
        (design / "__init__.py").write_text("")
    if runner is None:
        runner = ContainerRunner(design, ROOT) if container_available() else LocalRunner()
    bank = None
    try:
        from agent.core.bank import LocalBank
        bank = LocalBank()
    except Exception:                                      # CI: no private knowledge bank
        bank = None
    sess = Session(design=design, board=cfg.board, runner=runner, bank=bank)
    rt = Runtime(cfg, run_id, run_dir, design, sess, client, Meter(cfg.run_limits), Snapshots(run_dir, design),
                 oracle_llm=oracle_llm)
    _RT[run_id] = rt
    (run_dir / "config.json").write_text(json.dumps({**{k: str(v) for k, v in cfg.__dict__.items()},
                                                     "run_limits": cfg.run_limits,
                                                     "isolation": type(runner).__name__}, indent=1))
    return rt


def checkpointer_for(run_dir: Path):
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver
    return SqliteSaver(sqlite3.connect(str(run_dir / "checkpoints.sqlite"), check_same_thread=False))


def summary(rt: Runtime, state: dict) -> dict:
    hist = state.get("history") or []
    return {"run_id": rt.run_id, "design": rt.cfg.name, "model": rt.cfg.model, "interview": rt.cfg.interview,
            "review": rt.cfg.review, "stages_visited": [h["n"] for h in hist],
            "loops": sum(1 for a, b in zip(hist, hist[1:]) if b["n"] <= a["n"] and not a.get("rewind")),
            "rewinds": [h["rewind"] for h in hist if h.get("rewind")],
            "tokens": rt.meter.run["tokens"], "cost_usd": rt.meter.run["usd"], "unreported_cost_calls": rt.meter.unreported,
            "turns": rt.meter.run["turns"], "wall_s": rt.meter.run["seconds"],
            "questions": (state.get("interview") or {}), "stop": state.get("stop"),
            "gates_last": {h["stage"]: h["passed"] for h in hist},
            "approvals": [{"n": h["n"], **h["approval"]} for h in hist],
            "bringup": ((state.get("evidence") or {}).get("bringup") or {}).get("pass")}
