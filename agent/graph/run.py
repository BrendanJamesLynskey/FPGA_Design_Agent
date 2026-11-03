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
import os
import re
import subprocess
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
from agent.graph.contract import MODEL_CONTRACT, contract_argv, parse_result
from agent.graph.interview import Interview, Question, SpecOracle
from agent.graph.llm import BudgetExceeded, Meter, chat_model
from agent.graph.roles import ROLES, RoleJail, role_inputs, role_session
from agent.core.artefacts import check_artefact
from agent.graph.repair import stage2_owners
from agent.graph import ownership
from agent.graph.snapshot import Snapshots
from agent.graph.spec_schema import (PROOF_METHODS, SpecError, clock_hz, load_spec, propose_proof, rate_params,
                                     validate)
from agent.graph.stages import MACHINE, RUN_LIMITS, classify, exit_check, route_failure
from flow import architecture as arch_mod

RUNS = ROOT / "runs"
FLOW_TOOLS = ("read_file", "list_files", "lint", "simulate", "formal", "build", "gates", "report", "check_constraints", "search_docs",
              "load_skill", "board_constraints", "spec_items")


class ArmBlocked(Exception):
    """The Claude Code arm cannot run at all (no token, CLI missing, login failed)."""


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
    owners: dict        # stage 2: role -> the failure text that role owns (05c2: repair, do not regenerate)
    sig: str            # stage 2: signature of the last failure
    repeat: int         # stage 2: consecutive visits with an unchanged signature
    note_role: str      # the owner's edit prompt goes to this role (default: the stage's writer)
    arch_source: str    # who wrote the approved architecture: agent | owner
    hand_edit_only: bool  # the owner edited by hand and gave no prompt: re-run the gates on their files, no agent turn


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
    harness: str = "deepagents"     # deepagents | claude_code (05c: headless `claude -p` on the Max plan)
    cc_model: str = "claude-haiku-5-5"
    cc_effort: str = "medium"
    verif_level: str = "V3"         # verification stage stage 2 must reach (V3 = the methodology)
    profile: str = "single"         # per-role model routing (05f): single | cvdp (agent.graph.role_models.PROFILES)
    roles: dict | None = None       # explicit per-role overrides on top of the profile: role -> {harness, model, effort}

    def role_models(self, stage: str | None = None) -> dict:
        """role -> {harness, model, effort}, with the ``role@stage`` overrides of ``stage`` applied. The interview
        oracle is not a role: it always runs on ``model``."""
        from agent.graph.role_models import resolve
        return resolve(self, stage)


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
    client_for: Callable[[str], Callable] | None = None     # OpenRouter client for a deepagents role on another model
    visit: int = 0                                          # the current stage's visit number (for the turn trace)
    budget_notes: list = field(default_factory=list)        # roles whose turn budget ended this visit (05g)


_RT: dict[str, Runtime] = {}


# --- sub-agents ---------------------------------------------------------------------------------------------------

PROMPTS = {
    "clarify": "You turn a short design request (spec.md) into spec.yaml for an FPGA design on the {board}. Write "
               "spec.yaml with: name, title, board, part, top, clocks, reset, parameters, ports (name, direction, "
               "width, board pin role), behaviour, registers, timing, resources_expected, assumptions (each with a "
               "reason), and open_questions: one entry per thing the request leaves open, each as {{question, "
               "default, reason}} (the default you propose and why). Use only spec.md and the knowledge tools. "
               "requirements: a list of {{id, text, proof}}, one per checkable requirement of the request (id unique, for example "
               "REQ-01); proof is a list of the methods that will discharge it, from simulation (a cocotb test against the "
               "blind model), formal (a SymbiYosys property), hardware (a bring-up check on the board) and analysis (a flow "
               "gate or report: timing, resources, power); propose the method you think fits, and leave proof out only if "
               "you cannot tell (the interview will ask). "
               "spec.yaml must be valid YAML (quote any text that contains ': ' or '?'); ports, clocks, reset, "
               "behaviour, registers and timing must all be non-empty, in this exact shape: behaviour is a mapping of "
               "group name -> list of statements; registers is a mapping with a 'map' list of entries "
               "{{offset, name, access, reset, bits}}; timing is a mapping, with latency: a mapping of name -> text. Timing parameters (debounce, PWM period, scan or "
               "refresh period, baud divider) are INTEGER CYCLE COUNTS of the named clock, for example "
               "PWM_PERIOD_CYCLES: 1024; put the rate or duration only in a comment or in timing. Never a rate "
               "(_HZ, _MS) or a fraction as a parameter. If spec.yaml already exists it is shown below with the "
               "gate's message: fix it in place.",
    "model": "You are the blind golden model writer. From spec.yaml alone write model.py: a pure-Python, cycle-level "
             "reference model of the design's externally visible behaviour (no HDL, no simulator imports).\n"
             + MODEL_CONTRACT,
    "tests": "You write the cocotb tests for the design from spec.yaml and the blind model model.py (you never see "
             "the RTL). Write tests/test_{name}_rtl.py (pytest entry calling flow.cocotb_run) and the cocotb bench; "
             "import the model with sys.path.insert(0, str(Path(__file__).resolve().parents[1])); import model. "
             "Also write verif/testplan.yaml tracing every spec item to a test: call spec_items for the exact ids "
             "the V1 gate checks (every one must appear in some requirement's spec list), and the requirements of spec.yaml with "
             "their proof methods: the testplan gets a top-level `proof:` list of {{requirement, method, artefact}}, one "
             "entry for every method of every requirement. artefact is: for simulation a bench test (module.test) that "
             "checks it, for formal a SymbiYosys job name in verif/formal, for hardware a bring-up step (uart_tests, "
             "ila_captures) or step:case, for analysis a flow gate (stage:gate, for example post_route:setup, "
             "post_synth:post_synth_resources_in_range).\n" + MODEL_CONTRACT,
    "hwtests": "You write the board bring-up tests and ILA capture checks for the design (stage 9), from spec.yaml, the "
               "blind model model.py, probes.yaml and BRINGUP.md. You never see the RTL. Write tests/test_{name}_hw.py "
               "and hw_checks.py. Paths are relative to the design directory (/tests/..., /hw_checks.py). "
               "Problems found by the bring-up artefact check: {fails}\n",
    "rtl": "You are the RTL and implementation engineer for stage {stage} ({stage_name}) of the UltraFast flow on the "
           "{board}. Do only what this stage allows: {allowed}. The flow's gates decide when the stage is done, "
           "not you; when you think your part is complete, stop and reply DONE. Failures so far: {fails}. "
           "Reviewer note: {note}",
}


#: the bring-up file formats of stage 9, as a short schema (never the reference design's content): what
#: flow/bringup.py and flow/hw_dry_check.py need. Same text for both harnesses.
HW_FORMAT = """
Bring-up files (stage 9; flow/bringup.py runs them on the board once the owner approves programming):
- tests/test_{name}_hw.py: a pytest module with `pytestmark = pytest.mark.hw` and plain `def test_...(board)` functions.
  A module-scoped fixture `board` opens the board's UART: `from shell.host.fpga_shell import FpgaShell`;
  `FpgaShell.open(request.config.getoption("--hw-port"), timeout_s=0.2)`; the bitstream's build stamp comes from
  `request.config.getoption("--hw-stamp")` (hex text). Registers are read and written through the shell window,
  `sh.read(p.WINDOW_BASE + offset)` / `sh.write(p.WINDOW_BASE + offset, value)` with `from shell.host import
  protocol as p` (@shell/PROTOCOL.md has the frames). Compare every answer with the blind model (model.py). Leave the
  design at its reset values afterwards, and keep LED duty and count low (the board's power rule).
- hw_checks.py: the ILA capture checks, run on the ILA build. A module-level `CAPTURES: list[Capture]` where you define
  `Capture` as a dataclass with name, condition ("AND" or "OR"), position (int, trigger position in the 1024-sample
  window), compares (dict: probe name -> the integer value the trigger waits for; use "AND": Vivado cannot merge the compare
  values of one ILA port under "OR"), setup(sh), stimulus(sh) and
  check(samples) -> dict with a "pass" bool; `samples` is {{probe name: [value per clock]}}. Probe names are the ones in
  probes.yaml. Also a function `restore(sh)` that puts the design back at its reset values.
- BRINGUP.md for a tester who did not design it, with the sections Setup, Testing (step by step, pass/fail), Debug aids
  (the ILA probes and their triggers) and If it fails.
Call gates(kind="bringup_ready") to check that these files are complete without the board. The stage cannot ask the
owner to approve programming until that check passes.
"""

FRESH_TESTS = (" Write your whole output: files of an earlier attempt that you do not write again are deleted.")


def repair_note(role: str, reasons: list[str]) -> str:
    """The extra prompt text of a repair visit: only this role's own failures, and the instruction to edit."""
    return ("\n\nREPAIR VISIT. Your previous output is in the files listed below: it is yours to edit. The gates found "
            f"problems that belong to the {role} role:\n" + "\n".join(f"- {r[:2200]}" for r in reasons)
            + "\nMake the smallest change that fixes them. Do not rewrite or restructure what already works; the other "
              "artefacts are frozen and nobody else rewrites them this visit.")


CONVENTIONS = """
Flow conventions (fixed by the repo; follow them exactly):
- File tool paths (read_file, write_file, list_files) are relative to the design directory, for example rtl/top.sv; "{design_rel}/rtl/top.sv" and "/rtl/top.sv" mean the same file.
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
  CLKS_PER_BIT, TIMEOUT_CYCLES, DESIGN_ID, BUILD_STAMP. The design's registers live in this window. The board top
  declares `parameter logic [31:0] BUILD_STAMP = 32'h0` and passes it to fpga_shell (.BUILD_STAMP(BUILD_STAMP)); the
  flow sets it per build, so never write a constant there.
- design.xdc: call board_constraints with a map of board resource name -> your port name (it lists the resources when
  called with no map). It writes the pins, I/O standards and the board clock constraint from the master XDC; never
  write a pin number yourself. check_constraints checks the result.
- probes.yaml (stage 9, ILA debug build; build.yaml `probes:` names it): `ila: {{name, clock_net, depth}}` and a top-level
  `probes:` list of {{name, pins, width}}; pins are post-synthesis register output pins (cell names survive synthesis,
  net names do not; a bus lists its bits with [*] and width must match). Read the synthesised design's reports under
  build/base/ for the real names; the write is refused if the shape is wrong.
- architecture.yaml (stage 1, beside ARCHITECTURE.md): schema fpga-design-agent/architecture/v1 with blocks [{{name, function}}],
  interfaces [{{name, between: [a, b], protocol: axi4-lite|axi4-stream|simple|uart|gpio|other, prefix, module}}],
  clock_domains [{{name, clock (the clock port name), freq_mhz}}], reset {{synchronisers: [module names]}}, crossings
  [{{from, to, signal, primitive, inline_in}}] ('from' may be async; primitive is one of {cdc_prims}) and
  predicted_resources {{lut, ff, bram_tile, dsp}}, each a number or [low, high]. Predict before you write RTL: after
  synthesis a result more than 2x outside your range fails a gate. The owner approves ARCHITECTURE.md and
  architecture.yaml BEFORE any RTL is written, and both are frozen afterwards.
- Design standards v1.0 (checked by flow/standards_check.py; gates(kind="standards") shows the rules and findings):
{standards}
- ARCHITECTURE.md must have a "## Block diagram" section with a fenced text diagram, the clock plan and the pin list.
- Tests (test writer): tests/test_{name}_rtl.py is a pytest entry that calls
  flow.cocotb_run.run(name, toplevel, sources, test_module, test_dir, parameters=..., seed=...), where
  sources = flow.cocotb_run.SHELL_RTL + sorted((design_dir / "rtl").glob("*.sv")); the cocotb bench module sits
  next to it in tests/ and checks the RTL against model.py.
- Stage 2 ends only at verification stage V3 (flow/verif_gates.py): load_skill(["verification-stages"]) first.
  verif/testplan.yaml (schema fpga-design-agent/testplan/v0) has keys: schema, design, spec ({design_rel}/spec.yaml),
  model, bench {{modules: [...], dir: {design_rel}/tests}}, checkers ({design_rel}/verif/checkers), formal_dir
  ({design_rel}/verif/formal), thresholds {{seeds_min, functional_bins_pct, cover_properties_pct, line_pct,
  toggle_pct, mutation_score_pct}}, waivers {{code_coverage: [], functional_bins: [], cover_properties: []}} (each
  waiver needs a reason), requirements: [{{id, spec: [spec.yaml item paths], tests: [module.test], assertions,
  cover_props, bins, formal}}], proof: [{{requirement: <spec.yaml requirement id>, method: simulation|formal|hardware|analysis,
  artefact: ...}}], plus verif/mutants.yaml. The last gate output shows what verif_gates found.
"""


def conventions_text(fmt: dict) -> str:
    """CONVENTIONS with this run's values; the one place that fills it (the Claude Code arm's tests use it too)."""
    from flow import architecture as am
    return CONVENTIONS.format(**{"cdc_prims": ", ".join(am.CDC_PRIMITIVES), "standards": _standards_summary(), **fmt})


def _standards_summary() -> str:
    from flow.standards_check import RULES
    return "\n".join(f"    {k}: {v[1]}" for k, v in RULES.items() if v[0] != "review")


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
        out.append(StructuredTool.from_function(func=fn, name=f"fda_{name}", description=t.describe(),
                                                args_schema={"type": "object", "properties": t.schema().get(
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
            bad = check_artefact(_canon(rt, file_path), content)
            if bad:
                from deepagents.backends.protocol import WriteResult
                return WriteResult(error=f"not written: {bad}")
            return super().write(file_path, content)

        def edit(self, file_path, old_string, new_string, replace_all=False):
            try:
                jail.resolve(file_path.lstrip("/"), write=True)
            except SecurityError as e:
                from deepagents.backends.protocol import EditResult
                return EditResult(error=str(e))
            f = rt.design / file_path.lstrip("/")
            if f.is_file():
                from deepagents.backends.protocol import EditResult
                from deepagents.backends.utils import perform_string_replacement
                r = perform_string_replacement(f.read_text(errors="replace"), old_string, new_string, replace_all)
                bad = None if isinstance(r, str) else check_artefact(_canon(rt, file_path), r[0])
                if bad:
                    return EditResult(error=f"not written: {bad}")
            return super().edit(file_path, old_string, new_string, replace_all)

    return JailBackend(root_dir=rt.design, virtual_mode=True)


def drop_superseded(design: Path, jail, before: list[Path], written: dict[str, str]) -> list[str]:
    """Delete files a role wrote in an earlier attempt and did not write again (05c fix 4), through its jail."""
    gone = []
    for p in before:
        rel = str(p.relative_to(design))
        if rel not in written and p.is_file():
            jail.resolve(rel, write=True)
            p.unlink()
            gone.append(rel)
    return gone


KNOWLEDGE_TOOLS = ("load_skill", "search_docs", "board_constraints")     # never removed or reduced for any role (05f)
FILE_TOOLS = ("read_file", "write_file", "list_files")


def subagent_plan(rt: Runtime, role: str, prompt: str, allowed: tuple[str, ...] = (), repair: bool = False) -> dict:
    """What one sub-agent turn is given, harness-neutral: the system prompt, the first user message, the core
    tools and the limits. Both the Deep Agents run and the Claude Code arm (05c) are built from this, and the
    equivalence test compares them."""
    from agent.core.registry import TOOLS
    from agent.graph.roles import ROLE_TOOLS
    inputs = role_inputs(rt.session, role, previous=repair)
    if role != "rtl":
        prompt += ("\nYour working directory is the design directory: write files at paths like /model.py, "
                   "/tests/..., /verif/... (repo-relative paths in build.yaml and testplan.yaml stay as given).")
    msg = prompt + "\n\nFiles you have:\n" + "\n".join(f"--- {k} ---\n{v}" for k, v in inputs.items())
    core = tuple(n for n in allowed if n in FLOW_TOOLS and n in TOOLS)
    role_files = ROLE_TOOLS[role]
    files = tuple(n for n in FILE_TOOLS if role_files is None or n in role_files)
    return {"role": role, "system_prompt": prompt, "user_message": msg, "inputs": inputs, "core_tools": core,
            "file_tools": files, "limits": dict(rt.meter.stage_limits), "stage": rt.session.stage, "repair": repair,
            "turns_left": rt.meter.turns_left()}


def _canon(rt: Runtime, path: str) -> str:
    rel = path.lstrip("/")
    return rel.removeprefix(str(rt.design.relative_to(ROOT)) + "/")


def _validating_state_backend(rt: Runtime):
    """The in-memory file backend of the restricted roles, validating known artefacts when the model writes or
    edits them (05c2 fix 4): a malformed file is refused with the line and column, in the model's own turn."""
    from deepagents.backends import StateBackend
    from deepagents.backends.protocol import EditResult, WriteResult
    from deepagents.backends.utils import file_data_to_string, perform_string_replacement

    class ValidatingStateBackend(StateBackend):
        def write(self, file_path, content):
            bad = check_artefact(_canon(rt, file_path), content)
            if bad:
                return WriteResult(error=f"not written: {bad}")
            return super().write(file_path, content)

        def edit(self, file_path, old_string, new_string, replace_all=False):
            fd = self._read_files().get(file_path)
            if fd is not None and fd.get("encoding") != "base64":
                r = perform_string_replacement(file_data_to_string(fd), old_string, new_string, replace_all)
                if not isinstance(r, str):
                    bad = check_artefact(_canon(rt, file_path), r[0])
                    if bad:
                        return EditResult(error=f"not written: {bad}")
            return super().edit(file_path, old_string, new_string, replace_all)

    return ValidatingStateBackend()


def role_client(rt: Runtime, model: str) -> Callable:
    """The model client of a Deep Agents role: the run's own client for the run's model, else a factory's."""
    if model == rt.cfg.model:
        return rt.client
    if rt.client_for is None:
        raise ValueError(f"no client for model {model!r} (a Deep Agents role on a model other than the run's)")
    return rt.client_for(model)


def run_subagent(rt: Runtime, role: str, prompt: str, allowed: tuple[str, ...] = (), repair: bool = False) -> dict[str, str]:
    """Run one sub-agent through the harness and model its role is routed to (05f), and account for it per role
    and stage (``role_usage.jsonl``): turns, tokens, wall time, reported cost / plan estimate. Brief 05g adds the turn
    trace to each record: the visit, the turns the role was allowed, how it ended (done / stage_budget / run_budget /
    blocked / error), the tools it called, the refusals it met and the files it wrote."""
    spec = rt.cfg.role_models(rt.session.stage)[role]
    m0, n_cc, t0 = dict(rt.meter.run), len(_cc_calls(rt)), time.monotonic()
    a0, allowed_turns, ended, written = len(rt.session.audit.records), rt.meter.turns_left(), "done", {}
    try:
        written = _run_subagent(rt, role, prompt, allowed, repair, spec)
        return written
    except BudgetExceeded as e:
        ended = "run_budget" if str(e).startswith("run ") else "stage_budget"
        raise
    except ArmBlocked:
        ended = "blocked"
        raise
    except Exception as e:
        ended = f"error:{type(e).__name__}"
        raise
    finally:
        new_cc = _cc_calls(rt)[n_cc:]
        rows = [r for r in rt.session.audit.records[a0:] if r.get("role") in (role, None)]
        tools: dict[str, int] = {}
        refused: dict[str, int] = {}
        for r in rows:
            tools[r["tool"]] = tools.get(r["tool"], 0) + 1
            if r.get("refused"):
                refused[str(r.get("rule"))] = refused.get(str(r.get("rule")), 0) + 1
        rec = {"stage": rt.session.stage, "visit": rt.visit, "role": role, "stage_override": spec != rt.cfg.role_models()[role],
               "harness": spec["harness"], "model": spec["model"],
               "effort": spec["effort"], "repair": repair,
               "turns": int(rt.meter.run["turns"] - m0["turns"]), "turns_allowed": allowed_turns, "ended": ended,
               "tokens": int(rt.meter.run["tokens"] - m0["tokens"]),
               "wall_s": round(time.monotonic() - t0, 1),
               "tools": tools, "refused": refused, "files_written": sorted(written) if isinstance(written, dict) else [],
               "cost_usd": None if spec["harness"] == "claude_code" else round(rt.meter.run["usd"] - m0["usd"], 6),
               "plan_cost_estimate_usd": round(sum(c.get("plan_cost_estimate_usd") or 0 for c in new_cc), 4)
               if spec["harness"] == "claude_code" else None}
        with (rt.run_dir / "role_usage.jsonl").open("a") as f:
            f.write(json.dumps(rec) + "\n")


#: Turns held back while a role runs, for the roles that follow it in the same stage visit (brief 05g). Before this,
#: the stage-9 RTL writer used the whole stage budget and the tests role never got a turn (luna run f7ba, visits 1-2).
ROLE_TURN_RESERVE = {2: {"model": 35, "tests": 25}, 9: {"rtl": 15}}


def run_role(rt: Runtime, role: str, prompt: str, allowed: tuple[str, ...] = (), repair: bool = False) -> dict[str, str]:
    """``run_subagent`` with the stage's turn reserve for the roles after this one. A role that ends on the stage turn
    budget does not stop the visit: the roles after it still run (the gate decides). The run-wide limit still stops the
    run, but only once the real limit (without the reserve) is reached."""
    n = next((st.n for st in MACHINE if st.name == rt.session.stage), -1)
    rt.meter.reserved = ROLE_TURN_RESERVE.get(n, {}).get(role, 0)
    try:
        return run_subagent(rt, role, prompt, allowed, repair)
    except BudgetExceeded as e:
        rt.meter.reserved = 0
        try:
            rt.meter.check()
        except BudgetExceeded:
            if str(e).startswith("run "):
                raise                                   # the real run limit
        rt.budget_notes.append(f"{role}: {e}")
        return {}
    finally:
        rt.meter.reserved = 0


def _run_subagent(rt: Runtime, role: str, prompt: str, allowed: tuple[str, ...], repair: bool, spec: dict) -> dict[str, str]:
    """Run one sub-agent. Deep Agents: restricted roles see only their seeded inputs (in-memory backend) and
    their outputs are copied into the design through the role jail. Returns {path: content} written."""
    if spec["harness"] == "claude_code":
        from agent.claude_code_arm.arm import run_subagent_cc
        return run_subagent_cc(rt, {**subagent_plan(rt, role, prompt, allowed, repair),
                                    "model": spec["model"], "effort": spec["effort"]})
    from deepagents import HarnessProfile, create_deep_agent, register_harness_profile
    from deepagents.backends.utils import create_file_data, file_data_to_string
    from deepagents.profiles.harness.harness_profiles import GeneralPurposeSubagentProfile

    register_harness_profile("fda", HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)))
    sess = role_session(rt.session, role)
    model = chat_model(role_client(rt, spec["model"]), rt.meter, rt.llm_log)
    plan = subagent_plan(rt, role, prompt, allowed, repair)
    prompt, msg, inputs = plan["system_prompt"], plan["user_message"], plan["inputs"]
    if role == "rtl":
        agent = create_deep_agent(model=model, tools=_core_tools(rt, sess, allowed), system_prompt=prompt,
                                  backend=_jail_backend(rt, role))
        agent.invoke({"messages": [{"role": "user", "content": msg}]}, {"recursion_limit": 200})
        return {}
    agent = create_deep_agent(model=model, tools=_core_tools(rt, sess, allowed), system_prompt=prompt,
                              backend=_validating_state_backend(rt))
    out = agent.invoke({"messages": [{"role": "user", "content": msg}],
                        "files": {f"/{k}": create_file_data(v) for k, v in inputs.items()}},
                       {"recursion_limit": 120})
    written = {}
    superseded: list[Path] = []
    if role == "tests" and not repair:        # a fresh write replaces the role's earlier output; a repair edits it
        superseded = [p for d in ("tests", "verif") for p in sorted((rt.design / d).rglob("*"))
                      if p.is_file() and "__pycache__" not in p.parts and p.name != "__init__.py"]
    for path, data in (out.get("files") or {}).items():
        rel = _canon(rt, path)                                            # the repo-relative design path
        content = file_data_to_string(data)
        if inputs.get(rel) == content:
            continue                                                      # seeded and not changed
        r = dispatch(sess, "write_file", {"path": rel, "content": content})
        if not r.get("refused"):
            written[rel] = r["output"]
    if superseded and written:                    # 05c fix 4: a rewrite replaces the role's earlier output
        drop_superseded(rt.design, sess.jail, superseded, written)
    return written


# --- nodes --------------------------------------------------------------------------------------------------------

def tests_checklist(rt: Runtime, stage: int, repair: bool) -> str:
    """The stage-entry checklist of the tests role (brief 05g): the exact files each gate reads, so the role does not
    have to find them out from a failed gate. Plain text built from the design's own names; no reference content."""
    from agent.core.runner import tool_available
    name = rt.cfg.name
    formal = tool_available("sby")
    lines = ["", "", "STAGE-ENTRY CHECKLIST (the files the gates read; the gate fails if one is missing):"]
    if stage == 2:
        lines += [
            f"1. tests/test_{name}_rtl.py: the pytest entry (gate V0 `bench_modules_present`; the `simulate` tool runs tests/test_*_rtl.py).",
            "2. tests/<module>.py for every module listed in bench.modules of the testplan (V0 `bench_modules_present`).",
            "3. verif/testplan.yaml (V0 `testplan_present`, V1 `spec_items_traced`): every spec item traced to a test. "
            "Its `proof:` list needs one {requirement, method, artefact} entry for every method of every requirement in "
            "spec.yaml (V1 `proof_methods_discharged`), and each artefact must exist (V1 `proof_references_resolve`).",
            "4. `formal` methods: " + (
                "SymbiYosys is installed. Write verif/formal/<job>.sby and its property module (properties over the top "
                "module's ports from spec.yaml), call the `formal` tool, and use <job> as the artefact. A job that has not "
                "passed bmc and cover is not discharged." if formal else
                "SymbiYosys is NOT installed here, so no formal job can run. Do not name a formal job and do not claim a "
                "proof. Re-plan the method: add a top-level `replan:` list to verif/testplan.yaml with one "
                "{requirement, method: formal, replaced_by: simulation|analysis|hardware, artefact, why} entry per formal "
                "method (why = a sentence saying why it was re-planned). The replacement's own evidence is what counts."),
            "5. `hardware` methods are discharged in stage 9 (tests/test_" + name + "_hw.py, hw_checks.py); name the bring-up "
            "step in the proof list now (uart_tests, ila_captures or step:case).",
        ]
    else:
        lines += [
            f"1. tests/test_{name}_hw.py: `pytestmark = pytest.mark.hw`, plain `def test_...(board)` functions (bring-up readiness).",
            "2. hw_checks.py: `CAPTURES` (condition AND) and `restore(sh)` (bring-up readiness).",
            "3. Read-only references you can open: shell_ref/PROTOCOL.md, shell_ref/host/fpga_shell.py and "
            "shell_ref/host/protocol.py (the classes you import), and probes.yaml for the probe names.",
            f"4. Keep tests/test_{name}_rtl.py, the bench and verif/ exactly as they are.",
        ]
    lines.append("Write every file of the list in this visit. " + (
        "This is a repair visit: change only the files the failures name, and never delete another." if repair else
        "A file you leave out is a failed gate."))
    return "\n".join(lines) + "\n"


def _rt(state: State) -> Runtime:
    return _RT[state["run_id"]]


def stage2_plan(rt: Runtime, state: State) -> dict[str, list[str] | None]:
    """Which stage-2 roles run this visit, in order. ``None``: a fresh write (the artefact does not exist yet); a list:
    a repair of that role's own output, with the failures that role owns. Roles not listed are frozen."""
    d = rt.design
    have = {"model": (d / "model.py").is_file(),
            "tests": bool(list((d / "tests").glob("test_*_rtl.py"))) if (d / "tests").is_dir() else False,
            "rtl": bool(list((d / "rtl").glob("*.sv"))) if (d / "rtl").is_dir() else False}
    owners = dict(state.get("owners") or {})
    plan: dict[str, list[str] | None] = {}
    for role in ("model", "tests", "rtl"):
        if not have[role]:
            plan[role] = None                            # nothing to repair: write it
        elif role in owners:
            plan[role] = list(owners[role])
        elif not owners and role == "rtl":               # arrived from a later stage's failure: the RTL is the suspect
            plan[role] = [("; ".join(state.get("fails") or []) or "a later stage failed") + "\n"
                          + str(state.get("detail") or "")[:1500]]
    return plan


def node_work(state: State) -> dict:
    rt, n = _rt(state), state["stage"]
    if state.get("hand_edit_only"):                    # the owner edited by hand: gate their files, do not rewrite them
        return {"hand_edit_only": False, "note": ""}
    st = MACHINE[n]
    visits = dict(state.get("visits") or {})
    visits[str(n)] = visits.get(str(n), 0) + 1
    if visits[str(n)] > rt.cfg.run_limits["visits_per_stage"]:
        return {"visits": visits, "stop": f"stage {n} visited more than {rt.cfg.run_limits['visits_per_stage']} times"}
    rt.meter.start_stage(st.limits)
    rt.session.stage = st.name
    rt.visit, rt.budget_notes = visits[str(n)], []
    fmt = {"board": rt.cfg.board, "name": rt.cfg.name, "stage": n, "stage_name": st.name,
           "allowed": ", ".join(st.tools), "fails": "; ".join(state.get("fails") or []) or "none",
           "note": state.get("note") or "none",
           "design_rel": str(rt.design.relative_to(ROOT))}
    conv0 = conventions_text(fmt)
    conv = conv0 + ("\nLast gate output:\n" + state["detail"][:3000] if state.get("detail") else "")
    # the owner's edit prompt (brief 05d, addition 6) goes to the role it names, default the stage's writer
    note_for = state.get("note_role") or ("clarify" if n == 0 else "rtl")
    def prompt_note(role: str) -> str:
        return (f"\n\nThe owner reviewed the last result and asks (their prompt, follow it): {state['note']}"
                if state.get("note") and role == note_for else "")
    try:
        if n == 1:
            (rt.design / arch_mod.APPROVAL).unlink(missing_ok=True)     # the architecture is open again: approve it anew
        if n == 2 and not arch_mod.approval_status(rt.design)[0]:       # no RTL before the architecture is approved
            return {"visits": visits, "note": "", "detail": "stage 2 did not start: " + arch_mod.approval_status(rt.design)[1]}
        if n == 0:
            run_role(rt, "clarify", PROMPTS["clarify"].format(**fmt) + prompt_note("clarify")
                         + ("\nGate message: " + state["detail"][:3000] if state.get("detail") else ""),
                         ("search_docs", "load_skill"))
        elif n == 2:
            for role, reasons in stage2_plan(rt, state).items():
                repair = reasons is not None
                note = repair_note(role, reasons) if repair else ""
                if role == "model":
                    run_role(rt, "model", PROMPTS["model"].format(**fmt) + note + prompt_note("model"), (), repair)
                elif role == "tests":
                    run_role(rt, "tests", PROMPTS["tests"].format(**fmt) + (note if repair else FRESH_TESTS)
                                 + tests_checklist(rt, 2, repair) + prompt_note("tests") + conv0, ("search_docs", "load_skill", "spec_items"), repair)
                else:
                    own = "; ".join(r[:1500] for r in reasons) if repair else (
                        "; ".join(state.get("fails") or []) or "none")
                    run_role(rt, "rtl", PROMPTS["rtl"].format(**{**fmt, "fails": own})
                                 + (note if repair else "") + prompt_note("rtl") + conv0, st.tools, repair)
        else:           # stage 9 too: the model writes probes.yaml and BRINGUP.md BEFORE the builds and the hardware pause
            run_role(rt, "rtl", PROMPTS["rtl"].format(**fmt) + conv + (HW_FORMAT.format(**fmt) if n == 9 else ""),
                         tuple(t for t in st.tools if t not in ("program", "bringup")))
            if n == 9:                                  # then the bring-up tests, which need the probe names (planner item, 05d)
                from flow import hw_dry_check
                dry = hw_dry_check.check_design(rt.design)
                own = [q for q in dry["problems"] if not q.startswith(("BRINGUP.md", "probes.yaml"))]
                if own:
                    run_role(rt, "tests", PROMPTS["hwtests"].format(**{**fmt, "fails": "; ".join(own)})
                                 + tests_checklist(rt, 9, True) + HW_FORMAT.format(**fmt) + MODEL_CONTRACT, ("search_docs", "load_skill", "gates"),
                                 repair=True)        # never "fresh": a fresh tests write deletes the stage-2 benches
        files = [p for p in rt.design.rglob("*") if p.is_file() and "build" not in p.relative_to(rt.design).parts
                 and "__pycache__" not in p.parts]
        ownership.record(rt.design, "agent", st.name, f"stage {n} work, visit {visits[str(n)]}",
                         f"{len(files)} files in the design", n=n)
    except ArmBlocked as e:                                # the Claude Code arm cannot run (auth, CLI): stop, say why
        return {"visits": visits, "stop": f"claude_code blocked: {e}"}
    except BudgetExceeded as e:
        if str(e).startswith("run "):                      # run limit: stop the run
            return {"visits": visits, "stop": f"budget: {e}"}
        return {"visits": visits, "note": "", "detail": f"stage visit ended: {e}"}   # stage limit: gate decides
    if rt.budget_notes:           # a role ended on its turn budget: the gate decides, and the next visit hears about it
        return {"visits": visits, "note": "", "detail": "stage visit ended on the turn budget: " + "; ".join(rt.budget_notes)}
    return {"visits": visits, "note": ""}


def _spec(rt: Runtime) -> dict:
    """The parsed spec.yaml. A parse error raises SpecError (05c fix 1: never an empty spec)."""
    return load_spec(rt.design / "spec.yaml")


def _interview(rt: Runtime, spec: dict, state: State) -> tuple[dict, dict]:
    from langgraph.types import interrupt
    iv = Interview()
    who = None
    if rt.cfg.interview == "oracle":
        who = SpecOracle(rt.cfg.hidden_spec, rt.oracle_llm)
    asks = [(str(o.get("question", "")), str(o.get("default", "")), str(o.get("reason", o.get("default", ""))))
            for o in spec.get("open_questions") or []]
    rates = [r for r in rate_params(spec) if r["cycles"]]
    for r in rates:                                               # 05c fix 3: rates become cycle counts
        clk = f"{clock_hz(spec) / 1e6:g} MHz"
        asks.append((f"{r['name']} is given as {r['value']} {r['unit']}. The model and the RTL need an integer "
                     f"number of clock cycles ({r['new_name']}); at {clk}, how many?", str(r["cycles"]),
                     f"{r['cycles']} is {r['value']} {r['unit']} at {clk}, rounded once, so the model and RTL agree"))
    unproven = [r for r in spec.get("requirements") or [] if isinstance(r, dict) and not r.get("proof")]
    for r in unproven:                                            # 05d: a proof method per requirement, with a default
        methods, why = propose_proof(str(r.get("text", "")))
        asks.append((f"Which proof method discharges requirement {r['id']} ({r.get('text')})? One or more of "
                     f"{', '.join(PROOF_METHODS)}", ",".join(methods), why))
    for i, (qt, qd, qr) in enumerate(asks):
        q = Question(id=f"q{i + 1}", text=qt, default=qd, reason=qr)
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
    for r in rates:                                               # the answered (or defaulted) integer replaces it
        got = next((q for q in iv.questions if q.text.startswith(f"{r['name']} is given as")), None)
        m = re.search(r"\d+", got.answer or "") if got else None
        params = {k: v for k, v in (spec.get("parameters") or {}).items() if k != r["name"]}
        params[r["new_name"]] = int(m.group()) if m else r["cycles"]
        spec["parameters"] = params
    for r in unproven:                                            # the answered (or defaulted) methods go into the spec
        got = next((q for q in iv.questions if q.text.startswith(f"Which proof method discharges requirement {r['id']} ")), None)
        found = [m for m in PROOF_METHODS if got and got.answer and m in got.answer.lower()]
        r["proof"] = found or propose_proof(str(r.get("text", "")))[0]
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


def _contract(rt: Runtime, detail: list) -> dict:
    """Contract-check gate (05c fix 2): import model.py, Model(**spec parameters), reset(), step({})."""
    if not (rt.design / "model.py").is_file():
        res = {"ok": False, "error": "model.py does not exist"}
    else:
        try:
            spec = _spec(rt)
        except SpecError:
            spec = {}
        r = rt.session.runner.run("contract", contract_argv(rt.design, spec), ROOT, None, 120)
        res = parse_result(r.returncode, r.stdout, r.stderr)
    if not res["ok"]:
        detail.append("[model contract] " + str(res.get("error")))
    return res


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
            out = str(r.get("output", ""))
            errs = "\n".join(l[:400] for l in out.splitlines() if l.startswith(("E ", "%Error", "ERROR", "error"))
                             or ": error" in l)[:1500]
            ff = r.get("first_failure")
            head = (f"first failing test {ff['test']}: " + " | ".join(ff["message"]) + (f" ({ff['where']})" if ff.get("where") else "")
                    + "\n") if ff else ""
            detail.append(f"[{name}] " + head + (errs + "\n...\n" if errs else "") + out[-800:])
        return r
    if n == 0:
        ev.pop("spec_errors", None)
        try:
            spec = _spec(rt)
            errs = validate(spec, allow_rates=True, need_proof=False)       # shape first: an invalid spec is never rewritten
        except SpecError as e:
            spec, errs = {}, [str(e)]
        if errs:                                          # fail the gate with the parser's / schema's message
            ev["spec"], ev["signed_off"], ev["spec_errors"] = spec, False, errs
            detail.append("[spec.yaml] " + "; ".join(errs))
        else:
            spec, summary = _interview(rt, spec, state)
            out["interview"] = summary
            errs = validate(spec)
            ev["spec"], ev["signed_off"], ev["spec_errors"] = spec, not spec.get("open_questions"), errs
            if errs:
                detail.append("[spec.yaml] " + "; ".join(errs))
    elif n == 1:
        ev["arch"] = (rt.design / "ARCHITECTURE.md").is_file()
        ev["arch_check"] = arch_mod.check_design(rt.design)
        ev["inventory"] = {"ok": bool(d("check_constraints", dispatch(rt.session, "check_constraints", {})).get("ok"))}
    elif n == 2 and not arch_mod.approval_status(rt.design)[0]:     # nothing below this line runs without an approval
        ok_a, why_a = arch_mod.approval_status(rt.design)
        ev["arch_approval"] = {"ok": ok_a, "why": why_a}
        detail.append("[architecture] " + why_a)
    elif n == 2:
        ev["arch_approval"] = {"ok": True, "why": ""}
        lr = d("lint", dispatch(rt.session, "lint", {}))
        ev["lint"] = {"ok": lr.get("ok"), "text": str(lr.get("output", ""))[-1500:]}
        ev["contract"] = _contract(rt, detail)
        if ev["contract"]["ok"]:                       # fail fast: no simulate on a model the tests cannot load
            sr = d("simulate", dispatch(rt.session, "simulate", {"sim": "icarus"}))
            ev["simulate"] = {"ok": sr.get("ok"), "first_failure": sr.get("first_failure"),
                              "text": str(sr.get("log_tail") or sr.get("output", ""))[-3000:]}
        else:
            ev["simulate"] = {"ok": False}
        ev["verif"] = d("verif_gates", dispatch(rt.session, "gates", {"kind": "verif"})).get("gates") or {}
        ev["verif_level"] = rt.cfg.verif_level
        std = dispatch(rt.session, "gates", {"kind": "standards"})
        ev["standards"] = std.get("gates")
        from agent.graph.stages import standards_stage
        ev["standards_fails"] = standards_stage(ev["standards"], "rtl")[1]
        if ev["standards_fails"]:
            detail.append("[standards] " + "\n".join(ev["standards_fails"])[:1800])
        if ev["lint"]["ok"] and ev["simulate"]["ok"]:          # no Vivado time on a design that fails its tests
            ev["gates_base"] = _build(rt, "synth")["gates"]
    elif n in (3, 4):
        ev["gates_base"] = _build(rt, "synth")["gates"]
        if n == 4:
            std = dispatch(rt.session, "gates", {"kind": "standards"})
            ev["standards"] = std.get("gates")
    elif n == 5:
        ev["gates_base"] = _build(rt, "route")["gates"]
    elif n in (6, 7, 8):
        ev["gates_base"] = _build(rt, "route")["gates"]
    elif n == 9:
        from flow import hw_dry_check
        ev["bringup_ready"] = hw_dry_check.check_design(rt.design)     # before the approval pause, not after it
        ev["gates_base"] = _build(rt, "bitstream")["gates"]
        ev["gates_ila"] = _build(rt, "bitstream", "ila")["gates"]
        if state.get("hw_approved"):
            rt.session.stage = st.name
            br = dispatch(rt.session, "bringup", {}) or {}
            ev["bringup"] = br.get("bringup") or {"pass": False, "failed_step": br.get("rule") or "bringup",
                                                  "why": str(br.get("output", ""))[:300]}
            ev["signoff"] = dispatch(rt.session, "gates", {"kind": "verif"}).get("gates")      # traceability with the board result
    if rt.last_build_output:
        ev["build_output"] = rt.last_build_output           # the repair visit's RTL writer is shown it (05d live run 3)
        detail.append("[build] " + rt.last_build_output)
        rt.last_build_output = ""
    if n == 9 and not state.get("hw_approved"):
        from dataclasses import replace as _replace
        ok, fails = exit_check(_replace(st, gates=tuple(g for g in st.gates if g not in ("bringup", "signoff"))), ev)
        if ok:                                   # everything but the board passes: ask before programming
            ok, fails = False, ["hardware: awaiting approval before programming"]
    else:
        ok, fails = exit_check(st, ev)
    if n == 2:                                   # 05c2 fix 1: the roles that own this visit's failures, and the repeat count
        if ok:
            out.update(owners={}, sig="", repeat=0)
        else:
            prev, rep = state.get("sig") or "", state.get("repeat") or 0
            _, sig = stage2_owners(ev)                       # this failure's signature
            rep = rep + 1 if (prev and sig == prev) else 0   # unchanged since the last visit: the repair did not work
            owners, sig = stage2_owners(ev, repeat=rep)
            out.update(owners=owners, sig=sig, repeat=rep)
    return {**out, "evidence": ev, "fails": [] if ok else fails, "detail": "\n".join(detail)}


ARCH_FILES = ("architecture.yaml", "ARCHITECTURE.md")


def _who(by: str) -> str:
    """owner (a person), auto (the run's own default or an oracle)."""
    return "auto" if by in ("auto", "oracle", "default", "limit") else "owner"


def node_review(state: State) -> dict:
    from langgraph.types import interrupt
    rt, n = _rt(state), state["stage"]
    st = MACHINE[n]
    hist = list(state.get("history") or [])
    passed = not state.get("fails") and not state.get("stop")
    gates = [[f, False, ""] for f in state.get("fails") or []] or [[g, True, ""] for g in st.gates]
    ev = state.get("evidence") or {}
    info = {"gates": gates, "visits": (state.get("visits") or {}).get(str(n), 1), "used": rt.meter.stage,
            "limits": st.limits, "inputs": list(ROLES["rtl"]["read"]) if n else ["spec.md"],
            "outputs": sorted(str(p.relative_to(rt.design)) for p in rt.design.rglob("*")
                              if p.is_file() and "build" not in p.parts)[:40],
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "notes": json.dumps(state.get("interview"), indent=1) if n == 0 and state.get("interview") else "",
            "verif": ev.get("verif"), "standards": ev.get("standards"), "stage_n": n, "board": rt.cfg.board,
            "diff": _stage_diff(rt, n), "owner_rows": ownership.load(rt.design),
            "role_models": rt.cfg.role_models(),
            "role_usage": [u for u in role_usage(rt) if u["stage"] == st.name]}
    hw_pause = n == 9 and not state.get("hw_approved") and state.get("fails") == [
        "hardware: awaiting approval before programming"]
    decision = {"decision": "approve", "by": "auto", "note": ""}
    key = f"{n}:{len(hist)}"                       # LangGraph re-runs this node on resume: one agent snapshot per visit
    page = rv.write_page(rt.design, n, st.name, {**info, "approval": None})
    snap = rt.snaps.take(n, st.name, note="pass" if passed else "; ".join(state.get("fails") or [])[:150], key=key)
    if n == 0 and passed and state.get("interview") and not any(r["what"] == "interview" for r in ownership.load(rt.design)):
        for q in state["interview"].get("questions", []):
            ownership.record(rt.design, _who(q.get("by") or "default"), st.name, "interview",
                             f"{q.get('status')}: {q.get('text', '')[:120]} -> {str(q.get('answer'))[:80]}", n=0)
    hand_only = False
    supplied = None
    reply: dict = {}
    if rt.cfg.review == "on" or hw_pause:
        reply = interrupt({"kind": "review", "stage": n, "stage_name": st.name, "page": str(page),
                           "passed": passed, "fails": state.get("fails"), "hardware": hw_pause})
        decision = {"decision": reply.get("decision", "approve"), "by": reply.get("by", "human"),
                    "note": reply.get("note", ""), "to": reply.get("to"), "role": reply.get("role")}
        if decision["decision"] == "supply" and n == 1:             # the owner supplies the architecture
            supplied = {k: v for k, v in (reply.get("files") or {}).items() if k in ARCH_FILES}
            for k, v in supplied.items():
                bad = check_artefact(k, v)
                if bad:
                    decision["note"] = (decision["note"] + " " if decision["note"] else "") + f"supplied file refused: {bad}"
                    supplied = None
                    break
                (rt.design / k).write_text(v)
        # owner hand edits: any change since the agent's snapshot (the agent does nothing while paused)
        edits = ownership.hand_edits(rt.design, snap["manifest"])
        if edits:
            rt.snaps.take(n, st.name, note="owner hand edit: " + ", ".join(edits)[:120], author="owner")
            ownership.record(rt.design, "owner", st.name, "supplied architecture" if supplied else "hand edit",
                             ", ".join(edits), n=n)
            if decision["decision"] in ("approve", "supply"):        # edited files are not yet gated: gates run again
                decision["decision"], hand_only = "edit", not decision["note"]
                decision["note"] = decision["note"] or "owner hand edit: " + ", ".join(edits)[:150]
    rv.write_page(rt.design, n, st.name, {**info, "approval": decision})
    hist.append({"n": n, "stage": st.name, "page": str(page), "passed": passed, "approval": decision,
                 "snapshot": snap["commit"], "visit": info["visits"], "used": dict(rt.meter.stage)})
    rv.write_index(rt.design, hist, rt.cfg.role_models())
    with (rt.design / "BUILD_NOTE.md").open("a") as f:
        f.write(f"\n## review {n:02d} {st.name}\n\n{decision['decision']} by {decision['by']}"
                f"{': ' + decision['note'] if decision.get('note') else ''} (gates {'pass' if passed else 'fail'})\n")
    upd: dict[str, Any] = {"history": hist, "hand_edit_only": False}
    if rt.cfg.review == "on" or hw_pause:
        who = _who(decision["by"])
        what = {"approve": "approved", "edit": "asked for changes", "rewind": f"rewound to stage {decision.get('to')}",
                "supply": "supplied the architecture"}.get(decision["decision"], decision["decision"])
        if decision["decision"] != "edit" or decision.get("note"):
            ownership.record(rt.design, who, st.name, what + (" (prompt)" if decision["decision"] == "edit" and not hand_only
                                                               else ""), decision.get("note", ""), n=n)
    elif passed:
        ownership.record(rt.design, "auto", st.name, "approved (review off)", "", n=n)
    # the architecture approval (Taylor addition 2): before any RTL, by the owner or, with review off, automatic
    if n == 1 and passed and decision["decision"] == "approve":
        who = _who(decision["by"])
        by_owner = any(r["who"] == "owner" and r["what"] in ("hand edit", "supplied architecture") and r["n"] == 1
                       for r in ownership.load(rt.design))
        rec = arch_mod.write_approval(rt.design, "auto" if who == "auto" else "owner", "owner" if by_owner else "agent",
                                      decision.get("note", ""))
        with (rt.design / "BUILD_NOTE.md").open("a") as f:
            f.write(f"\n## architecture approval\n\napproved ({rec['by']}); written by the {rec['source']}"
                    + (" (an owner contribution)" if rec["source"] == "owner" else "") + f"; sha256 {rec['sha256'][:12]}\n")
        ownership.record(rt.design, who, st.name, "architecture approved",
                         f"source: {rec['source']}" + (" (owner contribution)" if rec["source"] == "owner" else ""), n=n)
    if decision["decision"] == "rewind" and decision.get("to") is not None:
        to = int(decision["to"])
        r = rt.snaps.rewind(to)
        hist[-1]["rewind"] = {"to": to, "verified": r["verified"], "commit": r["commit"]}
        with (rt.design / "BUILD_NOTE.md").open("a") as f:        # the restored note predates this decision
            f.write(f"\n## review {n:02d} {st.name}\n\nrewind to stage {to} by {decision['by']}"
                    f"{': ' + decision['note'] if decision.get('note') else ''} (files verified: {r['verified']})\n")
        ownership.record(rt.design, _who(decision["by"]), st.name, f"rewound to stage {to}", decision.get("note", ""), n=n)
        rv.write_index(rt.design, hist, rt.cfg.role_models())
        upd.update(fails=[], note=decision.get("note", ""))
        return {**upd, "history": hist, "evidence": {}}
    if decision["decision"] == "edit":
        return {**upd, "note": decision.get("note", ""), "note_role": decision.get("role") or "", "hand_edit_only": hand_only,
                "fails": ["reviewer asked for changes"]}
    if hw_pause:
        return {**upd, "hw_approved": decision["decision"] == "approve"}
    return upd


def _stage_diff(rt: Runtime, n: int) -> list[dict]:
    """The RTL changes of this stage against the previous approved stage's snapshot (review page, brief 05d)."""
    prev = None
    for h in reversed(rt.snaps.records):
        if h["n"] < n or (h["n"] == n and False):
            prev = h["n"]
            break
    try:
        return rt.snaps.diff(prev, None, ("rtl/", "design.xdc", "spec.yaml", "architecture.yaml", "ARCHITECTURE.md"))
    except (KeyError, IndexError, OSError):
        return []


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
        from agent.graph.role_models import describe
        with (design / "BUILD_NOTE.md").open("a") as f:      # 05f: who ran which role, from the first snapshot on
            f.write(f"\n## models by role (profile {cfg.profile})\n\n{describe(cfg.role_models())}. "
                    f"Interview oracle: {cfg.model} (fixed). The stage machine is plain code.\n")
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
                                                     "run_limits": cfg.run_limits, "profile": cfg.profile,
                                                     "roles": cfg.roles or {}, "role_models": cfg.role_models(),
                                                     "oracle_model": cfg.model,
                                                     "isolation": type(runner).__name__}, indent=1))
    return rt


def checkpointer_for(run_dir: Path):
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver
    return SqliteSaver(sqlite3.connect(str(run_dir / "checkpoints.sqlite"), check_same_thread=False))


def _cc_calls(rt: Runtime) -> list[dict]:
    f = rt.run_dir / "claude_code_calls.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f.exists() else []


def knowledge_use(rt: Runtime) -> dict:
    """Which knowledge tools each role called in each stage, from the audit log (05f): call counts per tool, and for
    ``load_skill`` the section names and the skill files returned (so the device layers' use by the RTL writer shows)."""
    f = rt.design / "build" / "audit.jsonl"
    out: dict[str, dict] = {}
    for line in (f.read_text().splitlines() if f.exists() else []):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("tool") not in KNOWLEDGE_TOOLS or r.get("refused"):
            continue
        d = out.setdefault(f"{r.get('role') or '?'}/{r.get('stage')}", {})
        t = d.setdefault(r["tool"], {"calls": 0})
        t["calls"] += 1
        if r["tool"] == "load_skill":
            t.setdefault("sections", [])
            t.setdefault("skills", [])
            t.setdefault("empty_calls", 0)
            t["sections"] = sorted({*t["sections"], *(r.get("arguments") or {}).get("sections", [])})
            t["skills"] = sorted({*t["skills"], *(r.get("skills") or [])})
            t["empty_calls"] += not r.get("skills")                  # 05g: a call that returned no skill file
            if r.get("sections_empty"):
                t["sections_empty"] = sorted({*t.get("sections_empty", []), *r["sections_empty"]})
            if r.get("procedures_fallback"):
                t["procedures_fallback"] = sorted({*t.get("procedures_fallback", []), *r["procedures_fallback"]})
        elif r["tool"] == "search_docs":
            t.setdefault("hits", [])
            t["hits"] = sorted({*t["hits"], *(r.get("hits") or [])})[:40]
    return out


def knowledge_bank_status(rt: Runtime) -> dict:
    """Whether the frozen bank was reachable in this run's environment (05g): its path, how the path was chosen
    (``FDA_KNOWLEDGE`` or the sibling checkout), and the checkout's HEAD. The Claude Code arm's tool server resolves the
    same path, so one answer covers both harnesses."""
    from agent.core.bank import DEFAULT_BANK
    root = Path(DEFAULT_BANK)
    head = None
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return {"root": root.name, "chosen_by": "FDA_KNOWLEDGE" if os.environ.get("FDA_KNOWLEDGE") else "sibling checkout",
            "present": root.is_dir(), "loaded": getattr(getattr(rt, "session", None), "bank", None) is not None, "head": head}


def role_usage(rt: Runtime) -> list[dict]:
    f = rt.run_dir / "role_usage.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f.exists() else []


def usage_by(rows: list[dict], key: str) -> dict:
    """Sum role_usage rows by ``key`` (role or stage): calls, turns, tokens, wall_s, reported USD, plan estimate."""
    out: dict[str, dict] = {}
    for u in rows:
        d = out.setdefault(str(u[key]), {"calls": 0, "turns": 0, "tokens": 0, "wall_s": 0.0, "cost_usd": 0.0,
                                         "plan_cost_estimate_usd": 0.0})
        d["calls"] += 1
        d["turns"] += u["turns"]
        d["tokens"] += u["tokens"]
        d["wall_s"] = round(d["wall_s"] + u["wall_s"], 1)
        d["cost_usd"] = round(d["cost_usd"] + (u.get("cost_usd") or 0), 6)
        d["plan_cost_estimate_usd"] = round(d["plan_cost_estimate_usd"] + (u.get("plan_cost_estimate_usd") or 0), 4)
    return out


def usage_trace(rows: list[dict]) -> list[dict]:
    """The per-stage, per-role turn trace of a run (05g): one line per sub-agent call, in the order they ran."""
    keep = ("stage", "visit", "role", "repair", "turns_allowed", "turns", "ended", "wall_s", "tools", "refused", "files_written")
    return [{k: u.get(k) for k in keep} for u in rows]


def summary(rt: Runtime, state: dict) -> dict:
    hist = state.get("history") or []
    roles = rt.cfg.role_models()
    harnesses = sorted({r["harness"] for r in roles.values()})
    models = sorted({r["model"] for r in roles.values()})
    cc = "claude_code" in harnesses
    calls = _cc_calls(rt) if cc else []
    mixed = len(harnesses) > 1
    extra = {"harness": "mixed" if mixed else harnesses[0]}
    if cc:
        extra.update(claude_code_version=(calls[0]["claude_code_version"] if calls else None),
                     plan_cost_estimate_usd=round(sum(c.get("plan_cost_estimate_usd") or 0 for c in calls), 4),
                     oracle_model=rt.cfg.model)
    usage = role_usage(rt)
    return {"run_id": rt.run_id, "design": rt.cfg.name, "model": models[0] if len(models) == 1 else "per-role", **extra,
            "profile": rt.cfg.profile, "role_models": roles, "oracle_model": rt.cfg.model,
            "stage_overrides": __import__("agent.graph.role_models", fromlist=["x"]).stage_overrides(rt.cfg),
            "knowledge_use": knowledge_use(rt), "knowledge_bank": knowledge_bank_status(rt),
            "turn_trace": usage_trace(usage),
            "per_role": usage_by(usage, "role"), "per_stage": usage_by(usage, "stage"),
            "interview": rt.cfg.interview,
            "review": rt.cfg.review, "stages_visited": [h["n"] for h in hist],
            "loops": sum(1 for a, b in zip(hist, hist[1:]) if b["n"] <= a["n"] and not a.get("rewind")),
            "rewinds": [h["rewind"] for h in hist if h.get("rewind")],
            "tokens": rt.meter.run["tokens"], "cost_usd": rt.meter.run["usd"], "unreported_cost_calls": rt.meter.unreported,
            "turns": rt.meter.run["turns"], "wall_s": rt.meter.run["seconds"],
            "questions": (state.get("interview") or {}), "stop": state.get("stop"),
            "gates_last": {h["stage"]: h["passed"] for h in hist},
            "approvals": [{"n": h["n"], **h["approval"]} for h in hist],
            "bringup": ((state.get("evidence") or {}).get("bringup") or {}).get("pass")}
