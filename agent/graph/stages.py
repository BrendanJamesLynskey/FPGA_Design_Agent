"""The stage machine of docs/methodology.md ("The agent's stage machine") plus the V-stages of
docs/verification.md, as data and pure functions. The graph moves on only when :func:`exit_check` passes on
the flow's own gate output (never on the model's judgement); a failure goes to :func:`route_failure`, the
earliest stage that owns the cause.

No model calls here: everything is decided from tool results (``gates.json``, ``verif_gates.json``, the tools'
``ok`` flags), so CI tests it with recorded results.
"""

from __future__ import annotations

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
    Stage(1, "board-and-device-planning", (*FILES, "board_constraints", "check_constraints", "gates"),
          ("arch_note", "arch_yaml", "inventory"), (0,), _L),
    Stage(2, "rtl-design-creation", (*FILES, "lint", "simulate", "formal", "gates"),
          ("arch_approved", "lint", "model_contract", "simulate", "standards_rtl", "verif_v3", "stage_rtl"), (0, 1),
          {"turns": 60, "seconds": 3600, "usd": 0.80}),
    Stage(3, "constraints", (*FILES, "board_constraints", "check_constraints", "build", "gates"), ("constraints_post_synth",), (2,), _L),
    Stage(4, "synthesis", (*FILES, "build", "gates", "report"), ("stage_post_synth", "standards_post_synth"), (1, 2, 3), _L),
    Stage(5, "implementation", (*FILES, "build", "gates", "report"), ("stage_post_place", "stage_post_route"), (6,), _L),
    Stage(6, "timing-closure", (*FILES, "build", "gates", "report"), ("timing",), (3, 2, 5), _L),
    Stage(7, "power-closure", (*FILES, "build", "gates", "report"), ("power",), (2, 0), _L),
    Stage(8, "drc-closure", (*FILES, "build", "gates", "report"), ("drc",), (3, 2), _L),
    Stage(9, "configuration-and-debug", (*FILES, "build", "gates", "report", "program", "bringup"),
          ("bitstream_base", "bitstream_ila", "bringup_ready", "bringup", "signoff"), (6, 2, 0), {"turns": 30, "seconds": 3600, "usd": 0.40}),
)
assert tuple(s.name for s in MACHINE) == STAGES

RUN_LIMITS = {"turns": 300, "seconds": 6 * 3600, "usd": 3.00, "visits_per_stage": 4}

# gate name -> the stage names in flow/gates.py output it reads
_FLOW_STAGES = {"stage_rtl": ["rtl"], "stage_post_synth": ["post_synth"], "stage_post_place": ["post_place"],
                "stage_post_route": ["post_route"], "constraints_post_synth": ["post_synth"],
                "bitstream_base": ["bitstream"]}
_ROUTE_RULES = {"setup", "hold", "pulse_width"}
_POWER_RULES = {"power_junction_ok"}
_DRC_RULES = {"drc_clean", "cdc_no_critical", "methodology_no_critical"}


def _stage_pass(gates: dict | None, flow_stage: str, only: set[str] | None = None,
                skip: set[str] | None = None) -> tuple[bool, list[str]]:
    st = ((gates or {}).get("stages") or {}).get(flow_stage) or {}
    if not st.get("ran"):
        return False, [f"{flow_stage}: did not run"]
    g = st.get("gates") or {}
    if only is not None and not only <= set(g):
        return False, [f"{flow_stage}:{n} missing" for n in sorted(only - set(g))]
    bad = [f"{flow_stage}:{n}" for n, ok in g.items()
           if (only is None or n in only) and not (skip and n in skip) and not ok]
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
                                  only={"post_synth_no_unconstrained_endpoints", "post_synth_methodology_no_critical"})
        elif g == "timing":
            ok, why = _stage_pass(ev.get("gates_base"), "post_route", only=_ROUTE_RULES)
        elif g == "power":
            ok, why = _stage_pass(ev.get("gates_base"), "post_route", only=_POWER_RULES)
            if ok and ev.get("power_ok") is False:
                ok, why = False, ["power_ok failed for the board's power source"]
        elif g == "drc":
            ok1, w1 = _stage_pass(ev.get("gates_base"), "post_synth", only={"post_synth_drc_clean"})
            ok2, w2 = _stage_pass(ev.get("gates_base"), "post_route", only=_DRC_RULES)
            ok, why = ok1 and ok2, w1 + w2
        elif g == "bitstream_ila":
            ok, why = _stage_pass(ev.get("gates_ila"), "bitstream")
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


def classify(stage: Stage, fails: list[str]) -> str | None:
    """Map gate failures to the owning cause, following methodology.md's "Loops back to" column."""
    text = " ".join(fails)
    if "architecture not approved" in text:
        return "arch"                    # an approval is the owner's (or auto): back to the architecture stage
    if stage.n == 4 and "resources:" in text:
        return resource_cause(fails)
    if stage.n == 4 and "standards STD-" in text:
        return "constraints"             # CDC and clock-network findings after synthesis are constraint-shaped
    if stage.n == 2 and "standards STD-" in text:
        # a finding in the (frozen) architecture.yaml is the architecture's to fix, not the RTL writer's
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
