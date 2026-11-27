"""The stage machine of docs/methodology.md ("The agent's stage machine") plus the V-stages of
docs/verification.md, as data and pure functions. The graph moves on only when :func:`exit_check` passes on
the flow's own gate output (never on the model's judgement); a failure goes to :func:`route_failure`, the
earliest stage that owns the cause.

No model calls here: everything is decided from tool results (``gates.json``, ``verif_gates.json``, the tools'
``ok`` flags), so CI tests it with recorded results.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from typing import Any

from agent.core.session import STAGES
from agent.graph.repair import verif_failures


@dataclass(frozen=True)
class Stage:
    n: int
    name: str
    tools: tuple[str, ...]            # core tools the stage's sub-agent may call (plus read/write/list/search)
    gates: tuple[str, ...]            # what exit_check requires (names below)
    loops_to: tuple[int, ...]         # stages a failure here may route to, earliest first
    limits: dict[str, float] = field(default_factory=dict)   # turns, seconds, usd per visit


FILES = ("read_file", "write_file", "list_files", "search_docs", "load_skill")
_L = {"turns": 30, "seconds": 1800, "usd": 0.40}

MACHINE: tuple[Stage, ...] = (
    Stage(0, "clarify", FILES, ("spec_signed",), (), {"turns": 20, "seconds": 900, "usd": 0.20}),
    Stage(1, "board-and-device-planning", (*FILES, "board_constraints", "check_constraints", "gates", "check", "gt_plan", "ip_lookup"),
          ("arch_note", "arch_yaml", "inventory"), (0,), _L),
    Stage(2, "rtl-design-creation", (*FILES, "lint", "simulate", "formal", "gates", "check", "gt_plan"),
          ("arch_approved", "lint", "model_contract", "simulate", "standards_rtl", "constants", "verif_v3", "stage_rtl", "report_gates"), (0, 1),
          {"turns": 80, "seconds": 3600, "usd": 0.80}),      # 05g: 60 -> 80, the tests role keeps a reserve (run.ROLE_TURN_RESERVE)
    Stage(3, "constraints", (*FILES, "board_constraints", "check_constraints", "build", "gates", "report", "check", "gt_plan"), ("constants", "constraints_post_synth", "report_gates"), (2,), _L),   # f2-stage3-io: + report
    Stage(4, "synthesis", (*FILES, "build", "gates", "report", "check"), ("stage_post_synth", "standards_post_synth", "report_gates"), (1, 2, 3), _L),
    Stage(5, "implementation", (*FILES, "build", "gates", "report", "check"), ("stage_post_place", "stage_post_route"), (6,), _L),
    Stage(6, "timing-closure", (*FILES, "build", "gates", "report", "check"), ("timing",), (3, 2, 5), _L),
    Stage(7, "power-closure", (*FILES, "build", "gates", "report", "check"), ("power",), (2, 0), _L),
    Stage(8, "drc-closure", (*FILES, "build", "gates", "report", "check"), ("drc",), (3, 2), _L),
    Stage(9, "configuration-and-debug", (*FILES, "build", "gates", "report", "check", "program", "bringup"),
          ("bitstream_base", "bitstream_ila", "bringup_ready", "bringup", "signoff"), (6, 2, 0), {"turns": 45, "seconds": 3600, "usd": 0.40}),   # 05g: 30 -> 45, 15 held for the tests role
)
assert tuple(s.name for s in MACHINE) == STAGES

RUN_LIMITS = {"turns": 300, "seconds": 6 * 3600, "usd": 3.00, "visits_per_stage": 4}

# 07a2 fix 4: stage 2 (verification) is the one stage whose single visit can spend many minutes in the simulator, and it
# repairs three roles (model, tests, RTL), so it gets more visits than the rest. Run 4's Icarus runs took ~6 min each and
# used up four visits while every repair was converging. Chosen over "count tool-error visits separately": a visit that
# ends in a tool error is not reliably told from one that ends in the agent's own failure, and a per-stage number is
# plain, testable, and bounded by the stage's turn and USD limits anyway.
STAGE_VISITS = {2: 6}


def visit_limit(stage: int, run_limits: dict) -> int:
    """How many times ``stage`` may be entered: the run's ``visits_per_stage``, or the stage's own number when larger."""
    base = int(run_limits["visits_per_stage"])
    return max(base, STAGE_VISITS.get(stage, 0)) if base >= RUN_LIMITS["visits_per_stage"] else base

#: Brief 234: the run turn cap scales with the design's size, measured in architecture blocks. A turn is one model call. From the 224 arm
#: (small designs of 4 to 6 blocks): the clean pass to stage 9 took 183 turns for 5 blocks (p4 run 2, 37 per block); runs that looped
#: used 169 to 300 (49 to 60 per block). So 60 per block covers a looping run and the floor stays the old 300. The ceiling is 15
#: blocks; the USD cap (not this one) is what limits a big design's spend.
TURNS_PER_BLOCK = 60
MAX_RUN_TURNS = 900


def run_turn_cap(blocks: int) -> int:
    """The run's turn cap for a design of ``blocks`` architecture blocks: ``max(300, 60 * blocks)``, at most 900."""
    return min(MAX_RUN_TURNS, max(int(RUN_LIMITS["turns"]), TURNS_PER_BLOCK * int(blocks)))


def visits_after_route(visits: dict, n: int, target: int) -> dict:
    """Brief 234: the visit counts after stage ``n`` failed and was routed back to ``target`` (< n).

    The stages the loop passes again (``target`` + 1 .. ``n`` - 1) start from zero: their earlier visits were spent repairing a
    failure the later stage's change has now replaced, and entering them again is a re-check, not another repair attempt (p4 run 1,
    20261125-174731-a2e5: stage 3 used its four visits on constraints, passed, then stage 4 sent the run back through stage 3 and the
    fifth entry was refused before any gate ran). The two stages that are the loop itself keep their counts: ``n`` (the one that
    failed) and ``target`` (the one asked to change what failed). So a loop that does not converge still ends: the highest stage in
    any cycle is only reset by a failure of a still higher stage, which is not in the cycle, so its count only grows, and a route
    back to one stage (brief 213's run, stage 2 to stage 1 four times) still stops on that stage's limit. A forward move or a retry
    of the same stage changes nothing."""
    if target >= n:
        return dict(visits)
    return {k: v for k, v in visits.items() if not target < int(k) < n}


# gate name -> the stage names in flow/gates.py output it reads
_FLOW_STAGES = {"stage_rtl": ["rtl"], "stage_post_synth": ["post_synth"], "stage_post_place": ["post_place"],
                "stage_post_route": ["post_route"], "constraints_post_synth": ["post_synth"],
                "bitstream_base": ["bitstream"]}
_ROUTE_RULES = {"setup", "hold", "pulse_width"}
# brief 20: the exception check (flow/exceptions_check.py) joins the constraints and timing gates where the build has it
_EXC_GATES = {"post_synth": "post_synth_exceptions_clean", "post_route": "exceptions_clean"}
# brief 20 part B: the I/O check (flow/io_check.py) likewise
_IO_GATES = {"post_synth": "post_synth_io_constraints_clean", "post_route": "io_timing_clean"}


def _with_exceptions(gates: dict | None, flow_stage: str, only: set[str]) -> set[str]:
    st = ((gates or {}).get("stages") or {}).get(flow_stage) or {}
    have = st.get("gates") or {}
    return only | {n for n in (_EXC_GATES[flow_stage], _IO_GATES[flow_stage]) if n in have}


def io_text(st: dict, limit: int = 6) -> str:
    """The failing findings of a stage's I/O check, one clause each (rule, XDC file:line, the finding)."""
    fails = ((st.get("io_timing") or {}).get("failures") or [])
    out = []
    for f in fails[:limit]:
        where = f"{f['file']}:{f['line']}" if f.get("file") else ""
        out.append(" ".join(x for x in (f["rule"], where, (f.get("text") or ""), (f.get("message") or "")[:240]) if x))
    more = f"; ... {len(fails) - limit} more" if len(fails) > limit else ""
    return "; ".join(out) + more


def exceptions_text(st: dict, limit: int = 6) -> str:
    """The failing exceptions of a stage's exception check, one clause each (rule, XDC file:line, Vivado's text)."""
    fails = ((st.get("exceptions") or {}).get("failures") or [])
    out = []
    for f in fails[:limit]:
        where = f"{f['file']}:{f['line']}" if f.get("file") else (f"position {f['position']}" if f.get("position") else "")
        viv = f.get("vivado") or {}
        msg = viv.get("message") or viv.get("detail") or " ".join(f"{k}={v}" for k, v in viv.items() if v)
        out.append(" ".join(x for x in (f["rule"], where, (f.get("text") or ""), msg[:240]) if x))
    more = f"; ... {len(fails) - limit} more" if len(fails) > limit else ""
    return "; ".join(out) + more
_POWER_RULES = {"power_junction_ok"}
_DRC_RULES = {"drc_clean", "cdc_no_critical", "methodology_no_critical"}


def _stage_pass(gates: dict | None, flow_stage: str, only: set[str] | None = None,
                skip: set[str] | None = None, label: str | None = None) -> tuple[bool, list[str]]:
    """``label`` names the build when it is not the base one (68F: "bitstream: did not run" alone did not say which
    build; the base build's own record had passed). The wording keeps "did not run": ``classify`` reads it."""
    st = ((gates or {}).get("stages") or {}).get(flow_stage) or {}
    if not st.get("ran"):
        who = f"{flow_stage} ({label})" if label else flow_stage
        err = (gates or {}).get("error")
        return False, [f"{who}: did not run" + (f" (its gates record is unreadable: {str(err)[:160]})" if err else
                                                 " (no gates record)" if not gates else "")]
    g = st.get("gates") or {}
    if only is not None and not only <= set(g):
        return False, [f"{flow_stage}:{n} missing" for n in sorted(only - set(g))]
    bad = [f"{flow_stage}:{n}" for n, ok in g.items()
           if (only is None or n in only) and not (skip and n in skip) and not ok]
    if st.get("unconstrained_ports"):          # 05g follow-up: the repair visit sees WHICH ports, not only the gate's name
        from flow.gates import unconstrained_text
        bad = [b + (f" ({unconstrained_text(st['unconstrained_ports'])})" if "unconstrained" in b else "") for b in bad]
    if st.get("exceptions"):                   # brief 20: which exception, where in the XDC, and Vivado's words
        bad = [b + (f" ({exceptions_text(st)})" if b.endswith("exceptions_clean") else "") for b in bad]
    if st.get("resets"):                       # brief 71: which reset rule, where, and the one-line fix
        rs_ = st["resets"]
        txt = "; ".join(f"{f['rule']} {f['code']} {f['where']}: {f['message'][:160]}" for f in (rs_.get("findings") or [])[:6]) \
            or str(rs_.get("why", ""))[:200]
        bad = [b + (f" ({txt})" if b.endswith("resets_clean") else "") for b in bad]
    if st.get("io_timing"):                    # brief 20 part B: which delay, where in the XDC, and why
        bad = [b + (f" ({io_text(st)})" if b.endswith(("io_timing_clean", "io_constraints_clean")) else "") for b in bad]
    xp = (gates or {}).get("xprobe")           # brief 18: present only for a build run with FDA_XPROBE=1
    if xp and not xp.get("error"):
        for b in list(bad):
            kind = {"post_route:setup": "setup", "post_route:hold": "hold"}.get(b)
            bad += [f"cross-probe: {p['text']}" for p in xp.get("paths", []) if kind and p["kind"] == kind][:2]
    return not bad, bad


def standards_stage(res: dict | None, stage: str) -> tuple[bool, list[str]]:
    """The failing rules of the design-standards checker (flow/standards_check.py) for one stage, one line per finding.
    A checkable rule that did not run counts as failed."""
    if not res or "rules" not in res:
        return False, ["standards: the checker produced no result"]
    why = []
    for r in res["rules"]:
        if r.get("stage") != stage:
            continue
        if r["status"] == "fail":
            why += [f"standards {r['id']}: {f['file']}:{f['line']}: {f['message']}" for f in r["findings"][:12]]
        elif r["status"] == "not_run":
            why.append(f"standards {r['id']}: not checked ({r.get('why_not_run')})")
    return not why, why


def signoff_failures(v: dict | None) -> tuple[bool, list[str]]:
    """Sign-off: every proof method has passing evidence (flow/verif_gates.py traceability table)."""
    so = ((v or {}).get("stages") or {}).get("SIGNOFF")
    if not so:
        return False, ["sign-off: the verification gates produced no traceability table"]
    if so.get("pass"):
        return True, []
    rows = [r for r in (v.get("traceability") or []) if r["result"] != "pass"]
    return False, [f"sign-off: {r['requirement']} {r['method']} {r['artefact']}: {r['result']} ({r['detail']})" for r in rows[:30]]


def constants_stage(c: dict | None) -> tuple[bool, list[str]]:
    """The derived-constants gate (brief 82P4; flow/derived_constants.py, rule HDL-ORC-01). A blocking finding (a design ID
    bound to a value that contradicts the spec's quoted ID, a ``create_clock`` period that contradicts the board file) fails
    the stage. Advice findings (an unresolved binding, a spec identity word with no matching literal) never fail it. An
    evidence record with no ``constants`` key (the check was not run, or errored) does not fail: the check is a gate on a
    contradiction it found, not on its own availability; the run record says whether it ran."""
    if not c:
        return True, []
    fs = [f for f in (c.get("findings") or []) if f.get("blocking")]
    return not fs, [f"constants {f['code']} {f.get('where', '')}: {f['message']}" + _spec_holder_tag(c, f) for f in fs]


def _spec_holder_tag(c: dict, f: dict) -> str:
    """Brief 82P6: a CONST-ID-01 that persisted into a later visit, whose wrong value is also in spec.yaml, is the clarify stage's
    to fix (spec.yaml is its output): the failure text says so and ``classify`` routes it to stage 0."""
    if (f.get("code") == "CONST-ID-01" and c.get("persisted")
            and any(h.get("role") == "spec" for h in (f.get("holders") or []))):
        return " [the wrong value is also held by spec.yaml, which the clarify stage owns]"
    return ""


#: brief 209a: the report checks (brief 204a) that block. Their findings are the check suite's own (``flow.checks``); every other
#: finding of those checks is an advisory and never blocks.
REPORT_GATE_CODES = ("RPT-LL-02", "RPT-CS-02", "RPT-LOG-03")


def report_gates_stage(r: dict | None) -> tuple[bool, list[str]]:
    """The report gate (brief 209a): a blocking RPT-LL-02 (a setup path that fails even with no net delay: the design cannot close at
    this clock), RPT-CS-02 (control sets over 15 % of capacity) or RPT-LOG-03 (a generic the build sets that the top lacks) sends
    the run back to the Designer, with the finding's own text as the failure. ``r`` is ``agent.graph.run.report_gates_eval``'s
    record; ``None`` (the checks did not run, or the build wrote no synthesis report) is not a failure: like the constants gate it
    is a gate on a finding, not on its own availability. Advisories are in ``r['advisories']`` for the Designer's feedback only."""
    if not r:
        return True, []
    fs = [f for f in (r.get("findings") or []) if f.get("blocking") and f.get("code") in REPORT_GATE_CODES]
    return not fs, [f"report gate {f['code']} {f.get('where', '')}: {f.get('message', '')}" + (f" Fix: {f['fix']}" if f.get("fix") else "")
                    for f in fs]


def failed_gates(stage: Stage, ev: dict[str, Any]) -> list[str]:
    """Brief 246: the names of the gates of ``stage`` that fail on ``ev`` (each gate checked on its own), in the stage's order. For a standards gate the
    failing rule ids are appended (``standards_rtl:STD-RST-01``), so two different rules do not look like the same failure. Used for the failure signature."""
    names: list[str] = []
    for g in stage.gates:
        try:
            ok, why = exit_check(dataclasses.replace(stage, gates=(g,)), ev)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if ok:
            continue
        ids = sorted({m for w in why for m in re.findall(r"\bstandards (STD-[A-Z]+-\d+)", str(w))}) if g in ("standards_rtl", "standards_post_synth") else []
        names.append(g + (":" + ",".join(ids) if ids else ""))
    return names


def exit_check(stage: Stage, ev: dict[str, Any]) -> tuple[bool, list[str]]:
    """``ev`` holds the latest tool results the graph collected in this stage: ``spec`` (parsed spec.yaml),
    ``signed_off`` (bool, from the review/interview), ``lint``/``simulate`` (tool results), ``gates_base`` /
    ``gates_ila`` (flow/gates.py JSON), ``verif`` (verif_gates JSON), ``bringup`` (bring-up JSON), ``arch`` (bool,
    the architecture note exists), ``inventory`` (check_constraints result). Returns (pass, failures)."""
    fails: list[str] = []
    for g in stage.gates:
        ok, why = True, []
        if g == "spec_signed":
            spec = ev.get("spec") or {}
            errs = list(ev.get("spec_errors") or [])
            ok = bool(spec) and not spec.get("open_questions") and bool(ev.get("signed_off")) and not errs
            why = [] if ok else (errs or ["spec.yaml missing, has open questions, or not signed off"])
        elif g == "arch_note":
            ok, why = bool(ev.get("arch")), ["no architecture note (ARCHITECTURE.md)"]
        elif g == "arch_yaml":
            r = ev.get("arch_check") or {}
            ok, why = bool(r.get("ok")), ["architecture.yaml: " + e for e in (r.get("errors") or ["not checked"])]
        elif g == "arch_approved":
            a = ev.get("arch_approval") or {}
            ok, why = bool(a.get("ok")), ["architecture not approved: " + str(a.get("why") or "no approval record")]
        elif g in ("standards_rtl", "standards_post_synth"):
            ok, why = standards_stage(ev.get("standards"), "rtl" if g == "standards_rtl" else "post_synth")
        elif g == "signoff":
            ok, why = signoff_failures(ev.get("signoff"))
        elif g == "constants":
            ok, why = constants_stage(ev.get("constants"))
        elif g == "report_gates":
            ok, why = report_gates_stage(ev.get("report_gates"))
        elif g == "inventory":
            r = ev.get("inventory") or {}
            ok, why = bool(r.get("ok")), ["check_constraints failed"]
        elif g == "model_contract":
            c = ev.get("contract") or {}
            ok, why = bool(c.get("ok")), ["model contract: " + str(c.get("error") or "not checked")[-600:]]
        elif g in ("lint", "simulate"):
            ok, why = bool((ev.get(g) or {}).get("ok")), [f"{g} not passing"]
        elif g == "verif_v3":
            v = ev.get("verif") or {}
            need = ev.get("verif_level") or "V3"
            ok = (v.get("reached") or "") >= need and v.get("reached") is not None
            why = verif_failures(v, need) or [f"verification at {v.get('reached')!r}, needs {need}"]
        elif g == "constraints_post_synth":
            ok, why = _stage_pass(ev.get("gates_base"), "post_synth",
                                  only=_with_exceptions(ev.get("gates_base"), "post_synth",
                                                        {"post_synth_no_unconstrained_endpoints",
                                                         "post_synth_methodology_no_critical"}))
        elif g == "timing":
            ok, why = _stage_pass(ev.get("gates_base"), "post_route", only=_with_exceptions(ev.get("gates_base"), "post_route",
                                                                                           _ROUTE_RULES))
        elif g == "power":
            ok, why = _stage_pass(ev.get("gates_base"), "post_route", only=_POWER_RULES)
            if ok and ev.get("power_ok") is False:
                ok, why = False, ["power_ok failed for the board's power source"]
        elif g == "drc":
            ok1, w1 = _stage_pass(ev.get("gates_base"), "post_synth", only={"post_synth_drc_clean"})
            ok2, w2 = _stage_pass(ev.get("gates_base"), "post_route", only=_DRC_RULES)
            ok, why = ok1 and ok2, w1 + w2
        elif g == "bitstream_ila":
            ok, why = _stage_pass(ev.get("gates_ila"), "bitstream", label="debug build with the ILA")
        elif g == "bringup_ready":
            r = ev.get("bringup_ready") or {}
            ok = bool(r.get("ok"))
            why = ["bring-up artefacts: " + p for p in (r.get("problems") or ["not checked"])]
        elif g == "bringup":
            b = ev.get("bringup") or {}
            ok = b.get("pass") is True
            why = [f"bring-up failed at {b.get('failed_step')!r}" + (f": {b['why']}" if b.get("why") else "")]
        elif g in _FLOW_STAGES:
            ok, why = _stage_pass(ev.get("gates_base"), _FLOW_STAGES[g][0])
            if g == "stage_post_synth" and not ok:
                st = ((ev.get("gates_base") or {}).get("stages") or {}).get("post_synth") or {}
                if st.get("resource_sanity") and not st["resource_sanity"]["pass"]:
                    from flow.architecture import resource_failures
                    why = why + resource_failures(st["resource_sanity"])
            if g == "stage_post_synth" and ev.get("plan_fails"):      # closure-loop hook: a planned DSP/BRAM not inferred
                ok, why = False, why + list(ev["plan_fails"])
        else:
            raise KeyError(g)
        if not ok:
            fails += why
    return not fails, fails


def route_failure(stage: Stage, cause: str | None) -> int:
    """Where a failed stage goes back to. ``cause`` is a classification taken from tool output (never the
    model's choice): ``spec`` -> 0, ``rtl`` -> 2, ``constraints`` -> 3, ``impl`` -> 5, ``timing`` -> 6, else the
    stage itself (another attempt). The target must be one the stage machine allows, else the stage retries."""
    target = {"spec": 0, "arch": 1, "rtl": 2, "constraints": 3, "impl": 5, "timing": 6, "bringup": 9}.get(cause or "", stage.n)
    return target if target in stage.loops_to or target == stage.n else stage.n


# What a pytest harness or test-file failure looks like in a bring-up step's "why" (never a hardware result).
_HARNESS_MARKERS = ("ModuleNotFoundError", "ImportError", "SyntaxError", "NameError", "ERROR collecting",
                    "unrecognized arguments", "Labtools 27-3239", "Labtools 27-3241",
                    "too many comparators", "no tests/test_", "cannot load", "fixture '")


def classify(stage: Stage, fails: list[str]) -> str | None:
    """Map gate failures to the owning cause, following methodology.md's "Loops back to" column."""
    text = " ".join(fails)
    if "report gate RPT-" in text:
        return "rtl"                     # brief 209a: a path that cannot close, too many control sets or an unused generic is the RTL's
    if "constants CONST-CLK" in text:
        return "constraints"             # a clock period against the board file is the constraints' to fix
    if "constants CONST-ID-01" in text and "held by spec.yaml" in text:
        return "spec"                    # 82P6: the wrong value persisted and spec.yaml carries it: the clarify stage's to correct
    if "constants CONST-" in text:
        return "rtl"                     # a constant the RTL binds against the spec: the RTL's (the spec text is not at fault)
    if "architecture not approved" in text:
        return "arch"                    # an approval is the owner's (or auto): back to the architecture stage
    if stage.n == 4 and "plan: " in text:
        return "rtl"                     # closure loop: the RTL did not follow the design-time plan's templates
    if stage.n == 4 and "resources:" in text:
        return resource_cause(fails)
    if stage.n == 4 and "standards STD-" in text:
        return "constraints"             # CDC and clock-network findings after synthesis are constraint-shaped
    if stage.n == 2 and "standards STD-" in text:
        # a finding in the (frozen) architecture.yaml is the architecture's to fix, not the Designer's
        return "arch" if all("architecture.yaml:" in f for f in fails if "standards STD-" in f) else "rtl"
    if stage.n == 2 and "model" in text and "spec" in text:
        return "spec"
    if stage.n in (4, 8) and any(k in text for k in ("unconstrained", "TIMING", "XDC", "methodology")):
        return "constraints"
    if stage.n == 4:
        return "rtl"
    if stage.n == 5:
        return "timing"
    if stage.n == 6:
        return "constraints" if "unconstrained" in text or "cdc" in text else "rtl"
    if stage.n == 7:
        return "rtl"
    if stage.n == 9:
        if "bring-up artefacts" in text or "hardware-bringup" in text:
            return "bringup"             # missing or malformed bring-up files: their own writer fixes them, not stage 2
        if "bring-up failed at" in text and any(k in text for k in _HARNESS_MARKERS):
            return "bringup"             # an import/collection error in the UART tests is the tests role's, not hardware's
        if "did not run" in text:       # a build that produced nothing (for example no probes.yaml): another attempt here
            return None
        return "timing" if "bitstream" in text else ("rtl" if "bring-up" in text else None)
    return None


def resource_cause(fails: list[str]) -> str:
    """Where a resource-sanity failure goes (brief 05d): ``rtl`` when the result looks like unintended logic - a RAM or
    DSP the architecture predicted that did not map while LUTs/FFs are over (a RAM that became LUTs), or a latch was
    named; otherwise ``arch``: the prediction was wrong."""
    rows = [f for f in fails if f.startswith("resources:")]
    below_hard = any(("bram_tile" in f or "dsp" in f) and "(below" in f for f in rows)
    above_logic = any(("lut" in f or "ff" in f) and "(above" in f for f in rows)
    if (below_hard and above_logic) or any("latch" in f.lower() for f in fails):
        return "rtl"
    return "arch"
