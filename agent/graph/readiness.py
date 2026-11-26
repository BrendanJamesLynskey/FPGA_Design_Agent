"""Stage 0 until the requirements are ready (brief 227): the roles, the rounds and the stop rule. The checks are in ``flow/readiness.py`` (code only).

The process the owner asked for (2026-11-25): 1) requirements building, iterated until they are unambiguous and satisfactory to the agent; 2) build
and verify, reading the frozen set. "Satisfactory to the agent" has a measure: **two fresh readers who share no history predict the same behaviour on
the same probe set, and no question is open** (``flow.readiness.compare_readers``; code compares, no model judges). A third reader, a different model,
writes the structured layer from the user's English alone; a difference from the first structured layer is an ambiguity too.

Roles (each its own model call; none sees the RTL; the purposes ``reqreview``, ``reqreader`` and ``reqreader3`` of the model table):

- the **requirements reviewer**: an experienced FPGA engineer's pre-build questions by checklist topic (the knowledge-bank skill
  ``procedures/requirements-review``, cited by id; a short public fallback when the bank is not present), and the early compliance assessment;
- the **probe writer** (the reviewer's model, its own call): scenarios (edge cases, reset, back-pressure, overflow, simultaneous events), each with a
  constrained answer so that code can compare the answers;
- **reader A and reader B**: the same model, two separate fresh calls that see only the requirements and the interface table;
- **reader 3** (a different model): writes layer 2 from layer 1;
- the **amender** (the Clarifier's job in stage 0): turns the user's answers into changed rows; code checks it (ids are never reused, only answered
  rows change).

Nothing here is a verdict by a model: questions come from code or from the reviewer (and are asked), agreement is code, freezing is code.

Stop rule (stated, never silent): ``Limits`` gives rounds, model calls and questions. At a limit, or when nobody can answer (``--interview off``), the
run stops with ``REQUIREMENTS_NEEDED.md`` and exit status 3 (``agent.graph.requirements.EXIT_REQUIREMENTS``); it never guesses.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

import yaml

from flow import readiness as R

LLM = Callable[[str, str], str]
STOP_PREFIX = "requirements:"
REPORT_FILE = "REQUIREMENTS_READINESS.md"
NEEDED_FILE = "REQUIREMENTS_NEEDED.md"

#: the checklist topics (the headings of the knowledge-bank skill ``procedures/requirements-review``). A topic list is general engineering practice, so
#: this fallback is public; the questions under each topic, seeded from the owner's own pre-build questions and the recorded failures, live in the bank.
TOPICS = ("clocks and their sources", "clocks and crossings", "reset strategy", "I/O standards and board pins", "throughput and latency", "resource budget",
          "timing-closure risk", "numeric formats", "error and back-pressure", "power-up state", "test strategy", "interface", "feasibility", "requirement")
FALLBACK_CHECKLIST = """Pre-build checklist, by topic (ask only what the request and the rows do not already state):
- clocks and their sources: every clock's frequency, source (oscillator, PLL, derived) and which pins or ports carry it; relation between clocks.
- clocks and crossings: every signal that crosses between clock domains, and the crossing method; asynchronous inputs and their synchronisers.
- reset strategy: polarity, synchronous or asynchronous, the reset value of every register and output, behaviour during reset, reset in mid-operation.
- I/O standards and board pins: pin, IO standard and voltage, direction, drive and slew, series resistor, the external device and what it expects.
- throughput and latency: the rate or delay, and the two events it is measured between; a latency in cycles of which clock.
- resource budget: the part, the budget (LUT, FF, BRAM, DSP), the clock to close at.
- timing-closure risk: the longest arithmetic or lookup path against the clock period.
- numeric formats: signed or unsigned, width, fractional bits, rounding, overflow (wrap or saturate), the units of every number.
- error and back-pressure: what happens on an invalid input, a full buffer, a stalled consumer, a dropped valid.
- power-up state: the state at configuration, before the first reset.
- test strategy: how each requirement is checked, and what the board can measure.
"""

KB_SKILL_ID = "procedures/requirements-review"


def load_checklist(knowledge: str | os.PathLike[str] | None = None) -> tuple[str, str]:
    """``(text, source)``: the knowledge-bank skill when the bank is at hand (``FDA_KNOWLEDGE``), else the public fallback. The source names the skill id and
    the file's SHA-256 so a record says which checklist was used; the skill's text is private and is never copied into a public file."""
    import hashlib
    root = Path(knowledge or os.environ.get("FDA_KNOWLEDGE") or "")
    f = root / "procedures" / "requirements-review" / "SKILL.md"
    if str(root) and f.is_file():
        t = f.read_text()
        return t, f"{KB_SKILL_ID}@sha256:{hashlib.sha256(t.encode()).hexdigest()[:12]}"
    return FALLBACK_CHECKLIST, "public fallback checklist"


# ---- the prompts (public: written for this agent; they carry no benchmark text) ----------------------------------------------------------
REVIEWER_SYSTEM = """You are the requirements reviewer: an experienced FPGA engineer who reads a set of requirements before anyone builds the design, and says what must be settled first.
You are shown the request, the requirements, the interface summary and a checklist. You never see any RTL.
Answer with ONE JSON object and nothing else:
{"findings": [{"topic": "<a checklist topic>", "ids": ["<requirement ids, or empty>"], "missing_fact": "<the missing fact in a few words>", "question": "<one question to put to the user>", "blocking": true|false, "why": "<one line>"}],
 "compliance": [{"id": "<requirement id>", "status": "compliant"|"partial"|"non_compliant"|"tbc", "why": "<one line>", "risk": {"owner": "<who>", "mitigation": "<prototype | change the implementation | challenge the requirement and its margins>"}}],
 "verdict": "ready"|"not_ready"}
Rules:
- A finding is BLOCKING only when a builder would have to guess a fact, and a wrong guess changes behaviour that the ports, the files or a test can observe (a value, a latency in cycles, a file name or extension, a default, a reset value, a protocol rule). A preference, a style choice or something that is easy to change later is not blocking: either leave it out or mark it blocking:false.
- Ask only what the request and the requirements do not already state. Never invent a fact, never propose an answer as if it were given, never ask about the implementation.
- Name the missing fact precisely (the value, the cycle count, the file, the polarity), not the topic.
- Give each finding to the checklist topic it belongs to. At most 12 findings; fewer is better; an empty list with verdict "ready" is the right answer when nothing needs settling.
- compliance (only when asked for): your judgement from analysis, not evidence, of whether each requirement can be met on the stated board, part and budget. For partial, non_compliant or tbc give a risk with an owner and a mitigation.
- verdict is "not_ready" if and only if at least one finding is blocking."""

PROBE_SYSTEM = """You write probe scenarios for a hardware requirements set. Two other readers will each predict, from the requirements alone, what a correct design does in each scenario; where they differ, the requirements are ambiguous. You do not answer the probes.
Answer with ONE JSON object and nothing else: {"probes": [{"id": "P1", "category": "reset|boundary|simultaneous|overflow|back_pressure|unmapped|mid_operation_reset|invalid_input|power_up", "requirements": ["<ids>"], "scenario": "<a concrete situation, with the values>", "question": "<what a reader must predict>", "answer_kind": "bool"|"int"|"choice", "choices": ["<for choice only, at least two>"]}]}
Rules: 8 to 14 probes, one per situation; concrete values, not generalities; cover reset, boundary values, simultaneous events, overflow or saturation, back-pressure or stalls when the interface has them, unmapped or reserved accesses when there are registers, a reset in the middle of an operation, and an invalid input. A bool answer is yes or no; an int answer is a number (a cycle count, a value); a choice lists the possible behaviours. Ask for the behaviour the requirements fix, not for an opinion."""

READER_SYSTEM = """You are a careful reader of a hardware requirements set. You see only the requirements and the interface table, nothing else, and you have no other knowledge of the design.
For each probe, predict exactly what a correct design does, using ONLY what the requirements say. If the requirements do not decide the behaviour, answer "unspecified": do not fill the gap with a common convention, a guess or the most likely behaviour.
Answer with ONE JSON object and nothing else: {"answers": [{"id": "<probe id>", "answer": "<yes|no, or a number, or one of the choices, or unspecified>", "basis": "<the requirement id that decides it, or none>"}]}"""

L2_SYSTEM = """You write the structured form of one hardware requirement from its English sentence and the interface table. You see nothing else.
Answer with ONE JSON object and nothing else: {"scope": "<the state or mode in which it applies, or empty>", "condition": "<the event or condition that triggers it>", "component": "<what responds>", "timing": {"kind": "immediately|within|after|for|until|always|eventually", "n": <number or [low, high] or null>, "clock": "<a clock of the design>", "from": "<the event the count starts from>"}, "response": "<what holds or happens>"}
"within n" means some time in 1..n cycles; "after n" means exactly n cycles later; a tick is one cycle of the stated clock. If the English does not say, write "unspecified" in that field: do not guess."""

AMEND_SYSTEM = """You update a hardware requirements set from the user's answers to questions. You are shown the current rows, the questions and the answers.
Answer with ONE JSON object and nothing else: {"upsert": [{"id": "<existing id, or a new id>", "text": "<one checkable statement>", "proof": ["simulation"|"formal"|"hardware"|"analysis"], "kind": "...", "modal": "shall|should|will", "source": "answer <question id>", "l2": {...}, "worked": ["..."], "never": "..."}], "delete": ["<ids>"], "reason": "<one line>"}
Rules: change only what an answer decides; keep every other row as it is (do not list it). A row you change keeps its id. A new requirement takes a NEW id, never the id of a deleted row. Use the user's answer as given; never add a fact no answer or row states. One property per row. Do not name an implementation. If an answer is "not specified", leave the matter open: change nothing for it."""


# ---- plumbing --------------------------------------------------------------------------------------------------------------------------
_JSON = re.compile(r"\{.*\}", re.S)


def parse_json(text: str) -> dict[str, Any] | None:
    """The first JSON object of a reply (a reply may wrap it in a fence or a sentence); None when there is none."""
    t = str(text or "").strip()
    for cand in (t, *(_JSON.findall(t))):
        try:
            d = json.loads(cand)
        except ValueError:
            continue
        if isinstance(d, dict):
            return d
    return None


@dataclass
class LLMs:
    """The model calls of stage 0, each ``(system, user) -> text``. Two readers are two calls of the same function: no shared history."""
    review: LLM
    reader: LLM
    reader3: LLM | None = None


@dataclass
class Q:
    id: str
    text: str
    code: str = ""
    topic: str = "requirement"
    ids: list[str] = field(default_factory=list)
    blocking: bool = True
    source: str = "code"          # code | reviewer | readers
    answer: str | None = None
    by: str | None = None
    evidence: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text, "code": self.code, "topic": self.topic, "ids": self.ids, "blocking": self.blocking, "source": self.source,
                "answer": self.answer, "by": self.by, "evidence": self.evidence}


class Answerer(Protocol):
    name: str

    def answer(self, q: Any) -> tuple[str, str | None]: ...


class Budget:
    """Counts the model calls of stage 0; a refusal is the stop rule, never a silent skip."""

    def __init__(self, limits: R.Limits):
        self.limits, self.calls, self.log = limits, 0, []

    def spend(self, role: str) -> bool:
        if self.calls >= self.limits.max_calls:
            return False
        self.calls += 1
        self.log.append(role)
        return True


# ---- tables for the model ----------------------------------------------------------------------------------------------------------------
def interface_table(spec: dict[str, Any]) -> str:
    rows = []
    for p in spec.get("ports") or []:
        if isinstance(p, dict) and p.get("name"):
            rows.append(f"- {p['name']} ({p.get('dir', p.get('direction', '?'))}, {p.get('width', 1)} bit, clock {p.get('clock') or '-'})" + (f": {p['note']}" if p.get("note") else ""))
    clocks = ", ".join(f"{c.get('name') or c.get('port')} ({c.get('freq_mhz') or c.get('frequency') or c.get('mhz') or '?'} MHz)" for c in spec.get("clocks") or [] if isinstance(c, dict))
    rst = spec.get("reset") or {}
    return "\n".join(rows) + (f"\nClocks: {clocks}" if clocks else "") + (f"\nReset: {rst}" if rst else "")


def rows_text(spec: dict[str, Any], *, structured: bool = False) -> str:
    out = []
    for r in R.reqs_of(spec):
        line = f"{r['id']}: {R.norm(r.get('text'))}"
        if structured and r.get("l2"):
            line += f"\n    structured: {json.dumps(r['l2'], sort_keys=True)}"
        out.append(line)
    return "\n".join(out)


# ---- the roles ---------------------------------------------------------------------------------------------------------------------------
def review(llm: LLM, request: str, spec: dict[str, Any], checklist: str, *, want_compliance: bool, board: str = "") -> dict[str, Any]:
    user = (f"Request:\n{request.strip()}\n\nRequirements:\n{rows_text(spec)}\n\nInterface:\n{interface_table(spec)}\n\n"
            + (f"Board: {board}\n\n" if board else "") + f"Checklist:\n{checklist}\n\n"
            + ("Also give the compliance assessment of every requirement.\n" if want_compliance else "Do not give a compliance assessment (leave compliance empty).\n"))
    d = parse_json(llm(REVIEWER_SYSTEM, user)) or {}
    return clean_review(d)


def clean_review(d: dict[str, Any]) -> dict[str, Any]:
    fs = []
    for f in d.get("findings") or []:
        if isinstance(f, dict) and R.norm(f.get("question")):
            fs.append({"topic": str(f.get("topic") or "requirement"), "ids": [str(i) for i in f.get("ids") or []], "missing_fact": R.norm(f.get("missing_fact")),
                       "question": R.norm(f["question"]), "blocking": bool(f.get("blocking", True)), "why": R.norm(f.get("why"))})
    comp = []
    for c in d.get("compliance") or []:
        if isinstance(c, dict) and c.get("id") and c.get("status") in R.COMPLIANCE:
            comp.append({"id": str(c["id"]), "status": c["status"], "why": R.norm(c.get("why")), "risk": c.get("risk") if isinstance(c.get("risk"), dict) else {}})
    blocking_any = any(f["blocking"] for f in fs)
    return {"findings": fs, "compliance": comp, "verdict": "not_ready" if blocking_any else "ready"}      # the verdict follows the findings, whatever the model wrote


def write_probes(llm: LLM, spec: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    d = parse_json(llm(PROBE_SYSTEM, f"Requirements:\n{rows_text(spec, structured=True)}\n\nInterface:\n{interface_table(spec)}\n")) or {}
    probes = [p for p in d.get("probes") or [] if isinstance(p, dict)]
    for i, p in enumerate(probes):
        p.setdefault("id", f"P{i + 1}")
        p["id"] = str(p["id"])
    return probes, R.probe_problems(probes, spec)


def read(llm: LLM, spec: dict[str, Any], probes: list[dict[str, Any]]) -> dict[str, Any]:
    """One reader: sees the requirements (English only) and the interface table, and the probes with their answer kinds."""
    pt = "\n".join(f"{p['id']} [{p.get('answer_kind')}{': ' + ' | '.join(map(str, p.get('choices') or [])) if p.get('answer_kind') == 'choice' else ''}] {p.get('scenario')} -- {p.get('question')}" for p in probes)
    user = f"Requirements:\n{rows_text(spec)}\n\nInterface:\n{interface_table(spec)}\n\nProbes:\n{pt}\n"
    d = parse_json(llm(READER_SYSTEM, user)) or {}
    return {str(a.get("id")): a.get("answer") for a in d.get("answers") or [] if isinstance(a, dict)}


def third_reader_l2(llm: LLM, row: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any] | None:
    d = parse_json(llm(L2_SYSTEM, f"Requirement {row['id']}: {R.norm(row.get('text'))}\n\nInterface:\n{interface_table(spec)}\n"))
    return d if isinstance(d, dict) and d else None


def amend(llm: LLM, spec: dict[str, Any], qa: list[Q]) -> dict[str, Any]:
    qt = "\n".join(f"{q.id}: Q: {q.text}\n    A: {q.answer}" for q in qa)
    return parse_json(llm(AMEND_SYSTEM, f"Current rows:\n{yaml.safe_dump(R.reqs_of(spec), sort_keys=False)}\nQuestions and answers:\n{qt}\n")) or {}


def apply_amendment(spec: dict[str, Any], led: dict[str, Any], am: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    """Apply the amender's change with the code's checks: an upsert of an existing id is a declared revision; a new id must not be in the ledger (deleted or
    not); a deleted id stays in the ledger. Returns ``(spec, revised_ids, refused)``; a refused item is listed, never applied."""
    spec = json.loads(json.dumps(spec))
    rows = spec.setdefault("requirements", [])
    by = {str(r["id"]): r for r in rows if isinstance(r, dict) and r.get("id")}
    revised, refused = [], []
    for u in am.get("upsert") or []:
        if not isinstance(u, dict) or not u.get("id") or not R.norm(u.get("text")):
            refused.append(f"upsert without id or text: {u!r}"[:160])
            continue
        rid = str(u["id"])
        if rid in by:
            by[rid].update({k: v for k, v in u.items() if k != "id"})
            revised.append(rid)
        elif rid in (led.get("ids") or {}):
            refused.append(f"{rid} was used before (an id is never reused)")
        else:
            u = {**u, "id": rid}
            if not u.get("proof"):
                u["proof"] = ["simulation"]
            rows.append(u)
            by[rid] = u
    for rid in am.get("delete") or []:
        rows[:] = [r for r in rows if str(r.get("id")) != str(rid)]
    return spec, revised, refused


# ---- the loop ----------------------------------------------------------------------------------------------------------------------------
@dataclass
class Result:
    spec: dict[str, Any]
    frozen: bool
    stop: str | None
    state: dict[str, Any]
    open_questions: list[Q] = field(default_factory=list)


def _dedupe(qs: list[Q]) -> list[Q]:
    seen, out = set(), []
    for q in qs:
        k = re.sub(r"\W+", " ", q.text.lower()).strip()[:120]
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out


def run_stage0(design: Path, spec: dict[str, Any], request: str, *, level: str, llms: LLMs, answerer: Answerer | None = None, limits: R.Limits | None = None,
               checklist: tuple[str, str] | None = None, board: str = "", answers: dict[str, Any] | None = None, on_round: Callable[[dict[str, Any]], None] | None = None) -> Result:
    """Rounds of: mechanical checks, the reviewer, the probes and two readers (and the third reader at strict), then the questions to the user (or the oracle),
    then the amender. Freezes when no blocking problem is left and the readers agree on every probe; otherwise stops at a limit with the open questions.
    ``answers`` are a person's answers by question id (``requirements_answers.yaml``) applied before the first round."""
    design = Path(design)
    limits = limits or R.Limits()
    budget = Budget(limits)
    checklist = checklist or load_checklist()
    sva, conf = R.load_sva(design), R.load_yaml(design / R.CONFIRMATIONS_FILE)
    state: dict[str, Any] = {"schema": R.SCHEMA, "level": level, "limits": limits.as_dict(), "checklist": checklist[1], "started": R.now(), "rounds": [], "frozen": None,
                             "stop": None, "answerer": getattr(answerer, "name", None)}
    prev = R.load_yaml(design / R.STATE_DIR[0] / R.STATE_DIR[1] / "readiness_open.yaml") if answers else {}
    open_qs: list[Q] = [Q(**{k: v for k, v in q.items() if k in Q.__dataclass_fields__}) for q in (prev.get("open") or [])]
    probes: list[dict[str, Any]] | None = None
    asked_total = 0
    R.update_ledger(design, spec)                  # every id of the starting set is on record before any amendment: a deleted id stays retired
    for n in range(1, limits.max_rounds + 1):
        rnd: dict[str, Any] = {"n": n, "questions": [], "amendments": [], "refused": []}
        # 0. answers a person gave to the questions left open by the last stop
        if n == 1 and answers and open_qs:
            for q in open_qs:
                a = answers.get(q.id)
                if isinstance(a, dict):
                    q.answer, q.by = str(a.get("answer", "")), str(a.get("who") or "user")
                elif a:
                    q.answer, q.by = str(a), "user"
            given = [q for q in open_qs if q.answer]
            if given and budget.spend("amend"):
                spec, rev, ref = _amend_apply(design, spec, llms.review, given, rnd)
                rnd["questions"] += [q.as_dict() for q in given]
                rnd["amendments"], rnd["refused"] = rev, ref
            open_qs = [q for q in open_qs if not q.answer]
        led = R.read_ledger(design)
        # 1. the mechanical checks
        mech = R.mechanical_problems(design, spec, level=level, sva=sva, confirmations=conf)
        rnd["mechanical"] = [p.as_dict() for p in mech]
        qs: list[Q] = [Q(id="", text=p.question, code=p.code, topic=p.topic, ids=[p.id] if p.id not in ("interface", "set", "trace") else [], blocking=p.blocks(level), source="code")
                       for p in mech if p.blocks(level)]
        # 2. the reviewer (round 1, and again when rows changed)
        if budget.spend("review"):
            rv = review(llms.review, request, spec, checklist[0], want_compliance=level == "strict" and not any(isinstance(r.get("compliance"), (dict, str)) for r in R.reqs_of(spec)), board=board)
            rnd["review"] = {"findings": rv["findings"], "verdict": rv["verdict"], "compliance": len(rv["compliance"])}
            for f in rv["findings"]:
                if f["blocking"]:
                    qs.append(Q(id="", text=f["question"], code="RDY-REV-01", topic=f["topic"], ids=f["ids"], blocking=True, source="reviewer"))
            by = {str(r["id"]): r for r in R.reqs_of(spec)}
            for c in rv["compliance"]:
                if c["id"] in by and not by[c["id"]].get("compliance"):
                    by[c["id"]]["compliance"] = {"status": c["status"], "why": c["why"], "risk": c["risk"], "by": "reviewer", "when": R.now()}
        # 3. probes and readers
        ag = None
        if R.reqs_of(spec) and budget.calls + 3 <= limits.max_calls:
            if probes is None or rnd["amendments"]:
                budget.spend("probes")
                probes, perr = write_probes(llms.review, spec)
                rnd["probes"] = {"count": len(probes), "categories": sorted({str(p.get("category")) for p in probes}), "problems": perr}
            if probes and not rnd.get("probes", {}).get("problems", []):
                budget.spend("reader_a")
                a = read(llms.reader, spec, probes)
                budget.spend("reader_b")
                b = read(llms.reader, spec, probes)
                ag = R.compare_readers(probes, {"A": a, "B": b})
                rnd["agreement"] = ag.as_dict()
                rnd["probe_set"] = [{k: p.get(k) for k in ("id", "category", "answer_kind", "requirements")} for p in probes]       # the probe text stays in readiness.json only
                rnd["probe_text"] = probes
                rnd["answers"] = {"A": a, "B": b}
                qs += [Q(id="", text=p.question, code=p.code, topic="requirement", ids=[x for x in p.id.split(",") if x not in ("set",)], blocking=True, source="readers")
                       for p in R.questions_from_agreement(ag)]
            elif probes:
                qs.append(Q(id="", text="the probe set is not usable: " + "; ".join(rnd["probes"]["problems"][:3]), code="RDY-PROBE-01", blocking=True, source="readers"))
                probes = None
        if level == "strict" and llms.reader3 and R.reqs_of(spec):
            diffs = []
            for r in R.reqs_of(spec):
                if r.get("kind") in R.FORMAL_KINDS and isinstance(r.get("l2"), dict) and budget.spend("reader3"):
                    l2b = third_reader_l2(llms.reader3, r, spec)
                    d = R.l2_diff(r["l2"], l2b) if l2b else ["the third reader returned no structured layer"]
                    if d:
                        diffs.append({"id": str(r["id"]), "diff": d})
                        qs.append(Q(id="", text=f"{r['id']}: the structured layer written by a different reader from your English differs ({'; '.join(d)[:200]}). Which is what you mean?",
                                    code="RDY-L2-07", topic="requirement", ids=[str(r["id"])], blocking=True, source="readers"))
            rnd["l2_diffs"] = diffs
        qs = _dedupe(qs)
        for q in qs:
            asked_total += 1
            q.id = f"Q{asked_total}"
        # 4. done?
        if not qs and (ag is None or ag.ok):
            R.update_ledger(design, spec)
            rec = R.freeze(design, spec, level=level, rounds=n)
            state["frozen"] = rec
            state["rounds"].append(rnd)
            if on_round:
                on_round(rnd)
            return _finish(design, spec, state, [], None, budget)
        # 5. ask
        answered: list[Q] = []
        if answerer is not None:
            for q in qs[: max(0, limits.max_questions - sum(len(r["questions"]) for r in state["rounds"]))]:
                a, ev = answerer.answer(q)
                if str(a).strip().lower() not in ("", "not specified"):
                    q.answer, q.by, q.evidence = a, getattr(answerer, "name", "answerer"), ev
                    answered.append(q)
        rnd["questions"] += [q.as_dict() for q in qs]
        # 6. amend from the answers
        if answered and budget.spend("amend"):
            before = spec
            spec, rev, ref = _amend_apply(design, spec, llms.review, answered, rnd)
            rnd["amendments"], rnd["refused"] = rev, ref
            if rev or ref or spec != before:
                R.update_ledger(design, spec, revised=rev)
        open_qs = [q for q in qs if not q.answer]
        state["rounds"].append(rnd)
        if on_round:
            on_round(rnd)
        if not answered:                       # nobody can answer: another round would ask the same questions
            state["stop"] = "no answer was available for the open questions"
            return _finish(design, spec, state, open_qs, state["stop"], budget)
        if budget.calls >= limits.max_calls:
            state["stop"] = f"the model-call budget ({limits.max_calls}) is used up"
            return _finish(design, spec, state, open_qs, state["stop"], budget)
    state["stop"] = f"the round limit ({limits.max_rounds}) was reached with questions still open"
    return _finish(design, spec, state, open_qs, state["stop"], budget)


def _amend_apply(design: Path, spec: dict[str, Any], llm: LLM, answered: list[Q], rnd: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    am = amend(llm, spec, answered)
    spec2, rev, ref = apply_amendment(spec, R.read_ledger(design), am)
    return spec2, rev, ref


def _finish(design: Path, spec: dict[str, Any], state: dict[str, Any], open_qs: list[Q], stop: str | None, budget: Budget) -> Result:
    state["finished"] = R.now()
    state["model_calls"] = budget.calls
    state["calls_by_role"] = {r: budget.log.count(r) for r in sorted(set(budget.log))}
    state["open"] = [q.as_dict() for q in open_qs]
    return Result(spec=spec, frozen=bool(state.get("frozen")), stop=stop, state=state, open_questions=open_qs)


# ---- records and reports -----------------------------------------------------------------------------------------------------------------
def write_records(design: Path, res: Result) -> None:
    d = Path(design).joinpath(*R.STATE_DIR)
    d.mkdir(parents=True, exist_ok=True)
    (d / R.READINESS_FILE).write_text(json.dumps(res.state, indent=1, default=str) + "\n")
    (d / "readiness_open.yaml").write_text(yaml.safe_dump({"open": [q.as_dict() for q in res.open_questions]}, sort_keys=False))
    (Path(design) / "spec.yaml").write_text(yaml.safe_dump(res.spec, sort_keys=False))
    (Path(design) / REPORT_FILE).write_text(report_markdown(res))
    needed = Path(design) / NEEDED_FILE
    if res.stop:
        needed.write_text(needed_markdown(res))


def report_markdown(res: Result) -> str:
    st = res.state
    rounds = st.get("rounds") or []
    out = [f"# Requirements readiness: {'frozen' if res.frozen else 'NOT ready'}", "",
           f"Level **{st.get('level')}**; checklist: {st.get('checklist')}; limits: {st.get('limits')}. Rounds used: {len(rounds)}. Model calls: {st.get('model_calls')}.", ""]
    if res.stop:
        out += [f"**Stopped: {res.stop}.** See `{NEEDED_FILE}`.", ""]
    if st.get("frozen"):
        fr = st["frozen"]
        out += [f"Frozen at {fr['frozen_at']} (version {fr['version']}, hash `{fr['hash']}`): {len(fr['ids'])} requirements. Later stages read this set; a change returns to stage 0 and is recorded.", ""]
    out += ["| Round | Questions asked | Answered | Probes | Reader agreement | Disagreements | Gaps |", "|---|---|---|---|---|---|---|"]
    for r in rounds:
        ag = r.get("agreement") or {}
        qs = r.get("questions") or []
        out.append(f"| {r['n']} | {len(qs)} | {sum(bool(q.get('answer')) for q in qs)} | {(r.get('probes') or {}).get('count', '-')} | "
                   f"{(str(round(ag['rate'] * 100)) + '%') if ag else '-'} | {len(ag.get('disagreements', []))} | {len(ag.get('gaps', []))} |")
    out += ["", "A probe set can be too small to find the ambiguity that matters: the number of probes and their categories are in `build/requirements/readiness.json`. "
            "Two readers who agree have read the requirements the same way; they can share a misreading, which is why the third reader is a different model and why the user's "
            "confirmation of each requirement from its show-back packet is a separate field (`validated_by_user`), never inferred from agreement.", ""]
    return "\n".join(out)


def needed_markdown(res: Result) -> str:
    out = ["# Requirements needed before this design can proceed", "", f"Requirements readiness stopped: {res.stop}. Nothing was built.", "",
           f"Answer each question in `{R.ANSWERS_FILE}` (`Q1: <your answer>`, or `Q1: {{answer: ..., who: ...}}`), then run again; or answer through the interview.", "",
           "| Id | Topic | Question | Where it came from |", "|---|---|---|---|"]
    for q in res.open_questions:
        out.append(f"| {q.id} | {q.topic} | {R._c(q.text)} | {q.source} ({q.code}) |")
    return "\n".join(out) + "\n"


def stop_text(res: Result) -> str:
    return f"{STOP_PREFIX} readiness: {res.stop}; {len(res.open_questions)} open question(s) (see {NEEDED_FILE})"


def load_answers(design: Path, *dirs: Path) -> dict[str, Any]:
    for d in (Path(design), *dirs):
        f = Path(d) / R.ANSWERS_FILE
        if f.is_file():
            doc = R.load_yaml(f)
            return doc.get("answers", doc) if isinstance(doc, dict) else {}
    return {}


# ---- the run hook and the command line ---------------------------------------------------------------------------------------------------
def gate_step(rt: Any, spec: dict[str, Any], level: str, answerer: Answerer | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The stage-0 hook of ``agent run --readiness on`` (after the interview). Returns ``(spec, summary)``; ``summary['requirements_stop']`` is set when the
    gate did not pass. The models are the purposes ``reqreview``, ``reqreader`` and ``reqreader3``."""
    log = rt.run_dir / "claude_code_calls.jsonl"
    llms = LLMs(review=rt.resolver.text("reqreview", label="reqreview", claude_log=log), reader=rt.resolver.text("reqreader", label="reqreader", claude_log=log),
                reader3=rt.resolver.text("reqreader3", label="reqreader3", claude_log=log))
    request = (rt.design / "spec.md").read_text(errors="replace") if (rt.design / "spec.md").is_file() else ""
    lim = R.Limits(**{k: int(v) for k, v in (getattr(rt.cfg, "readiness_limits", None) or {}).items() if k in R.Limits.__dataclass_fields__})
    res = run_stage0(rt.design, spec, request, level=level, llms=llms, answerer=answerer, limits=lim, board=getattr(rt.cfg, "board", ""), answers=load_answers(rt.design))
    write_records(rt.design, res)
    summ = {"readiness": {"frozen": res.frozen, "rounds": len(res.state["rounds"]), "stop": res.stop, "level": level}}
    if res.stop:
        summ["requirements_stop"] = stop_text(res)
    return res.spec, summ


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Stage 0 only: requirements readiness on a design directory (spec.md, spec.yaml) with the Claude Code CLI.")
    ap.add_argument("design")
    ap.add_argument("--level", choices=R.LEVELS, default="standard")
    ap.add_argument("--hidden-spec", help="the spec an oracle answers from (evaluation runs); without it nobody answers and the run stops with the questions")
    ap.add_argument("--max-rounds", type=int, default=4)
    ap.add_argument("--max-calls", type=int, default=60)
    ap.add_argument("--review-model", default="claude-sonnet-5-5")
    ap.add_argument("--reader-model", default="claude-sonnet-5-5")
    ap.add_argument("--reader3-model", default="claude-haiku-5-5", help="a different model from the readers")
    a = ap.parse_args(argv)
    from agent.access import require_or_exit
    require_or_exit("python -m agent.graph.readiness")
    from agent.models import claude_cli

    def call(model: str, effort: str = "low") -> LLM:
        return lambda system, user: str(claude_cli.text_call(system, user, model=model, effort=effort, timeout_s=600).get("result", ""))
    design = Path(a.design)
    spec = R.load_yaml(design / "spec.yaml")
    request = (design / "spec.md").read_text(errors="replace") if (design / "spec.md").is_file() else ""
    who = None
    if a.hidden_spec:
        from agent.graph.interview import SpecOracle

        def oracle_llm(system: str, user: str) -> dict[str, Any]:
            return parse_json(call(a.review_model)(system, user)) or {}
        who = SpecOracle(Path(a.hidden_spec), oracle_llm)
    res = run_stage0(design, spec, request, level=a.level, llms=LLMs(review=call(a.review_model, "medium"), reader=call(a.reader_model), reader3=call(a.reader3_model)),
                     answerer=who, limits=R.Limits(max_rounds=a.max_rounds, max_calls=a.max_calls), answers=load_answers(design))
    write_records(design, res)
    print(("frozen" if res.frozen else "NOT ready") + f" after {len(res.state['rounds'])} round(s)" + (f": {res.stop}" if res.stop else ""))
    return 0 if res.frozen else 3


if __name__ == "__main__":
    raise SystemExit(main())
