#!/usr/bin/env python3
"""The requirements readiness gate, the code half (brief 227): every check that needs no model.

Stage 0 builds requirements with the user until they are ready; stage 1 onwards builds and verifies them. This module is the
mechanical part of "ready" (the model roles are in ``agent/graph/readiness.py``). Everything here is code: a verdict is never a model's.

A requirement row is a mapping of ``spec.yaml`` ``requirements``: ``id``, ``text`` (layer L1, EARS-style English the user confirms) and
``proof`` as before (brief 210), plus optional fields this brief adds. At ``standard`` only L1 and the core checks apply; at ``strict`` the
three layers and the show-back packet are required (research 228 section 8, accepted):

- ``modal``: ``shall`` (mandatory, verified), ``should`` (desirable: promoted to shall or recorded as not verified) or ``will`` (descriptive,
  never verified);
- ``kind``: ``interface | timing | protocol | functional | reset | budget | board | other``;
- ``l2``: FRETish-shaped fields ``{scope, condition, component, timing: {kind, n, clock, from}, response}`` (layer L2);
- ``l3``: ``{sva: true}`` (a property generated from L2 by ``flow/sva_req.py``) or ``{check: <name>}`` or ``{sim_only: <why>}``;
- ``method``: ``Test | Analysis | Inspection | Demonstration`` and ``evidence``: what will be named as the evidence;
- ``trace_up``: the id of a user goal (``goals`` in spec.yaml) the requirement serves; ``source``: where it came from;
- ``worked``: worked numbers, ``never``: one "must never happen" example;
- ``validated_by_user``: a record ``{who, when, shown}`` (validation: the right design) kept apart from ``verified`` (verification: built right);
  ``derived``: true for a default the agent chose that became a requirement (it must be validated);
- ``design_constraint``: true when an implementation-specific requirement is a real constraint the user kept;
- ``compliance``: the reviewer's early assessment ``compliant | partial | non_compliant | tbc`` with ``risk: {owner, mitigation}``.

The six properties of a good requirement (necessary, verifiable, achievable, traceable, unique, simple and clear) are checked in
:func:`six_properties`; the sources are cited in ``docs/agent.md`` (INCOSE-style requirement-quality practice, research 228, and the
MicroZed Chronicles article of 2026-11-26 "Getting the Foundations Right", cited, not copied).

The checks return :class:`Problem` rows. Each has a ``question``: a missing item is a question to the user, never a silent default.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

SCHEMA = "fpga-force/readiness/v1"
STATE_DIR = ("build", "requirements")
READINESS_FILE = "readiness.json"
FROZEN_FILE = "frozen.json"
LEDGER_FILE = "req_ids.json"                    # every id ever used in this design: an id is never reused
ANSWERS_FILE = "requirements_answers.yaml"      # a person's answers to the stage-0 questions, by question id
CONFIRMATIONS_FILE = "requirements_confirmations.yaml"

MODALS = ("shall", "should", "will")
KINDS = ("interface", "timing", "protocol", "functional", "reset", "budget", "board", "other")
METHODS = ("Test", "Analysis", "Inspection", "Demonstration")
COMPLIANCE = ("compliant", "partial", "non_compliant", "tbc")
TIMING_KINDS = ("immediately", "within", "after", "for", "until", "always", "eventually")
NEEDS_N = ("within", "after", "for")
L2_FIELDS = ("scope", "condition", "component", "timing", "response")
#: layer-2 and layer-3 are required at strict for these kinds (research 228 8(a)); the others are tables or numeric rows
FORMAL_KINDS = ("timing", "protocol", "reset", "functional")
#: spec.yaml ``proof`` methods (brief 53) -> the verification method of this brief
PROOF_TO_METHOD = {"simulation": "Test", "formal": "Analysis", "analysis": "Analysis", "hardware": "Demonstration"}
LEVELS = ("standard", "strict")
#: a scope the user states as "everywhere": it must still be written (an omitted scope is the usual FRETish mistake: the property then holds forever when the user meant after reset)
NO_SCOPE = ("always", "any time", "anytime", "at all times", "whole operation", "everywhere")


@dataclass
class Problem:
    """One thing that stops a requirement being ready. ``blocking`` problems stop the gate at the level shown; advisory ones are listed."""
    id: str                      # the requirement id, or "interface", "set"
    code: str                    # RDY-<check>-<n>
    text: str                    # what is wrong
    question: str                # what to ask the user (or the oracle)
    level: str = "standard"      # the lowest level at which it blocks
    topic: str = "requirement"   # the reviewer checklist topic it belongs to, if any
    blocking: bool = True
    repair: bool = False         # a defect the agent can fix from the rows as written (split a compound row, drop a duplicate): it is repaired, not put to the user

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "code": self.code, "text": self.text, "question": self.question, "level": self.level, "topic": self.topic,
                "blocking": self.blocking, "repair": self.repair}

    def blocks(self, level: str) -> bool:
        return self.blocking and LEVELS.index(level) >= LEVELS.index(self.level)


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reqs_of(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in spec.get("requirements") or [] if isinstance(r, dict) and r.get("id")]


def norm(text: Any) -> str:
    return " ".join(str(text or "").split())


# ---- modal and method ----------------------------------------------------------------------------------------------------------------
_MODAL_RX = re.compile(r"\b(shall|should|will)\b", re.I)


def modal_of(row: dict[str, Any]) -> str | None:
    """``shall`` / ``should`` / ``will`` from the ``modal`` field, else the first such word of the text; None when neither says."""
    m = str(row.get("modal") or "").strip().lower()
    if m in MODALS:
        return m
    f = _MODAL_RX.search(str(row.get("text") or ""))
    return f.group(1).lower() if f else None


def method_of(row: dict[str, Any]) -> str | None:
    """The verification method: ``method`` as written (Test, Analysis, Inspection or Demonstration), else the first of ``proof`` mapped
    (simulation -> Test, formal and analysis -> Analysis, hardware -> Demonstration). Inspection is never inferred: it is stated."""
    m = str(row.get("method") or "").strip().capitalize()
    if m in METHODS:
        return m
    for p in row.get("proof") or []:
        if str(p) in PROOF_TO_METHOD:
            return PROOF_TO_METHOD[str(p)]
    return None


def is_verified_kind(row: dict[str, Any]) -> bool:
    """A SHALL row is mandatory and verified; a SHOULD row is verified only once promoted; a WILL row is never verified. A row with no modal word
    is treated as SHALL (the rows of briefs 53 and 210 never said)."""
    m = modal_of(row)
    return m in (None, "shall")


# ---- implementation-specific wording (practice 3) --------------------------------------------------------------------------------------
_IMPL = re.compile(
    r"\b(?:use|using|uses|instantiate|instantiates|implement(?:ed)? (?:with|using|as|in)|built (?:with|from|on)|based on|via the|through the) "
    r"(?:an? |the )?(?:xilinx |amd |vivado )?(?:[A-Za-z0-9_]*(?:VDMA|MIG|DMA|primitive|BRAM|DSP48\w*|URAM|LUTRAM|SRL\w*|MMCM|PLL|BUFG\w*|IDELAY\w*|ISERDES\w*|OSERDES\w*|"
    r"GT[HYXP]\w*|ILA|state machine|shift register|ring buffer|systolic|lookup table|block ram)\b)", re.I)


def implementation_specific(text: str) -> str | None:
    """The phrase that names an implementation rather than a function (``use the VDMA and MIG``), or None."""
    m = _IMPL.search(norm(text))
    return m.group(0) if m else None


# ---- the six properties (practice 1) ----------------------------------------------------------------------------------------------------
def text_sha(text: str) -> str:
    return hashlib.sha256(norm(text).encode()).hexdigest()[:16]


def six_properties(row: dict[str, Any], spec: dict[str, Any], *, level: str = "standard", ledger: dict[str, Any] | None = None) -> list[Problem]:
    """necessary, verifiable, achievable, traceable, unique, simple and clear: one problem per property that fails. ``necessary``, ``achievable`` and
    ``traceable`` block at strict only (they need the goals, the source record and the reviewer's assessment, which standard does not require)."""
    from agent.graph import spec_schema as SS
    rid, text = str(row["id"]), norm(row.get("text"))
    out: list[Problem] = []
    for msg in SS.requirement_quality_errors({"requirements": [{"id": rid, "text": text}]}):     # simple and clear: atomic, no vague word
        vague = " is vague " in msg
        out.append(Problem(rid, "RDY-CLEAR-01", msg, f"Please restate {rid} so that one statement can be checked: {msg.split(': ', 1)[-1]}", repair=not vague))
    if modal_of(row) is None and level == "strict":
        out.append(Problem(rid, "RDY-MODAL-01", "no SHALL, SHOULD or WILL", f"Is {rid} mandatory (SHALL: verified), desirable (SHOULD: reviewed with you) or "
                           "descriptive (WILL: never verified)?", level="strict"))
    if method_of(row) is None and is_verified_kind(row):                                           # verifiable: a method and named evidence
        out.append(Problem(rid, "RDY-VER-01", "no verification method (Test, Analysis, Inspection or Demonstration)",
                           f"How should {rid} be verified: Test, Analysis, Inspection or Demonstration, and by what evidence?"))
    elif level == "strict" and not norm(row.get("evidence")) and is_verified_kind(row):
        out.append(Problem(rid, "RDY-VER-02", "the evidence is not named (simulation result, timing report, test report, board result)",
                           f"What evidence will show {rid} is met (for example a named test, a timing report line, a board reading)?", level="strict"))
    if not (row.get("source") or row.get("origin")) and level == "strict":                         # traceable: where it came from
        out.append(Problem(rid, "RDY-TRACE-01", "no source: a line of the request, an answered question, a confirmed default or a waiver",
                           f"Where does {rid} come from (a line of your request, an answer, or a default you confirm)?", level="strict"))
    goals = {str(g.get("id")) for g in spec.get("goals") or [] if isinstance(g, dict) and g.get("id")}
    tu = row.get("trace_up")                                                                       # necessary: traces up to a user goal
    if level == "strict" and modal_of(row) != "will":
        if not tu:
            out.append(Problem(rid, "RDY-NEC-01", "does not trace up to a user goal", f"Which of your goals does {rid} serve? If none, should it be dropped?", level="strict"))
        elif goals and str(tu) not in goals:
            out.append(Problem(rid, "RDY-NEC-02", f"trace_up {tu!r} is not a goal of this design ({', '.join(sorted(goals)) or 'none'})",
                               f"{rid} claims to serve goal {tu}, which is not listed. Which goal does it serve?", level="strict"))
    comp = row.get("compliance")                                                                   # achievable: the early compliance assessment
    if level == "strict" and is_verified_kind(row):
        c = comp.get("status") if isinstance(comp, dict) else comp
        if c not in COMPLIANCE:
            out.append(Problem(rid, "RDY-ACH-01", "no early compliance assessment against the board, family and budget",
                               f"The reviewer has not judged whether {rid} can be met on this board and part.", level="strict", topic="feasibility"))
        elif c in ("non_compliant", "tbc"):
            risk = (comp.get("risk") if isinstance(comp, dict) else None) or row.get("risk") or {}
            if not (isinstance(risk, dict) and norm(risk.get("owner")) and norm(risk.get("mitigation"))):
                out.append(Problem(rid, "RDY-ACH-02", f"assessed {c} with no named risk (an owner and a mitigation)",
                                   f"{rid} may not be achievable ({c}). Prototype it, change the implementation, or challenge the requirement and its margins: which?",
                                   level="strict", topic="feasibility"))
    if ledger is not None:                                                                         # unique: an id is never reused
        prior = (ledger.get("ids") or {}).get(rid)
        if prior and prior.get("text_sha") and prior["text_sha"] != text_sha(text) and not prior.get("revised"):
            out.append(Problem(rid, "RDY-UNIQ-01", "the id was used before for a different requirement",
                               f"{rid} was used earlier for different wording; a deleted requirement's id is never reused. Give this requirement a new id."))
    return out


# ---- the id ledger (unique: never reused) ---------------------------------------------------------------------------------------------
def ledger_path(design: Path) -> Path:
    return Path(design).joinpath(*STATE_DIR, LEDGER_FILE)


def read_ledger(design: Path) -> dict[str, Any]:
    try:
        return json.loads(ledger_path(design).read_text())
    except (OSError, ValueError):
        return {"ids": {}}


def update_ledger(design: Path, spec: dict[str, Any], *, revised: Iterable[str] = ()) -> dict[str, Any]:
    """Record every id of the set. An id in the ledger and no longer in the set is ``deleted`` and stays in the ledger, so it is not reused.
    ``revised`` names the ids whose wording the user knowingly changed in this round (a change of the same requirement, not a reuse)."""
    led = read_ledger(design)
    ids = led.setdefault("ids", {})
    rev = set(revised)
    now_ids = set()
    for r in reqs_of(spec):
        rid = str(r["id"])
        now_ids.add(rid)
        sha = text_sha(r.get("text", ""))
        old = ids.get(rid)
        if old is None:
            ids[rid] = {"text_sha": sha, "first": now(), "deleted": False}
            continue
        if old.get("text_sha") != sha:
            old.setdefault("history", []).append({"text_sha": old.get("text_sha"), "until": now()})
            old["text_sha"] = sha
        old["deleted"] = False
        old.pop("revised", None)
    for rid, v in ids.items():
        if rid not in now_ids and not v.get("deleted"):
            v["deleted"], v["deleted_at"] = True, now()
    p = ledger_path(design)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(led, indent=1, sort_keys=True) + "\n")
    return led


def reused_ids(prev: dict[str, Any], spec: dict[str, Any], *, revised: Iterable[str] = ()) -> list[str]:
    """Ids of ``spec`` that the ledger knows as deleted (an id is retired for good, even when the new row claims to be a revision) or with different wording
    not declared revised: an id reused."""
    rev = set(revised)
    out = []
    for r in reqs_of(spec):
        old = (prev.get("ids") or {}).get(str(r["id"]))
        if not old:
            continue
        if old.get("deleted") or (str(r["id"]) not in rev and old.get("text_sha") != text_sha(r.get("text", ""))):
            out.append(str(r["id"]))
    return out


# ---- layer 2 (FRETish-shaped) -----------------------------------------------------------------------------------------------------------
def _clock_names(spec: dict[str, Any]) -> set[str]:
    out = set()
    for c in spec.get("clocks") or []:
        if isinstance(c, dict):
            out |= {str(c[k]) for k in ("name", "port") if c.get(k)}
    return out


def l2_problems(row: dict[str, Any], spec: dict[str, Any]) -> list[Problem]:
    """Field and unit completeness of the structured layer. The common mistakes are named in docs/agent.md: ``within n`` against ``after n`` (``kind`` is
    required), a tick that is not a stated clock, a missing scope, a missing condition."""
    rid = str(row["id"])
    l2 = row.get("l2")
    if not isinstance(l2, dict) or not l2:
        return [Problem(rid, "RDY-L2-01", "no structured layer (scope, condition, component, timing, response)",
                        f"The structured form of {rid} is missing: which condition triggers it, what responds, and how fast, in which clock?", level="strict")]
    out = []
    for f in L2_FIELDS:
        if f != "timing" and not norm(l2.get(f)):
            out.append(Problem(rid, "RDY-L2-02", f"the structured layer has no {f}", f"What is the {f} of {rid}?", level="strict"))
    t, clocks = l2.get("timing"), _clock_names(spec)
    if not isinstance(t, dict) or str(t.get("kind")) not in TIMING_KINDS:
        out.append(Problem(rid, "RDY-L2-03", f"timing.kind is missing or not one of {', '.join(TIMING_KINDS)}",
                           f"For {rid}: does the response happen within n cycles (some time in 1..n), exactly after n cycles, for n cycles, or until an event?", level="strict"))
        return out
    if t["kind"] in NEEDS_N and not isinstance(t.get("n"), (int, list)):
        out.append(Problem(rid, "RDY-L2-04", f"timing.kind is {t['kind']} but n is not a number (or a [low, high] range)", f"How many cycles does {rid} allow, as a number?", level="strict"))
    if t["kind"] in NEEDS_N + ("until", "immediately") and clocks and str(t.get("clock") or "") not in clocks:
        out.append(Problem(rid, "RDY-L2-05", f"timing.clock {t.get('clock')!r} is not a clock of the design ({', '.join(sorted(clocks))}); a tick is one cycle of a stated clock",
                           f"Which clock is the tick of {rid}'s timing?", level="strict", topic="clocks and crossings"))
    if t["kind"] in NEEDS_N and not norm(t.get("from")):
        out.append(Problem(rid, "RDY-L2-06", "timing.from does not name the event the count starts from", f"For {rid}, the count of cycles starts from which event or edge?", level="strict"))
    return out


def ears_text(row: dict[str, Any]) -> str:
    """The English of a requirement regenerated from its structured layer (not the user's own words), so a drift between what the user meant and the
    fields shows. EARS patterns: state-driven (WHILE), event-driven (WHEN), unwanted behaviour (IF ... THEN) and ubiquitous."""
    l2 = row.get("l2") or {}
    modal = (modal_of(row) or "shall").upper()
    comp = norm(l2.get("component")) or "the design"
    cond, scope, resp = norm(l2.get("condition")), norm(l2.get("scope")), norm(l2.get("response"))
    t = l2.get("timing") or {}
    k, n, clk, frm = t.get("kind"), t.get("n"), norm(t.get("clock")), norm(t.get("from"))
    nn = f"{n[0]} to {n[1]}" if isinstance(n, list) and len(n) == 2 else str(n)
    unit = f"{clk} cycle{'' if nn == '1' else 's'}" if clk else "cycles"
    when = {"immediately": "in the same cycle", "within": f"within {nn} {unit}" + (f" of {frm}" if frm else ""),
            "after": f"exactly {nn} {unit} after {frm or 'the condition'}", "for": f"for {nn} {unit}" + (f" from {frm}" if frm else ""),
            "until": f"until {frm or 'the condition clears'}", "eventually": "eventually"}.get(str(k), "")
    lead = ""
    if scope and scope.lower() not in NO_SCOPE:
        lead += f"WHILE {scope}, "
    if cond:
        lead += (f"IF {cond}, THEN " if re.match(r"(?i)(?:not\b|unwanted|fault|error)", cond) else f"WHEN {cond}, ")
    tail = " at all times" if k == "always" else ""
    sentence = f"{lead}{comp} {modal} {(when + ' ') if when else ''}{resp}{tail}".strip()
    return sentence[0].upper() + sentence[1:] + ("" if sentence.endswith(".") else ".")


_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+")
_STOPW = {"the", "a", "an", "is", "are", "be", "of", "to", "in", "on", "and", "or", "it", "its", "when", "while", "if", "then", "shall", "that", "this"}


def _toks(s: Any) -> set[str]:
    return {w.lower() for w in _WORD.findall(str(s or "")) if w.lower() not in _STOPW}


def l2_diff(a: dict[str, Any], b: dict[str, Any], *, min_overlap: float = 0.5) -> list[str]:
    """How two structured layers of the same requirement differ (empty: they agree). Timing is compared exactly (kind, n, clock); the prose fields by
    the words they share, since two honest readers word the same thing differently. Code only."""
    out = []
    ta, tb = (a.get("timing") or {}), (b.get("timing") or {})
    for k in ("kind", "n", "clock"):
        if str(ta.get(k)) != str(tb.get(k)):
            out.append(f"timing.{k}: {ta.get(k)!r} against {tb.get(k)!r}")
    for f in ("scope", "condition", "response"):
        x, y = _toks(a.get(f)), _toks(b.get(f))
        if not x and not y:
            continue
        ov = len(x & y) / max(1, len(x | y))
        if ov < min_overlap:
            out.append(f"{f}: {norm(a.get(f))!r} against {norm(b.get(f))!r} (only {ov:.0%} of the words shared)")
    na = {w for f in ("scope", "condition", "response") for w in _toks(a.get(f)) if w.isdigit()}
    nb = {w for f in ("scope", "condition", "response") for w in _toks(b.get(f)) if w.isdigit()}
    if na != nb:
        out.append(f"numbers differ: {sorted(na ^ nb)}")
    return out


# ---- layer 3 ---------------------------------------------------------------------------------------------------------------------------
def l3_problems(row: dict[str, Any], spec: dict[str, Any], sva: dict[str, Any] | None = None) -> list[Problem]:
    """Strict: a timing, protocol, reset or functional row has a layer 3 (a generated property, a named check or a stated reason it is simulation only).
    ``sva`` is ``build/verif/sva/evidence.json`` of ``flow/sva_req.py``; a property that was generated but is vacuous or failed is not layer 3."""
    rid = str(row["id"])
    if row.get("kind") not in FORMAL_KINDS or not is_verified_kind(row):
        return []
    l3 = row.get("l3")
    rec = ((sva or {}).get("requirements") or {}).get(rid) or {}
    if rec.get("status") in ("vacuous", "failed"):
        return [Problem(rid, "RDY-L3-02", f"the generated property is {rec['status']}: {rec.get('why', '')}"[:240],
                        f"The property written from {rid} is {rec['status']}. Is the requirement wrong, an assumption missing, or the trigger unreachable?", level="strict")]
    if rec.get("status") in ("proved", "bounded"):
        return []
    if isinstance(l3, dict) and (l3.get("check") or l3.get("sim_only") or l3.get("sva")):
        if l3.get("sim_only") is not None and not l3.get("check") and len(norm(l3["sim_only"])) < 8:
            return [Problem(rid, "RDY-L3-03", "sim_only gives no reason", f"Why is {rid} simulation only?", level="strict")]
        return []
    return [Problem(rid, "RDY-L3-01", "no layer 3: no property, named check or stated reason it is simulation only",
                    f"How is {rid} to be checked mechanically: a property, a named check, or simulation only (and why)?", level="strict", topic="test strategy")]


# ---- the interface contract (research 228 8(a), brief 227 section 1) ------------------------------------------------------------------
def interface_problems(spec: dict[str, Any]) -> list[Problem]:
    """Every port with direction, width, clock domain and reset value; every output's latency from a named input event; every handshake rule; units.
    A missing item is a question, never a default. Reads spec.yaml ``ports``, ``clocks``, ``reset`` and the optional ``latencies`` (output, from, cycles,
    clock) and ``handshakes`` (name, rule) tables."""
    out: list[Problem] = []
    ports = [p for p in spec.get("ports") or [] if isinstance(p, dict) and p.get("name")]
    clock_ports = {str(c.get("port") or c.get("name")) for c in spec.get("clocks") or [] if isinstance(c, dict)}
    rst = spec.get("reset") or {}
    rport = str(rst.get("port") or rst.get("name") or "") if isinstance(rst, dict) else ""
    multi = len(clock_ports) > 1
    lat = [x for x in spec.get("latencies") or [] if isinstance(x, dict)]
    for p in ports:
        n = str(p["name"])
        d = str(p.get("dir", p.get("direction", ""))).lower()
        if d not in ("in", "input", "out", "output", "inout"):
            out.append(Problem("interface", "RDY-IF-01", f"port {n} has no direction", f"Is {n} an input, an output or inout?", topic="interface"))
        try:
            int(p.get("width", 1))
        except (TypeError, ValueError):
            out.append(Problem("interface", "RDY-IF-02", f"port {n} has no numeric width ({p.get('width')!r})", f"What is the width of {n} in bits?", topic="interface"))
        if n in clock_ports or n == rport:
            continue
        note = str(p.get("note", ""))
        if multi and not norm(p.get("clock")):
            out.append(Problem("interface", "RDY-IF-03", f"port {n} has no clock domain (the design has {len(clock_ports)} clocks)", f"Which clock is {n} synchronous to?", level="strict", topic="clocks and crossings"))
        if d in ("out", "output"):
            if p.get("reset_value") is None and not re.search(r"\b(combinational|no reset|unreset|wire|constant|static)\b", note, re.I):
                out.append(Problem("interface", "RDY-IF-04", f"output {n} has no reset value", f"What does {n} drive during and just after reset?", level="strict", topic="reset strategy"))
            if not any(str(x.get("output")) == n for x in lat) and not re.search(r"\b(combinational|static|constant|status led)\b", note, re.I):
                out.append(Problem("interface", "RDY-IF-05", f"output {n} has no stated latency from a named input event",
                                   f"How many cycles after which input event does {n} change (or is it combinational)?", level="strict", topic="throughput and latency"))
    for x in lat:
        if not (norm(x.get("from")) and isinstance(x.get("cycles"), (int, list)) and norm(x.get("clock"))):
            out.append(Problem("interface", "RDY-IF-06", f"latency of {x.get('output')} lacks the starting event, the number of cycles or the clock",
                               f"State the latency of {x.get('output')}: from which event, in how many cycles of which clock.", topic="throughput and latency"))
    kinds: dict[str, set[str]] = {}
    for p in ports:
        m = re.match(r"(?i)^(.*?)_?(tvalid|tready|valid|ready)$", str(p["name"]))
        if m and m.group(1):
            kinds.setdefault(m.group(1), set()).add("valid" if m.group(2).lower().endswith("valid") else "ready")
    hs = {str(h.get("name")) for h in spec.get("handshakes") or [] if isinstance(h, dict)}
    for s in sorted(k for k, v in kinds.items() if v == {"valid", "ready"}):          # a valid with no ready is a strobe, not a handshake
        if not any(s in h for h in hs):
            out.append(Problem("interface", "RDY-IF-07", f"the valid/ready interface {s!r} has no stated handshake rule",
                               f"For {s}: may valid drop before ready? Is data held while stalled? What happens on a reset mid-transfer?", topic="error and back-pressure"))
    for h in spec.get("handshakes") or []:
        if isinstance(h, dict) and not norm(h.get("rule")):
            out.append(Problem("interface", "RDY-IF-08", f"handshake {h.get('name')} has no rule", f"State the rule of handshake {h.get('name')}.", topic="error and back-pressure"))
    for r in reqs_of(spec):                                                                         # numeric formats
        t = norm(r.get("text"))
        if re.search(r"\b(signed|unsigned|fixed[- ]point|q\d+\.\d+|saturat\w*|overflow|wrap\w*)\b", t, re.I) is None and re.search(r"\b(sum|accumulat\w+|multipl\w+|scale\w*|gain|average|mean)\b", t, re.I):
            out.append(Problem(str(r["id"]), "RDY-NUM-01", "an arithmetic result with no stated number format or overflow behaviour",
                               f"For {r['id']}: signed or unsigned, how many fractional bits, and what happens on overflow (wrap or saturate)?", level="strict", topic="numeric formats"))
    return out


# ---- consistency between rows ----------------------------------------------------------------------------------------------------------
_ASSIGN = re.compile(r"\b((?:[A-Za-z_][A-Za-z0-9_]*\s+){0,2}[A-Za-z_][A-Za-z0-9_]*)\s+(?:is|equals|resets to|=|exactly)\s+(?:exactly |at most |at least )?(\d[\d_]*)\b")
_QUANT_STOP = {"the", "a", "an", "its", "each", "every", "both", "all", "of", "and", "or", "to", "value", "when", "if", "while", "after", "before", "until", "then"}
_CONDITIONAL = re.compile(r"\b(when|whenever|if|while|after|before|during|until|on|at|unless|once)\b", re.I)


def consistency_problems(spec: dict[str, Any]) -> list[Problem]:
    """Two rows that cannot both hold: the same quantity (a named signal followed by "is/equals/exactly" and a number) given two numbers, or two rows with the
    same text under different ids. Simple and conservative: it finds the obvious clash, it does not prove the set consistent (a formal consistency check of
    the layer-2 formulas is a later step, see docs/agent.md)."""
    out, seen, texts = [], {}, {}
    for r in reqs_of(spec):
        if not is_verified_kind(r):
            continue
        rid = str(r["id"])
        key = norm(r.get("text")).lower()
        if key in texts:
            out.append(Problem(rid, "RDY-CONS-01", f"the same wording as {texts[key]}", f"{rid} repeats {texts[key]}: drop one, or say what differs.", repair=True))
        texts[key] = rid
        text = norm(r.get("text"))
        if _CONDITIONAL.search(text):                                   # a quantity "when X" and the same quantity "when Y" may differ: not a clash
            continue
        for m in _ASSIGN.finditer(text):
            words = [w.lower() for w in m.group(1).split() if w.lower() not in _QUANT_STOP]
            val = int(m.group(2).replace("_", ""))
            if not words or val < 2:                                    # 0 and 1 are logic levels, not quantities
                continue
            sig = " ".join(words[-2:])
            prev = seen.get(sig)
            if prev and prev[1] != val and prev[0] != rid:
                out.append(Problem(rid, "RDY-CONS-02", f"{sig} is {val} here and {prev[1]} in {prev[0]}", f"{prev[0]} and {rid} give {sig} two values ({prev[1]} and {val}): which is right?"))
            seen.setdefault(sig, (rid, val))
    return out


def implementation_problems(spec: dict[str, Any]) -> list[Problem]:
    out = []
    for r in reqs_of(spec):
        ph = implementation_specific(r.get("text", ""))
        if ph and not r.get("design_constraint"):
            out.append(Problem(str(r["id"]), "RDY-IMPL-01", f"names an implementation ({ph!r}) rather than a function",
                               f"{r['id']} says {ph!r}. Is that a true constraint (keep it, as a design constraint) or should it be restated as a function and measurable values "
                               "(resolution, rate, latency, bandwidth)?"))
    return out


# ---- defaults, derived rows and validation ---------------------------------------------------------------------------------------------
def _valid_record(v: Any) -> dict[str, Any] | None:
    if v is True:
        return {"who": "?", "when": "?", "shown": None}
    return v if isinstance(v, dict) and norm(v.get("who")) and norm(v.get("when")) else None


def confirmation_problems(spec: dict[str, Any], *, level: str, confirmations: dict[str, Any] | None = None) -> list[Problem]:
    """A default the agent chose that became a requirement is *derived* and must be validated by the user; an unconfirmed default blocks at strict and
    is listed in the handover at standard. ``validated_by_user`` is a record ``{who, when, shown}`` and is kept apart from ``verified``. A confirmation
    whose ``shown`` hash is not the hash of the show-back packet now is stale (the packet was edited after the user read it)."""
    out = []
    conf = (confirmations or {}).get("confirmed") or {}
    for r in reqs_of(spec):
        rid = str(r["id"])
        og = r.get("origin")
        kind = (og.get("kind") if isinstance(og, dict) else og) or ""
        derived = bool(r.get("derived")) or str(kind) in ("default", "agent", "derived")
        v = _valid_record(r.get("validated_by_user") or conf.get(rid))
        if v and v.get("shown") and v["shown"] != packet_hash(r):
            out.append(Problem(rid, "RDY-VAL-02", "the user's confirmation was of an earlier version of the show-back packet", f"{rid} changed after you confirmed it. Please read it again and confirm.",
                               level="strict"))
        elif derived and not v:
            out.append(Problem(rid, "RDY-DEF-01", "a default the agent chose became this requirement and the user has not validated it",
                               f"The agent chose the basis of {rid} (a default). Do you confirm it as written?", level="strict"))
        elif level == "strict" and is_verified_kind(r) and not v:
            out.append(Problem(rid, "RDY-VAL-01", "not validated by the user (validation is the right design; verification is built right: they are separate)",
                               f"Please confirm {rid} from its show-back packet.", level="strict"))
    return out


def unconfirmed_defaults(spec: dict[str, Any], confirmations: dict[str, Any] | None = None) -> list[str]:
    """The handover list at standard: ids of derived rows nobody validated (they are listed, not blocking)."""
    return [p.id for p in confirmation_problems(spec, level="standard", confirmations=confirmations) if p.code == "RDY-DEF-01"]


def all_ok_risk(confirmations: dict[str, Any]) -> str | None:
    """An all-"OK" confirmation of a long list is a risk (research 228): the handover flags it when at least 8 requirements were confirmed in one batch with no
    edit and no question."""
    c = (confirmations or {}).get("confirmed") or {}
    batches: dict[str, int] = {}
    for v in c.values():
        if isinstance(v, dict):
            batches[str(v.get("when", ""))] = batches.get(str(v.get("when", "")), 0) + 1
    biggest = max(batches.values(), default=0)
    if biggest >= 8 and int((confirmations or {}).get("edits_made") or 0) == 0 and int((confirmations or {}).get("questions_asked") or 0) == 0:
        return (f"{biggest} requirements were confirmed in one batch with no edit and no question: confirm only what you read; "
                "a long all-OK list is the usual way a wrong requirement gets through")
    return None


# ---- the show-back packet --------------------------------------------------------------------------------------------------------------
def packet_hash(row: dict[str, Any]) -> str:
    """The hash of what the user reads: the user's text, the structured layer, the worked numbers and the never example."""
    body = json.dumps([norm(row.get("text")), row.get("l2"), row.get("worked"), row.get("never"), modal_of(row)], sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def showback(row: dict[str, Any], *, cover_trace: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the user is shown to confirm one requirement (research 228 8(b)): (1) the text regenerated from L2, (2) a timing diagram from a cover trace with cycle
    numbers (WaveDrom JSON, MIT) when one exists, (3) worked numbers, (4) one "must never happen" example. A formula or an SVA alone is never the thing confirmed.
    ``missing`` lists what the packet lacks; a packet with anything missing is not ready to be confirmed."""
    missing = []
    regen = ears_text(row) if isinstance(row.get("l2"), dict) and row["l2"] else None
    if regen is None:
        missing.append("text regenerated from the structured layer")
    worked = [w for w in row.get("worked") or [] if isinstance(w, (dict, str)) and norm(w if isinstance(w, str) else w.get("expected") or w.get("example"))]
    if not worked:
        missing.append("worked numbers")
    never = norm(row.get("never"))
    if not never:
        missing.append("a 'must never happen' example")
    if row.get("kind") in ("timing", "protocol", "reset") and not cover_trace:
        missing.append("a timing diagram from a cover trace (pending until the formal flow produces one)")
    return {"id": str(row["id"]), "l1": norm(row.get("text")), "regenerated": regen, "worked": worked, "never": never or None,
            "diagram": cover_trace, "missing": missing, "hash": packet_hash(row)}


def showback_problems(row: dict[str, Any], cover_trace: dict[str, Any] | None = None) -> list[Problem]:
    if row.get("kind") not in FORMAL_KINDS or not is_verified_kind(row):
        return []
    miss = [m for m in showback(row, cover_trace=cover_trace)["missing"] if not m.startswith("a timing diagram")]    # the diagram comes from the formal flow, later
    return [Problem(str(row["id"]), "RDY-SHOW-01", "the show-back packet lacks: " + "; ".join(miss),
                    f"For {row['id']}: give worked numbers and one case that must never happen.", level="strict", topic="test strategy")] if miss else []


# ---- the upward trace (DO-254 practice) -------------------------------------------------------------------------------------------------
def upward_trace(design: Path, spec: dict[str, Any]) -> list[Problem]:
    """A test that traces to no requirement is flagged (it is either an undocumented requirement or dead): each cocotb test of ``tests/`` must cite a requirement
    id of the set in its block (a ``# req:`` tag, its name or its docstring). Advisory, not blocking: helper tests exist."""
    ids = {str(r["id"]) for r in reqs_of(spec)}
    out = []
    d = Path(design)
    for f in sorted((d / "tests").glob("test_*.py")) if (d / "tests").is_dir() else []:
        text = f.read_text(errors="replace")
        defs = list(re.finditer(r"(?m)^(?:async )?def (test_\w+)\s*\(", text))
        for i, m in enumerate(defs):
            end = defs[i + 1].start() if i + 1 < len(defs) else len(text)
            above = text[:m.start()].splitlines()[::-1]
            tag: list[str] = []
            for ln in above:                                              # the comment and decorator lines directly above the def
                if ln.strip().startswith(("#", "@")):
                    tag.append(ln)
                else:
                    break
            block = "\n".join(tag) + "\n" + text[m.start():end]
            if not (set(re.findall(r"[A-Za-z]+[-_]\d+", block)) & ids):
                out.append(Problem("trace", "RDY-UP-01", f"test {m.group(1)} in {f.name} traces to no requirement",
                                   f"{m.group(1)} checks something no requirement states: add the requirement, or drop the test.", blocking=False, topic="test strategy"))
    return out


# ---- reader agreement (two fresh readers, a third for layer 2) -------------------------------------------------------------------------
PROBE_CATEGORIES = ("reset", "boundary", "simultaneous", "overflow", "back_pressure", "unmapped", "mid_operation_reset", "invalid_input", "power_up")
ANSWER_KINDS = ("bool", "int", "choice")
UNSPECIFIED = "unspecified"


def probe_problems(probes: list[dict[str, Any]], spec: dict[str, Any]) -> list[str]:
    """Why a probe set is not usable (empty: usable). Each probe has an id, a scenario, a question, an answer kind (bool, int or choice, with the choices) and a
    category; ``unspecified`` is always an allowed answer. The set must reach the categories that apply to the design (reset always; back-pressure when there is a
    valid/ready style interface; unmapped when there are registers). A set too small to find the ambiguity that matters is the user's risk, recorded with its size."""
    errs, seen = [], set()
    for p in probes:
        pid = str(p.get("id", ""))
        if not pid or pid in seen:
            errs.append(f"probe id {pid!r} missing or repeated")
        seen.add(pid)
        if not norm(p.get("scenario")) or not norm(p.get("question")):
            errs.append(f"probe {pid}: no scenario or question")
        k = p.get("answer_kind")
        if k not in ANSWER_KINDS:
            errs.append(f"probe {pid}: answer_kind must be one of {', '.join(ANSWER_KINDS)}")
        if k == "choice" and not (isinstance(p.get("choices"), list) and len(p["choices"]) >= 2):
            errs.append(f"probe {pid}: a choice probe lists at least two choices")
        if p.get("category") not in PROBE_CATEGORIES:
            errs.append(f"probe {pid}: category must be one of {', '.join(PROBE_CATEGORIES)}")
    need = {"reset"}
    ports = [str(q.get("name", "")) for q in spec.get("ports") or [] if isinstance(q, dict)]
    if any(re.search(r"(?i)(valid|ready)$", n) for n in ports):
        need.add("back_pressure")
    if spec.get("registers") or any(re.search(r"(?i)(^|_)(addr|waddr|raddr)$", n) for n in ports):
        need.add("unmapped")
    got = {p.get("category") for p in probes}
    errs += [f"no probe of category {c!r}, which applies to this design" for c in sorted(need - got)]
    return errs


def normalise_answer(probe: dict[str, Any], ans: Any) -> str:
    """One comparable string. ``unspecified`` (the reader says the requirements do not decide it) is its own value."""
    a = str(ans if ans is not None else "").strip().lower()
    if a in ("", UNSPECIFIED, "not specified", "unknown", "cannot tell", "undetermined", "n/a"):
        return UNSPECIFIED
    k = probe.get("answer_kind")
    if k == "bool":
        return "yes" if a in ("yes", "true", "1", "y") else ("no" if a in ("no", "false", "0", "n") else a)
    if k == "int":
        m = re.search(r"-?\d+", a.replace("_", "").replace(",", ""))
        return m.group(0) if m else a
    ch = [str(c).strip().lower() for c in probe.get("choices") or []]
    return a if a in ch else next((c for c in ch if c in a), a)


@dataclass
class Agreement:
    probes: int
    agreed: int
    disagreements: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[dict[str, Any]] = field(default_factory=list)          # every reader says unspecified: the requirements do not decide it

    @property
    def rate(self) -> float:
        return self.agreed / self.probes if self.probes else 1.0

    @property
    def ok(self) -> bool:
        return not self.disagreements and not self.gaps

    def as_dict(self) -> dict[str, Any]:
        return {"probes": self.probes, "agreed": self.agreed, "rate": round(self.rate, 4), "disagreements": self.disagreements, "gaps": self.gaps}


def compare_readers(probes: list[dict[str, Any]], readers: dict[str, dict[str, Any]]) -> Agreement:
    """The measure "satisfactory to the agent": no disagreement on the probe set and no open question. ``readers`` maps a reader name to ``{probe id: answer}``.
    A probe a reader did not answer counts as ``unspecified``. Different values (including one value and one ``unspecified``) are an ambiguity and become a
    question; a probe on which every reader says ``unspecified`` is a gap and becomes a question. Code compares normalised strings; no model judges agreement."""
    dis, gaps, agreed = [], [], 0
    for p in probes:
        pid = str(p["id"])
        got = {r: normalise_answer(p, a.get(pid)) for r, a in readers.items()}
        vals = set(got.values())
        if vals == {UNSPECIFIED}:
            gaps.append({"probe": pid, "scenario": p.get("scenario"), "question": p.get("question"), "answers": got, "requirements": p.get("requirements") or []})
        elif len(vals) > 1:
            dis.append({"probe": pid, "scenario": p.get("scenario"), "question": p.get("question"), "category": p.get("category"), "answers": got,
                        "requirements": p.get("requirements") or []})
        else:
            agreed += 1
    return Agreement(len(probes), agreed, dis, gaps)


def questions_from_agreement(ag: Agreement) -> list[Problem]:
    out = []
    for d in ag.disagreements:
        out.append(Problem(",".join(d.get("requirements") or []) or "set", "RDY-READ-01", f"two readers predicted different behaviour for: {d['scenario']} ({d['answers']})",
                           f"{d['question']} (Scenario: {d['scenario']}) Two careful readers of the requirements disagree about this; what is the intended behaviour?"))
    for g in ag.gaps:
        out.append(Problem(",".join(g.get("requirements") or []) or "set", "RDY-READ-02", f"the requirements do not decide: {g['scenario']}",
                           f"{g['question']} (Scenario: {g['scenario']}) The requirements do not say; what should happen?"))
    return out


# ---- the stop rule, the frozen set and the return to stage 0 ------------------------------------------------------------------------------
@dataclass
class Limits:
    max_rounds: int = 4
    max_calls: int = 60          # model calls over the whole of stage 0 (reviewer, probe writer, readers, third reader, amender)
    max_questions: int = 25

    def as_dict(self) -> dict[str, int]:
        return {"max_rounds": self.max_rounds, "max_calls": self.max_calls, "max_questions": self.max_questions}


def rows_hash(spec: dict[str, Any]) -> str:
    rows = [{"id": str(r["id"]), "text": norm(r.get("text")), "l2": r.get("l2"), "modal": modal_of(r), "proof": r.get("proof"), "method": method_of(r)} for r in reqs_of(spec)]
    return hashlib.sha256(json.dumps(sorted(rows, key=lambda r: r["id"]), sort_keys=True, default=str).encode()).hexdigest()[:24]


def frozen_path(design: Path) -> Path:
    return Path(design).joinpath(*STATE_DIR, FROZEN_FILE)


def read_frozen(design: Path) -> dict[str, Any] | None:
    try:
        return json.loads(frozen_path(design).read_text())
    except (OSError, ValueError):
        return None


def freeze(design: Path, spec: dict[str, Any], *, level: str, rounds: int, why: str = "readiness gate passed") -> dict[str, Any]:
    """Stages 1 onward read the frozen set. A later change returns to stage 0 and is recorded (:func:`reopen`). Frozen ids go in the ledger."""
    prev = read_frozen(design)
    rec = {"schema": SCHEMA, "frozen_at": now(), "version": ((prev or {}).get("version") or 0) + 1, "level": level, "rounds": rounds, "why": why,
           "hash": rows_hash(spec), "ids": sorted(str(r["id"]) for r in reqs_of(spec)), "reopened": (prev or {}).get("reopened", []), "status": "frozen",
           "rows": {str(r["id"]): text_sha(r.get("text", "")) for r in reqs_of(spec)}}
    update_ledger(design, spec)
    p = frozen_path(design)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=1) + "\n")
    return rec


def changed_since_freeze(design: Path, spec: dict[str, Any]) -> list[str]:
    """The ids whose wording, structure or presence differs from the frozen set (empty when not frozen or unchanged)."""
    fr = read_frozen(design)
    if not fr or not fr.get("hash") or fr["hash"] == rows_hash(spec):
        return []
    now_rows = {str(r["id"]): text_sha(r.get("text", "")) for r in reqs_of(spec)}
    old = fr.get("rows") or {}
    return sorted({i for i in set(now_rows) | set(old) if now_rows.get(i) != old.get(i)}) or ["(structure)"]


def reopen(design: Path, spec: dict[str, Any], *, why: str, ids: list[str] | None = None, who: str = "agent") -> dict[str, Any]:
    """A change after the freeze returns the design to stage 0: the freeze is withdrawn and the return is recorded with the ids, the reason and who."""
    fr = read_frozen(design) or {"schema": SCHEMA, "reopened": []}
    ch = ids if ids is not None else changed_since_freeze(design, spec)
    fr.setdefault("reopened", []).append({"when": now(), "ids": ch, "why": why, "who": who, "from_hash": fr.get("hash")})
    fr["frozen_at"], fr["hash"], fr["status"] = None, None, "reopened"
    p = frozen_path(design)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fr, indent=1) + "\n")
    return fr


def check_frozen_or_reopen(design: Path, spec: dict[str, Any], *, who: str = "agent") -> list[str]:
    """Called by a later stage that has read the spec: when it differs from the frozen set, record the return to stage 0 and report the changed ids."""
    ch = changed_since_freeze(design, spec)
    if ch:
        reopen(design, spec, why="requirements changed after the freeze", ids=ch, who=who)
    return ch


# ---- the whole mechanical gate ---------------------------------------------------------------------------------------------------------
def mechanical_problems(design: Path, spec: dict[str, Any], *, level: str = "standard", sva: dict[str, Any] | None = None,
                        confirmations: dict[str, Any] | None = None, cover_traces: dict[str, Any] | None = None) -> list[Problem]:
    """Every check of this module on a spec, no model. Problems that block at ``level`` stop the gate; the rest are listed."""
    led = read_ledger(design)
    if not reqs_of(spec):
        return [Problem("set", "RDY-SET-01", "the design has no requirements", "What must the design do and how will you check it?")]
    probs: list[Problem] = []
    for r in reqs_of(spec):
        probs += six_properties(r, spec, level=level, ledger=led)
        if r.get("kind") is not None and r["kind"] not in KINDS:
            probs.append(Problem(str(r["id"]), "RDY-KIND-01", f"kind {r.get('kind')!r} is not one of {', '.join(KINDS)}", f"What kind of requirement is {r['id']}?", level="strict"))
        if level == "strict":
            if r.get("kind") is None:
                probs.append(Problem(str(r["id"]), "RDY-KIND-01", "no kind (interface, timing, protocol, functional, reset, budget, board or other)", f"What kind of requirement is {r['id']}?", level="strict"))
            if r.get("kind") in FORMAL_KINDS and is_verified_kind(r):
                probs += l2_problems(r, spec)
            probs += l3_problems(r, spec, sva) + showback_problems(r, (cover_traces or {}).get(str(r["id"])))
    probs += implementation_problems(spec) + consistency_problems(spec) + interface_problems(spec)
    probs += confirmation_problems(spec, level=level, confirmations=confirmations) + upward_trace(design, spec)
    return probs


def blocking(probs: list[Problem], level: str) -> list[Problem]:
    return [p for p in probs if p.blocks(level)]


# ---- the Verification Cross-Reference Matrix (practice 4) --------------------------------------------------------------------------------
def _c(x: Any) -> str:
    return str(x if x is not None else "").replace("|", "\\|").replace("\n", " ")


def vcrm_markdown(spec: dict[str, Any], report: dict[str, Any] | None = None, *, independent: dict[str, str] | None = None) -> str:
    """The requirements as a VCRM: id, SHALL/SHOULD/WILL, text, verification method (Test, Analysis, Inspection, Demonstration), the evidence named, validated by the
    user, verified, the early compliance assessment and which checks were independent of the RTL's author. ``report`` is the requirements report data
    (``flow/requirements_report.py``), for the verified result. WILL rows are descriptive and never verified."""
    res = {r["id"]: r for r in (report or {}).get("requirements") or []}
    ind = independent or {}
    out = ["| Id | Modal | Requirement | Method | Evidence | Validated by user | Verified | Early compliance | Independent check |", "|---|---|---|---|---|---|---|---|---|"]
    for r in reqs_of(spec):
        rid = str(r["id"])
        m = (modal_of(r) or "shall").upper()
        v = _valid_record(r.get("validated_by_user"))
        vtxt = (f"yes ({v['who']}, {v['when']})" if v and v["who"] != "?" else "yes") if v else ("no (derived)" if r.get("derived") else "no")
        ver = "never (WILL)" if m == "WILL" else (res.get(rid, {}).get("result") or "pending") + (" (SHOULD: not mandatory)" if m == "SHOULD" else "")
        c = r.get("compliance")
        ctxt = (c.get("status") if isinstance(c, dict) else c) or "not assessed"
        out.append("| " + " | ".join(_c(x) for x in (rid, m, r.get("text"), method_of(r) or "none", r.get("evidence") or "-", vtxt, ver, ctxt, ind.get(rid, "none recorded"))) + " |")
    return "\n".join(out) + "\n"


# ---- the early compliance assessment and its calibration (practice 5) -------------------------------------------------------------------
def risks_from_assessment(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Each partial, non-compliant or TBC row becomes a named risk with an owner and a mitigation."""
    out = []
    for r in reqs_of(spec):
        c = r.get("compliance")
        s = c.get("status") if isinstance(c, dict) else c
        if s in ("partial", "non_compliant", "tbc"):
            rk = (c.get("risk") if isinstance(c, dict) else None) or r.get("risk") or {}
            out.append({"id": str(r["id"]), "status": s, "why": norm(c.get("why") if isinstance(c, dict) else ""), "owner": norm(rk.get("owner")) or None,
                        "mitigation": norm(rk.get("mitigation")) or None})
    return out


def calibration(assessment: dict[str, str], verified: dict[str, str]) -> dict[str, Any]:
    """After the build: the reviewer's early compliance judgement against the verified outcome. ``assessment`` maps an id to compliant / partial / non_compliant /
    tbc; ``verified`` to pass / fail / pending. A compliant row that passed, or a non-compliant one that failed, is an agreement; a compliant row that failed is a
    missed risk; a non-compliant row that passed is a false alarm; partial and tbc are counted apart (they predict nothing sharp). Pending rows are left out."""
    agree = missed = false_alarm = unsharp = n = 0
    rows = []
    for rid, a in assessment.items():
        v = verified.get(rid)
        if v not in ("pass", "fail"):
            continue
        n += 1
        if a == "compliant":
            ok = v == "pass"
            agree, missed, kind = agree + ok, missed + (not ok), ("agree" if ok else "missed_risk")
        elif a == "non_compliant":
            ok = v == "fail"
            agree, false_alarm, kind = agree + ok, false_alarm + (not ok), ("agree" if ok else "false_alarm")
        else:
            unsharp, kind = unsharp + 1, "unsharp"
        rows.append({"id": rid, "assessed": a, "verified": v, "kind": kind})
    return {"compared": n, "agree": agree, "missed_risk": missed, "false_alarm": false_alarm, "unsharp": unsharp, "rows": rows}


# ---- the two scores (section 2) ---------------------------------------------------------------------------------------------------------
FAILURE_CLASSES = ("interface", "timing", "reset", "handshake", "functional", "testbench_wrong", "tool", "cut_off_reply", "budget",
                   "requirement_missing", "requirement_wrong", "benchmark_limited")
STAGE0_CLASSES = ("requirement_missing", "requirement_wrong")


def attribute_failure(cls: str) -> str:
    """One stage per failure: a requirement missing or wrong (stage 0), or the design not meeting a correct requirement (stage 2). Benchmark-limited facts (the
    fact is nowhere in the problem or the oracle's source) are counted apart, never as an agent failure."""
    if cls not in FAILURE_CLASSES:
        raise ValueError(f"failure class must be one of {', '.join(FAILURE_CLASSES)}")
    return "benchmark_limited" if cls == "benchmark_limited" else ("stage0" if cls in STAGE0_CLASSES else "stage2")


def two_scores(state: dict[str, Any], build: dict[str, Any] | None) -> dict[str, Any]:
    """Every run reports two scores. Requirements quality: rounds, questions asked, reader agreement per round, and (where a hidden test checks facts) how many
    were covered by a frozen requirement. Build and verify: own checks against independent checks and their agreement (the 213 cross-table). ``build`` is None
    when the run stopped at stage 0."""
    rounds = state.get("rounds") or []
    req = {"rounds": len(rounds), "questions": sum(len(r.get("questions") or []) for r in rounds),
           "agreement_per_round": [(r.get("agreement") or {}).get("rate") for r in rounds], "frozen": bool(state.get("frozen")), "stop": state.get("stop"),
           "model_calls": state.get("model_calls"), "facts": state.get("facts")}
    b = None
    if build is not None:
        own, ind = build.get("own_pass"), build.get("independent_pass")
        b = {"own_pass": own, "independent_pass": ind, "agree": (own == ind) if own is not None and ind is not None else None,
             "failure_class": build.get("failure_class"), "stage": attribute_failure(build["failure_class"]) if build.get("failure_class") else None}
    return {"requirements_quality": req, "build_and_verify": b}


def fact_coverage(facts: list[dict[str, Any]], frozen_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """How many facts a hidden test checks were covered by a frozen requirement. ``facts``: ``{id, tokens: [...], in_source: bool}``: ``tokens`` are the words that
    must appear in a requirement for the fact to count as covered; ``in_source`` says whether the fact is in the problem or the oracle's source at all (False:
    benchmark-limited, not an agent failure). Code only."""
    text = " ".join(norm(r.get("text")) + " " + norm(json.dumps(r.get("l2") or {})) for r in frozen_rows).lower()
    cov, miss, limited = [], [], []
    for f in facts:
        if not f.get("in_source", True):
            limited.append(f["id"])
        elif all(str(t).lower() in text for t in f.get("tokens") or []):
            cov.append(f["id"])
        else:
            miss.append(f["id"])
    n = len(cov) + len(miss)
    return {"covered": cov, "missed": miss, "benchmark_limited": limited, "coverage": (len(cov) / n) if n else None}


# ---- the oracle note: never vectors (section 3) --------------------------------------------------------------------------------------------
_VECTOR = re.compile(r"(?:expected|golden|vector|stimul\w*|assert\w*)\b[^\n]{0,80}?(?:=|:|==)\s*(?:\d+'[hbdHBD][0-9a-fA-F_]+|0x[0-9a-fA-F]+|-?\d+\b)|"
                     r"\b(?:input|din|data)\s*=\s*\S+\s*(?:->|=>|,)\s*(?:output|out|dout|expected)\s*=", re.I)


def note_vectors(note: str) -> list[str]:
    """Lines of an oracle note that look like a test vector or an expected value (the oracle's hidden spec carries the interface and timing facts a user would
    know, never what a test expects). Returns the offending lines; :func:`build_note` refuses a note that has any."""
    return [ln.strip() for ln in str(note).splitlines() if _VECTOR.search(ln)]


def build_note(lines: list[str]) -> str:
    bad = note_vectors("\n".join(lines))
    if bad:
        raise ValueError("an oracle note must not carry test vectors or expected values; remove: " + " | ".join(bad[:3]))
    return "\n".join(lines).rstrip() + "\n"


# ---- files -----------------------------------------------------------------------------------------------------------------------------
def load_yaml(p: Path) -> dict[str, Any]:
    try:
        d = yaml.safe_load(Path(p).read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return d if isinstance(d, dict) else {}


def load_sva(design: Path) -> dict[str, Any]:
    try:
        return json.loads(Path(design).joinpath("build", "verif", "sva", "evidence.json").read_text())
    except (OSError, ValueError):
        return {}


def check(design: Path, *, level: str = "standard") -> list[Problem]:
    design = Path(design)
    return mechanical_problems(design, load_yaml(design / "spec.yaml"), level=level, sva=load_sva(design), confirmations=load_yaml(design / CONFIRMATIONS_FILE))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The mechanical checks of the requirements readiness gate (no model). The model roles run in `python -m agent.graph.readiness`.")
    ap.add_argument("design")
    ap.add_argument("--level", choices=LEVELS, default="standard")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    probs = check(Path(a.design), level=a.level)
    blk = blocking(probs, a.level)
    if a.json:
        print(json.dumps([p.as_dict() for p in probs], indent=1))
    else:
        print(f"{len(blk)} blocking, {len(probs) - len(blk)} advisory at level {a.level}")
        for p in probs:
            print(f"  {'BLOCK' if p.blocks(a.level) else 'note '} {p.code} {p.id}: {p.text}")
    return 3 if blk else 0


if __name__ == "__main__":
    sys.exit(main())
