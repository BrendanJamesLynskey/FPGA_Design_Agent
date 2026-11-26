"""Stage 0 until the requirements are ready (brief 227): the roles, the rounds and the stop rule. The checks are in ``flow/readiness.py`` (code only).

The process the owner asked for (2026-11-25): 1) requirements building, iterated until they are unambiguous and satisfactory to the agent; 2) build
and verify, reading the frozen set. "Satisfactory to the agent" has a measure: **two fresh readers who share no history predict the same behaviour on
the same probe set, and no question is open** (``flow.readiness.compare_readers``; code compares, no model judges). A third reader, a different model,
writes the structured layer from the user's English alone; a difference from the first structured layer is an ambiguity too.

Roles (each its own model call; none sees the RTL; the purposes ``reqreview``, ``reqreader`` and ``reqreader3`` of the model table):

- the **requirements reviewer**: an experienced FPGA engineer's pre-build questions by checklist topic (the knowledge-bank skill
  ``procedures/requirements-review/pre-build-review``, cited by id; a short public fallback when the bank is not present), and the early compliance assessment;
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

#: the checklist topics (the headings of the knowledge-bank skill ``procedures/requirements-review/pre-build-review``). A topic list is general engineering practice, so
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

KB_SKILL_ID = "procedures/requirements-review/pre-build-review"


def load_checklist(knowledge: str | os.PathLike[str] | None = None) -> tuple[str, str]:
    """``(text, source)``: the knowledge-bank skill when the bank is at hand (``FDA_KNOWLEDGE``), else the public fallback. The source names the skill id and
    the file's SHA-256 so a record says which checklist was used; the skill's text is private and is never copied into a public file."""
    import hashlib
    root = Path(knowledge or os.environ.get("FDA_KNOWLEDGE") or "")
    f = root / "procedures" / "requirements-review" / "pre-build-review" / "SKILL.md"
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

REVIEWER_SYSTEM_V2 = """You are the requirements reviewer: an experienced FPGA engineer who reads a set of requirements before anyone builds the design, and says what must be settled first.
You are shown the request, the requirements, the interface summary and a checklist. You never see any RTL.
Answer with ONE JSON object and nothing else:
{"findings": [{"topic": "<a checklist topic>", "ids": ["<requirement ids, or empty>"], "missing_fact": "<the missing fact in a few words>", "question": "<one question to put to the user>", "blocking": true|false, "why": "<one line>"}],
 "assumptions": [{"topic": "<a checklist topic>", "assumed": "<the value or behaviour you would assume, in one line>"}],
 "compliance": [{"id": "<requirement id>", "status": "compliant"|"partial"|"non_compliant"|"tbc", "why": "<one line>", "risk": {"owner": "<who>", "mitigation": "<prototype | change the implementation | challenge the requirement and its margins>"}}],
 "verdict": "ready"|"not_ready"}
Sort every gap you find into one of three classes before you write it down:
1. BLOCKING finding: the request leaves two or more reasonable designs that differ in something a port, a file name, a register, a report or a test can observe, AND nothing the request gives (its text, tables, examples, names or ordinary engineering convention) chooses between them. A wrong guess here would go unnoticed until a check fails.
2. ASSUMPTION: a conventional default would settle it (outputs reset to zero, an enable that is active high, binary encoding, synchronous reset, the obvious reading of an example, a tolerance nobody needs to state). Do not ask. Write it in assumptions with the value you would assume. Do not also make it a finding.
3. Not worth writing: a preference, a style, a name that is easy to change, anything the request already states.
Rules:
- Before you mark a finding blocking, read the request again for the fact: tables, examples, parameter lists and wording that implies a rule all count as stating it. A fact that is stated is never a finding.
- Ask only about the design the request describes; never invent a requirement, never propose an answer as if it were given, never ask about the implementation.
- Name the missing fact precisely (the value, the cycle count, the polarity, the file), not the topic.
- At most 5 blocking findings. With more candidates, keep the ones whose wrong guess would be hardest to notice (a silently wrong value, latency, name or file) and move the rest to assumptions. An empty findings list with verdict "ready" is the right answer when nothing needs settling.
- compliance (only when asked for): your judgement from analysis, not evidence, of whether each requirement can be met on the stated board, part and budget; for partial, non_compliant or tbc give a risk with an owner and a mitigation.
- verdict is "not_ready" if and only if at least one finding is blocking."""

REVIEWERS = {"v1": REVIEWER_SYSTEM, "v2": REVIEWER_SYSTEM_V2}
#: the product's reviewer. v1 was pre-registered and over-asks (it flagged 16 of 23 sound problems of the reviewer test set, 3.3 blocking questions each); v2 was written after seeing that and is an
#: exploratory, not confirmed, improvement (results/227_requirements_readiness/README.md). The test set keeps both so the comparison stays reproducible.
DEFAULT_REVIEWER = "v2"

PROBE_SYSTEM = """You write probe scenarios for a hardware requirements set. Two other readers will each predict, from the requirements alone, what a correct design does in each scenario; where they differ, the requirements are ambiguous. You do not answer the probes.
Answer with ONE JSON object and nothing else: {"probes": [{"id": "P1", "category": "reset|boundary|simultaneous|overflow|back_pressure|unmapped|mid_operation_reset|invalid_input|power_up", "requirements": ["<ids>"], "scenario": "<a concrete situation, with the values>", "question": "<what a reader must predict>", "answer_kind": "bool"|"int"|"choice", "choices": ["<for choice only, at least two>"]}]}
Rules: 8 to 14 probes, one per situation; concrete values, not generalities; cover reset, boundary values, simultaneous events, overflow or saturation, back-pressure or stalls when the interface has them, unmapped or reserved accesses when there are registers, a reset in the middle of an operation, and an invalid input. A bool answer is yes or no; an int answer is a number (a cycle count, a value); a choice lists the possible behaviours. Ask for the behaviour the requirements fix, not for an opinion."""

READER_SYSTEM = """You are a careful reader of a hardware requirements set. You see only the requirements and the interface table, nothing else, and you have no other knowledge of the design.
For each probe, predict exactly what a correct design does, using ONLY what the requirements say. If the requirements do not decide the behaviour, answer "unspecified": do not fill the gap with a common convention, a guess or the most likely behaviour.
Answer with ONE JSON object and nothing else: {"answers": [{"id": "<probe id>", "answer": "<yes|no, or a number, or one of the choices, or unspecified>", "basis": "<the requirement id that decides it, or none>"}]}"""

L2_SYSTEM = """You write the structured form of one hardware requirement from its English sentence and the interface table. You see nothing else.
Answer with ONE JSON object and nothing else: {"scope": "<the state or mode in which it applies, or empty>", "condition": "<the event or condition that triggers it>", "component": "<what responds>", "timing": {"kind": "immediately|within|after|for|until|always|eventually", "n": <number or [low, high] or null>, "clock": "<a clock of the design>", "from": "<the event the count starts from>"}, "response": "<what holds or happens>"}
"within n" means some time in 1..n cycles; "after n" means exactly n cycles later; a tick is one cycle of the stated clock. If the English does not say, write "unspecified" in that field: do not guess."""

FORMALISE_SYSTEM = """You write the structure of hardware requirements for review, from their English sentences, the interface table and the request. You see no RTL.
Answer with ONE JSON object and nothing else: {"goals": [{"id": "G1", "text": "<a goal of the user, from the request>"}], "rows": [{"id": "<requirement id>", "kind": "interface|timing|protocol|functional|reset|budget|board|other", "modal": "shall|should|will", "method": "Test|Analysis|Inspection|Demonstration", "evidence": "<what will be named as the evidence>", "trace_up": "<a goal id>", "l2": {"scope": "<state in which it applies, or always>", "condition": "<the triggering event or condition, or empty for a state>", "component": "<what responds>", "timing": {"kind": "immediately|within|after|for|until|always|eventually", "n": <number, [low, high] or null>, "clock": "<a clock of the design>", "from": "<the event the count starts from>"}, "response": "<what holds or happens>"}, "worked": ["<one worked example with numbers>"], "never": "<one thing that must never happen>", "l3": {"sva": true} | {"check": "<name>"} | {"sim_only": "<why>"}}]}
Rules: use ONLY what the English and the request say; where they do not say, write "unspecified" in that field and do not guess. The user will confirm every row from what you write, so it must say what the sentence says. "within n" means some time in 1..n cycles, "after n" exactly n cycles later. l2 and l3 only for kind timing, protocol, reset or functional; a budget, board or interface row has none. l3 sva means a property can be written from l2; sim_only when two unrelated clocks are involved and no relation is stated, or the row is about values over time. The goals come from the request, not from the rows."""

AMEND_SYSTEM = """You update a hardware requirements set from the user's answers to questions, and carry out repairs the checks ask for. You are shown the current rows, the ids already used, the questions with the answers, and the repairs.
Answer with ONE JSON object and nothing else: {"upsert": [{"id": "<existing id, or a new id>", "text": "<one checkable statement>", "proof": ["simulation"|"formal"|"hardware"|"analysis"], "kind": "...", "modal": "shall|should|will", "source": "answer <question id>", "l2": {...}, "worked": ["..."], "never": "..."}], "delete": ["<ids>"], "reason": "<one line>"}
Rules: change only what an answer decides; keep every other row as it is (do not list it). A row you change keeps its id. A new requirement takes a NEW id, never the id of a deleted row. Use the user's answer as given; never add a fact no answer or row states. One property per row. Do not name an implementation. If an answer is "not specified", leave the matter open: change nothing for it.
A repair (split a compound row into one row per statement, drop a duplicate) needs no answer: do it from the rows as written and add no fact. The first part keeps the row's id; each further part takes a new id that is not in the list of ids already used."""


# ---- plumbing --------------------------------------------------------------------------------------------------------------------------
_JSON = re.compile(r"\{.*\}", re.S)
_LAST_REPLY: list[str] = []          # the last unreadable reader replies (the start of each), kept for the record of a tool fault


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
    default: str = ""             # the oracle reads ``q.default``: there is none here (a question asked in stage 0 has no proposed default; the agent never guesses)
    reason: str = ""
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
def review(llm: LLM, request: str, spec: dict[str, Any], checklist: str, *, want_compliance: bool, board: str = "", system: str | None = None) -> dict[str, Any] | None:
    """The review, or None when the reply had no usable findings list (a tool fault: an unreadable reply is never "ready")."""
    user = (f"Request:\n{request.strip()}\n\nRequirements:\n{rows_text(spec)}\n\nInterface:\n{interface_table(spec)}\n\n"
            + (f"Board: {board}\n\n" if board else "") + f"Checklist:\n{checklist}\n\n"
            + ("Also give the compliance assessment of every requirement.\n" if want_compliance else "Do not give a compliance assessment (leave compliance empty).\n"))
    d = parse_json(llm(system or REVIEWERS[DEFAULT_REVIEWER], user))
    return clean_review(d) if d is not None and "findings" in d else None


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
    assumed = [{"topic": str(a.get("topic") or ""), "assumed": R.norm(a.get("assumed"))} for a in d.get("assumptions") or [] if isinstance(a, dict) and R.norm(a.get("assumed"))]
    return {"findings": fs, "assumptions": assumed, "compliance": comp, "verdict": "not_ready" if blocking_any else "ready"}      # the verdict follows the findings, whatever the model wrote


def problem_text(prompt: str, files: dict[str, str], produce: list[str], *, per_file: int = 15000, total: int = 60000) -> str:
    """A whole request as a builder receives it (the problem text, the files it is given with their contents, cut to a budget with a visible mark, and the files it
    must produce), for ``review_problem``: the reviewer reads this and nothing the builder does not have."""
    out, used = [prompt.strip(), ""], 0
    for path, body in files.items():
        body = str(body)
        cut = body[:per_file] + (f"\n[... {len(body) - per_file} more characters of this file not shown ...]" if len(body) > per_file else "")
        if used + len(cut) > total:
            out.append(f"--- {path} --- [not shown: {len(body)} characters]")
            continue
        used += len(cut)
        out += [f"--- {path} ---", cut]
    if produce:
        out += ["", "Files the builder must produce: " + ", ".join(produce)]
    return "\n".join(out)


def review_problem(llm: LLM, text: str, checklist: str, *, system: str | None = None) -> dict[str, Any]:
    """The reviewer on a request alone (no requirement rows, no interface table): used by the reviewer test set. Same system prompt, same cleaning."""
    user = (f"Request (this is the whole of what the builder receives):\n{text}\n\nRequirements: none are written beyond the request.\n\n"
            f"Checklist:\n{checklist}\n\nDo not give a compliance assessment (leave compliance empty).\n")
    return clean_review(parse_json(llm(system or REVIEWER_SYSTEM, user)) or {})


def write_probes(llm: LLM, spec: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    d = parse_json(llm(PROBE_SYSTEM, f"Requirements:\n{rows_text(spec, structured=True)}\n\nInterface:\n{interface_table(spec)}\n")) or {}
    probes = [p for p in d.get("probes") or [] if isinstance(p, dict)]
    for i, p in enumerate(probes):
        p.setdefault("id", f"P{i + 1}")
        p["id"] = str(p["id"])
    return probes, R.probe_problems(probes, spec)


def read(llm: LLM, spec: dict[str, Any], probes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """One reader: sees the requirements (English only) and the interface table, and the probes with their answer kinds."""
    pt = "\n".join(f"{p['id']} [{p.get('answer_kind')}{': ' + ' | '.join(map(str, p.get('choices') or [])) if p.get('answer_kind') == 'choice' else ''}] {p.get('scenario')} -- {p.get('question')}" for p in probes)
    user = f"Requirements:\n{rows_text(spec)}\n\nInterface:\n{interface_table(spec)}\n\nProbes:\n{pt}\n"
    raw = llm(READER_SYSTEM, user)
    d = parse_json(raw)
    if d is None or not isinstance(d.get("answers"), list) or not d["answers"]:
        _LAST_REPLY.append(str(raw))
        del _LAST_REPLY[:-3]
        return None                                                 # an unreadable reply is a tool fault, never "unspecified" (which would look like a disagreement)
    return {str(a.get("id")): a.get("answer") for a in d["answers"] if isinstance(a, dict)}


def third_reader_l2(llm: LLM, row: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any] | None:
    d = parse_json(llm(L2_SYSTEM, f"Requirement {row['id']}: {R.norm(row.get('text'))}\n\nInterface:\n{interface_table(spec)}\n"))
    return d if isinstance(d, dict) and d else None


def formalise(llm: LLM, request: str, spec: dict[str, Any]) -> dict[str, Any]:
    user = f"Request:\n{request.strip()}\n\nRequirements:\n{rows_text(spec)}\n\nInterface:\n{interface_table(spec)}\n"
    return parse_json(llm(FORMALISE_SYSTEM, user)) or {}


def apply_formalisation(spec: dict[str, Any], out: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Fill the structure the formaliser proposed into rows that lack it. Code checks every field (an enumerated kind, modal, method and timing kind) and never overwrites a
    field a person or an earlier round wrote. The result is a **proposal** the user validates: a row it touches is marked ``formalised_by: agent``. Returns (spec, refused)."""
    spec = json.loads(json.dumps(spec))
    refused: list[str] = []
    if not spec.get("goals"):
        gs = [{"id": str(g["id"]), "text": R.norm(g.get("text"))} for g in out.get("goals") or [] if isinstance(g, dict) and g.get("id") and R.norm(g.get("text"))]
        if gs:
            spec["goals"] = gs
    by = {str(r["id"]): r for r in R.reqs_of(spec)}
    goal_ids = {str(g["id"]) for g in spec.get("goals") or []}
    for f in out.get("rows") or []:
        r = by.get(str(f.get("id"))) if isinstance(f, dict) else None
        if r is None:
            continue
        touched = False
        for k, ok in (("kind", R.KINDS), ("modal", R.MODALS), ("method", R.METHODS)):
            v = f.get(k)
            v = v.capitalize() if k == "method" and isinstance(v, str) else v
            if r.get(k) is None and v is not None:
                if v in ok:
                    r[k], touched = v, True
                else:
                    refused.append(f"{r['id']}: {k} {v!r} is not one of {', '.join(ok)}")
        if r.get("evidence") is None and R.norm(f.get("evidence")):
            r["evidence"], touched = R.norm(f["evidence"]), True
        if r.get("trace_up") is None and f.get("trace_up") is not None:
            if str(f["trace_up"]) in goal_ids:
                r["trace_up"], touched = str(f["trace_up"]), True
            else:
                refused.append(f"{r['id']}: trace_up {f['trace_up']!r} is not a goal")
        l2 = f.get("l2")
        if r.get("l2") is None and isinstance(l2, dict) and l2:
            t = l2.get("timing") if isinstance(l2.get("timing"), dict) else {}
            if str(t.get("kind")) in R.TIMING_KINDS:
                r["l2"], touched = {k: l2[k] for k in R.L2_FIELDS if k in l2}, True
            else:
                refused.append(f"{r['id']}: l2.timing.kind {t.get('kind')!r} is not one of {', '.join(R.TIMING_KINDS)}")
        if r.get("worked") is None and isinstance(f.get("worked"), list) and f["worked"]:
            r["worked"], touched = [R.norm(w) for w in f["worked"] if R.norm(w)], True
        if r.get("never") is None and R.norm(f.get("never")):
            r["never"], touched = R.norm(f["never"]), True
        if r.get("l3") is None and isinstance(f.get("l3"), dict) and f["l3"]:
            r["l3"], touched = f["l3"], True
        if r.get("source") is None and not r.get("origin"):
            r["source"], touched = "the request, structured by the agent (to be confirmed)", True
        if touched:
            r["formalised_by"] = "agent"
    return spec, refused


def amend(llm: LLM, spec: dict[str, Any], qa: list[Q], repairs: list[str] | None = None, used_ids: list[str] | None = None) -> dict[str, Any]:
    qt = "\n".join(f"{q.id}: Q: {q.text}\n    A: {q.answer}" for q in qa) or "(none)"
    rp = "\n".join(f"- {t}" for t in repairs or []) or "(none)"
    ids = ", ".join(sorted(set(used_ids or []) | {str(r["id"]) for r in R.reqs_of(spec)})) or "(none)"
    return parse_json(llm(AMEND_SYSTEM, f"Current rows:\n{yaml.safe_dump(R.reqs_of(spec), sort_keys=False)}\nIds already used (never reuse): {ids}\n\n"
                                       f"Questions and answers:\n{qt}\n\nRepairs:\n{rp}\n")) or {}


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
    probes_for = ""
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
        # 0b. strict: the structure of each row (kind, modal, layer 2, worked numbers) is proposed by the agent; it is never taken for the user's confirmation
        if level == "strict" and any(r.get("l2") is None or r.get("kind") is None or r.get("modal") is None for r in R.reqs_of(spec)) and budget.spend("formalise"):
            spec, ref = apply_formalisation(spec, formalise(llms.review, request, spec))
            rnd["formalised"] = {"refused": ref}
        # 1. the mechanical checks; a defect the agent can repair from the rows as written (a compound row, a duplicate) is repaired, not put to the user
        mech = R.mechanical_problems(design, spec, level=level, sva=sva, confirmations=conf)
        fixes = [p for p in mech if p.repair and p.blocks(level)]
        if fixes and budget.spend("repair"):
            spec, rev, ref = _amend_apply(design, spec, llms.review, [], rnd, [f"{p.id}: {p.text}" for p in fixes])
            R.update_ledger(design, spec, revised=rev)
            rnd["repairs"] = {"asked": [p.as_dict() for p in fixes], "revised": rev, "refused": ref}
            mech = R.mechanical_problems(design, spec, level=level, sva=sva, confirmations=conf)
        rnd["mechanical"] = [p.as_dict() for p in mech]
        qs: list[Q] = [Q(id="", text=p.question, code=p.code, topic=p.topic, ids=[p.id] if p.id not in ("interface", "set", "trace") else [], blocking=p.blocks(level), source="code")
                       for p in mech if p.blocks(level)]                     # a repair that did not work is asked of the user
        # 2. the reviewer (round 1, and again when rows changed)
        if budget.spend("review"):
            want = level == "strict" and not any(isinstance(r.get("compliance"), (dict, str)) for r in R.reqs_of(spec))
            rv = review(llms.review, request, spec, checklist[0], want_compliance=want, board=board)
            if rv is None and budget.spend("review_retry"):
                rv = review(llms.review, request, spec, checklist[0], want_compliance=want, board=board)
            if rv is None:
                state["rounds"].append(rnd)
                state["stop"] = "the reviewer returned no usable reply twice (a tool fault, not a requirements question)"
                return _finish(design, spec, state, [], state["stop"], budget)
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
            if probes is None or probes_for != R.rows_hash(spec):          # the rows changed since the probes were written (an answer or a repair): write them again
                budget.spend("probes")
                probes, perr = write_probes(llms.review, spec)
                probes_for = R.rows_hash(spec)
                rnd["probes"] = {"count": len(probes), "categories": sorted({str(p.get("category")) for p in probes}), "problems": perr}
            if probes and not rnd.get("probes", {}).get("problems", []):
                budget.spend("reader_a")
                a = read(llms.reader, spec, probes)
                budget.spend("reader_b")
                b = read(llms.reader, spec, probes)
                for _ in range(2):                                       # an unreadable reply is asked again (a fresh call), at most twice per reader
                    if a is None and budget.spend("reader_a_retry"):
                        a = read(llms.reader, spec, probes)
                    if b is None and budget.spend("reader_b_retry"):
                        b = read(llms.reader, spec, probes)
                if a is None or b is None:
                    rnd["reader_error"] = {"A": a is None, "B": b is None, "last_reply_start": _LAST_REPLY[-1][:300] if _LAST_REPLY else ""}
                    state["rounds"].append(rnd)
                    state["stop"] = "a reader returned no usable answers three times (a tool fault, not a requirements question)"
                    return _finish(design, spec, state, [], state["stop"], budget)
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


def _amend_apply(design: Path, spec: dict[str, Any], llm: LLM, answered: list[Q], rnd: dict[str, Any], repairs: list[str] | None = None) -> tuple[dict[str, Any], list[str], list[str]]:
    led = R.read_ledger(design)
    am = amend(llm, spec, answered, repairs, list((led.get("ids") or {}).keys()))
    spec2, rev, ref = apply_amendment(spec, led, am)
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
def mark_derived(spec: dict[str, Any], request: str) -> dict[str, Any]:
    """A requirement that rests on a default the agent chose (nobody answered the question it came from) is **derived**: it is labelled so and must be
    validated by the user (``flow.readiness.confirmation_problems``). The link is the brief-210 report's ``origin_of`` (words shared with a resolved question
    whose status is defaulted or waived); a row that states its own ``origin`` or ``derived`` is left as written."""
    from flow import requirements_report as RR
    spec = json.loads(json.dumps(spec))
    for r in R.reqs_of(spec):
        if r.get("origin") or r.get("derived") is not None:
            continue
        og = RR.origin_of(r, spec, request)
        if og["kind"] in ("default", "waiver"):
            r["origin"], r["derived"] = {"kind": "default", "detail": og["detail"]}, True
    return spec


def gate_step(rt: Any, spec: dict[str, Any], level: str, answerer: Answerer | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The stage-0 hook of ``agent run --readiness on`` (after the interview). Returns ``(spec, summary)``; ``summary['requirements_stop']`` is set when the
    gate did not pass. The models are the purposes ``reqreview``, ``reqreader`` and ``reqreader3``."""
    log = rt.run_dir / "claude_code_calls.jsonl"
    llms = LLMs(review=rt.resolver.text("reqreview", label="reqreview", claude_log=log), reader=rt.resolver.text("reqreader", label="reqreader", claude_log=log),
                reader3=rt.resolver.text("reqreader3", label="reqreader3", claude_log=log))
    fr = R.read_frozen(rt.design)
    if fr and fr.get("hash"):                                   # frozen already: unchanged is ready; a change returns to stage 0 and is recorded
        ch = R.changed_since_freeze(rt.design, spec)
        if not ch:
            return spec, {"readiness": {"frozen": True, "rounds": 0, "stop": None, "level": level, "skipped": "the frozen set is unchanged"}}
        R.reopen(rt.design, spec, why="requirements changed after the freeze", ids=ch, who="a later stage")
    request = (rt.design / "spec.md").read_text(errors="replace") if (rt.design / "spec.md").is_file() else ""
    spec = mark_derived(spec, request)
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
