"""The "grill me" spec interview (owner feature, brief 05b).

The clarify stage asks **one question at a time**, each with a proposed default and the reason for it, until
``spec.yaml`` has no unresolved open question. Who answers:

- a human (``--interview on``, interactive): through a LangGraph interrupt; or
- the **spec oracle** (non-interactive runs): it holds a hidden full spec and answers only from it, saying
  ``not specified`` otherwise, in which case the proposed default is taken and marked ``defaulted``;
- nobody (``--interview off``): every question is defaulted.

Every question is recorded (asked / answered / defaulted, by whom), and the record goes into the build note and
``results/f2/``. The asker is the clarify sub-agent; this module holds only the bookkeeping and the oracle, so the
rules are tested without a model.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

NOT_SPECIFIED = "not specified"


@dataclass
class Question:
    id: str
    text: str
    default: str
    reason: str
    answer: str | None = None
    status: str = "open"                # open | answered | defaulted
    by: str | None = None               # human | oracle | default
    evidence: str | None = None         # the oracle's quoted line from the hidden spec


class Answerer(Protocol):
    name: str

    def answer(self, q: Question) -> tuple[str, str | None]: ...   # (answer or NOT_SPECIFIED, quoted evidence)


@dataclass
class Interview:
    questions: list[Question] = field(default_factory=list)
    max_questions: int = 12

    def ask(self, q: Question, who: Answerer | None) -> Question:
        """Ask one question. ``who=None`` (interview off) takes the default."""
        if not (q.text.strip() and q.default.strip() and q.reason.strip()):
            raise ValueError("a question needs text, a proposed default and the reason for it")
        if len(self.questions) >= self.max_questions:
            # a limit degrades, never crashes the run (a live run died here): the user is not asked, the default is
            # taken, and the record says it was the limit
            q.answer, q.status, q.by = q.default, "defaulted", "limit"
        elif who is None:
            q.answer, q.status, q.by = q.default, "defaulted", "default"
        else:
            a, ev = who.answer(q)
            if a.strip().lower() == NOT_SPECIFIED:
                q.answer, q.status, q.by, q.evidence = q.default, "defaulted", who.name, None
            else:
                q.answer, q.status, q.by, q.evidence = a, "answered", who.name, ev
        self.questions.append(q)
        return q

    def summary(self) -> dict[str, Any]:
        return {"asked": len(self.questions),
                "answered": sum(q.status == "answered" for q in self.questions),
                "defaulted": sum(q.status == "defaulted" for q in self.questions),
                "questions": [asdict(q) for q in self.questions]}

    def resolve_into(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Write the answers into spec.yaml: each question goes to ``resolved_questions`` with its answer and
        who gave it; ``open_questions`` keeps only questions never asked."""
        asked = {q.text for q in self.questions}
        spec = dict(spec)
        spec["open_questions"] = [o for o in spec.get("open_questions") or [] if o.get("question") not in asked]
        spec["resolved_questions"] = [*(spec.get("resolved_questions") or []),
                                      *({"question": q.text, "answer": q.answer, "status": q.status, "by": q.by,
                                         "default_reason": q.reason} for q in self.questions)]
        return spec


def merge_summaries(prev: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
    """07a2 fix 3: the clarify gate can run the interview more than once (the first visit fails on something else, the
    second finds every question already resolved in spec.yaml and asks none). The run summary must count the questions
    of every visit, so the later, empty summary must not replace the earlier one. Questions are kept in order, once
    each (by text)."""
    qs = [*(prev or {}).get("questions", [])]
    for q in new.get("questions", []):
        if q.get("text") not in {x.get("text") for x in qs}:
            qs.append(q)
    return {"asked": len(qs), "answered": sum(q.get("status") == "answered" for q in qs),
            "defaulted": sum(q.get("status") == "defaulted" for q in qs), "questions": qs}


def open_questions(spec: dict[str, Any] | None) -> list[str]:
    return [o.get("question", "") for o in (spec or {}).get("open_questions") or []]


def render_register_map(text: str) -> str:
    """07a2-prep: the hidden spec's ``registers.map`` as plain lines, one per register ("Y: offset 0x08, RO, reset 0: [7:0]
    limited answer"). The YAML flow mappings of the file are hard to quote verbatim, so a question like "which offset is the
    result register?" was answered "not specified" when the quote did not match. The lines are appended to the oracle's text,
    so the oracle can answer register-map questions and quote a line that is really there. "" when there is no map."""
    import yaml
    try:
        spec = yaml.safe_load(text)
    except yaml.YAMLError:
        return ""
    regs = (spec.get("registers") if isinstance(spec, dict) else None) or {}
    rows = [r for r in (regs.get("map") or []) if isinstance(r, dict) and "name" in r and "offset" in r] if isinstance(regs, dict) else []
    if not rows:
        return ""
    def off(v: Any) -> str:
        return f"0x{v:02X}" if isinstance(v, int) else str(v)
    lines = [f"{r['name']}: offset {off(r['offset'])}, {r.get('access', '?')}, reset {r.get('reset', 0)}: {r.get('bits', '')}"
             for r in rows]
    extra = [f"{k}: {v}" for k, v in regs.items() if k not in ("map",) and isinstance(v, (str, int))]
    return "\n".join(["Register map (the same entries as registers.map above, one per line):", *lines, *extra])


REG_TOPIC = re.compile(r"(?is)\b(?:registers?|regs?)\b.{0,80}\b(?:map|offsets?|address(?:es|ing)?|layout)\b"
                       r"|\b(?:offsets?|address(?:es|ing)?)\b.{0,80}\bregisters?\b|\bregister\s+map\b")
REQUEST_REGS = re.compile(r"(?i)\b(?:registers?|test\s+shell|the\s+shell|over\s+the\s+shell|shell\s+registers?)\b")
REQUEST_OFFSETS = re.compile(r"(?i)\b(?:offsets?)\b|\b0x[0-9a-f]+\b|\|\s*(?:0x)?[0-9a-f]+\s*\|")


def is_register_question(text: str) -> bool:
    """07a2 fix 1: a question about register addressing, offsets or the register map."""
    return bool(REG_TOPIC.search(text or ""))


def request_needs_register_map(request: str) -> bool:
    """07a2 fix 1: the request names registers or the test shell but gives no offsets."""
    return bool(REQUEST_REGS.search(request or "")) and not REQUEST_OFFSETS.search(request or "")


def _offset_int(t: str) -> int | None:
    try:
        return int(str(t), 0)
    except ValueError:
        return None


def register_map_errors(request: str, spec: dict[str, Any]) -> list[str]:
    """07a2 fix 1, the clarify gate: a request that names shell registers without offsets needs a question about the
    register map in the spec (open, or resolved by the interview), and, once that question is answered with a map, the
    spec's ``registers.map`` must carry every offset of the answer. Empty list: nothing to fix."""
    if not request_needs_register_map(request):
        return []
    qs = [*(spec.get("open_questions") or []), *(spec.get("resolved_questions") or [])]
    mine = [q for q in qs if isinstance(q, dict) and is_register_question(str(q.get("question", "")))]
    if not mine:
        return ["the request names registers or the test shell but gives no register offsets, and spec.yaml has no question "
                "asking for the register map: add an open_questions entry asking for the offsets, widths, reset values and "
                "access of every register (your proposed map as the default); do not invent the map"]
    regs = spec.get("registers") or {}
    have = {_offset_int(r.get("offset")) for r in (regs.get("map") or []) if isinstance(r, dict)} if isinstance(regs, dict) else set()
    errs = []
    for q in mine:
        if q.get("status") == "answered":
            want = {_offset_int(m) for m in re.findall(r"(?i)\boffset\s+(0x[0-9a-f]+|\d+)", str(q.get("answer", "")))}
            miss = sorted(w for w in want if w is not None and w not in have)
            if miss:
                errs.append("registers.map disagrees with the answered register map: no register at offset "
                            + ", ".join(f"0x{m:02X}" for m in miss) + "; copy the answer's map into registers.map")
    return errs


#: The oracle answers a register-addressing question with the whole map, one register per line.
def register_map_answer(rendered: str) -> tuple[str, str] | None:
    lines = rendered.splitlines()
    if len(lines) < 2:
        return None
    return "\n".join(lines[1:]), lines[1]


def _norm(t: str) -> str:
    return " ".join(str(t).replace("\u2019", "'").split()).strip(" \"'`-")


class SpecOracle:
    """Answers only from a hidden full spec file. ``llm`` is a callable (system, user) -> dict with keys
    ``answer`` and ``quote``; the quote must appear verbatim in the hidden spec, else the answer is refused and
    counted as ``not specified`` (the oracle cannot invent requirements). The hidden file never enters any
    agent's state: the oracle is outside the graph's sub-agents."""

    name = "oracle"
    SYSTEM = ("You stand in for the user of an FPGA design agent. You hold the full specification below and may "
              "answer only from it. Reply as JSON {\"answer\": ..., \"quote\": ...}, where quote is the exact line "
              "of the specification your answer rests on. If the specification does not settle the question, reply "
              "{\"answer\": \"not specified\", \"quote\": null}. Never guess, never add requirements.")

    def __init__(self, hidden_spec: Path, llm: Callable[[str, str], dict[str, Any]]):
        self._file = hidden_spec.read_text()
        rendered = render_register_map(self._file)                # 07a2-prep: register-map questions
        self._rendered = rendered
        self._text = self._file + ("\n\n" + rendered + "\n" if rendered else "")
        self._flat = _norm(self._text)
        self._llm = llm
        self.log: list[dict[str, Any]] = []

    def answer(self, q: Question) -> tuple[str, str | None]:
        if self._rendered and is_register_question(q.text):          # 07a2 fix 1: the whole map, no model call
            ans, quote = register_map_answer(self._rendered)
            self.log.append({"question": q.text, "answer": ans, "by": "register map"})
            return ans, quote
        out = self._llm(self.SYSTEM + "\n\n--- specification ---\n" + self._text,
                        json.dumps({"question": q.text, "proposed_default": q.default}))
        a, quote = str(out.get("answer", NOT_SPECIFIED)), out.get("quote")
        if a.strip().lower() != NOT_SPECIFIED and (not quote or str(quote).strip() not in self._text
                                                        and _norm(str(quote)) not in self._flat):
            self.log.append({"question": q.text, "refused": "quote not in the hidden spec", "raw": a})
            a, quote = NOT_SPECIFIED, None
        self.log.append({"question": q.text, "answer": a})
        return a, quote
