"""The "grill me" spec interview (owner feature, brief 05b).

The clarify stage asks **one question at a time**, each with a proposed default and the reason for it, until
``spec.yaml`` has no unresolved open question. Who answers:

- a human (``--interview on``, interactive): through a LangGraph interrupt; or
- the **spec oracle** (non-interactive runs): it holds a hidden full spec and answers only from it, saying
  ``not specified`` otherwise, in which case the proposed default is taken and marked ``defaulted``;
- nobody (``--interview off``): every question is defaulted.

Every question is recorded (asked / answered / defaulted, by whom), and the record goes into the build note and
``results/f2/``. The asker is the Clarifier sub-agent; this module holds only the bookkeeping and the oracle, so the
rules are tested without a model.
"""

from __future__ import annotations

from agent.core import prompts as _prompts

from agent.core.prompts import load as _p

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
    status: str = "open"                # open | answered | defaulted | waived | unresolved (brief 210: the last two only at standard and strict)
    by: str | None = None               # human | oracle | default
    evidence: str | None = None         # the oracle's quoted line from the hidden spec
    fact: str | None = None             # brief 174: the board_facts.yaml key that answered it (by == "package")
    risk: str = "medium"                # brief 210: low | medium | high (agent.graph.requirements.classify)
    risk_rule: str = ""                 # the rule (or "clarifier") that set the class
    risk_reason: str = ""
    waiver: dict[str, Any] | None = None    # brief 210: the recorded user decision that let a default stand (who, when, why)
    clarifier_risk: str | None = None   # brief 210: the class the Clarifier set on the open question, if any


class Answerer(Protocol):
    name: str

    def answer(self, q: Question) -> tuple[str, str | None]: ...   # (answer or NOT_SPECIFIED, quoted evidence)


@dataclass
class Interview:
    questions: list[Question] = field(default_factory=list)
    max_questions: int = 12
    facts: list[dict[str, Any]] = field(default_factory=list)   # brief 174: board_facts.yaml rows of a design package
    level: str = "loose"                                         # brief 210: loose | standard | strict (agent.graph.requirements)
    waivers: list[Any] = field(default_factory=list)             # brief 210: agent.graph.requirements.Waiver rows

    def lookup(self, q: Question) -> dict[str, Any] | None:
        """A sourced fact of the design package that answers the question, or None (then the question is asked as before)."""
        from agent.graph.package_facts import fact_for
        return fact_for(q.text, self.facts) if self.facts else None

    def ask(self, q: Question, who: Answerer | None) -> Question:
        """Ask one question. ``who=None`` (interview off) takes the default."""
        if not (q.text.strip() and q.default.strip() and q.reason.strip()):
            raise ValueError("a question needs text, a proposed default and the reason for it")
        from agent.graph import requirements as R
        q.risk, q.risk_rule, q.risk_reason = (k := R.classify(q.text, q.default, q.reason, q.clarifier_risk)).cls, k.rule, k.why
        known = self.lookup(q)
        if known is not None:             # brief 174: a fact with a cited source is not asked again; it does not count against the limit
            from agent.graph.package_facts import answer_text, evidence_text
            q.answer, q.status, q.by, q.fact, q.evidence = answer_text(known), "answered", "package", known["key"], evidence_text(known)
            self.questions.append(q)
            return q
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
        R.apply_policy(q, self.level, self.waivers)     # brief 210: at standard and strict a default may not stand for a question that must be resolved
        self.questions.append(q)
        return q

    def unresolved(self) -> list[Question]:
        """Brief 210: the questions the level does not let a default settle, and no waiver covers."""
        return [q for q in self.questions if q.status == "unresolved"]

    def summary(self) -> dict[str, Any]:
        return {"asked": len(self.questions),
                "answered": sum(q.status == "answered" for q in self.questions),
                "defaulted": sum(q.status == "defaulted" for q in self.questions),
                "waived": sum(q.status == "waived" for q in self.questions),
                "unresolved": sum(q.status == "unresolved" for q in self.questions),
                "level": self.level,
                "questions": [asdict(q) for q in self.questions]}

    def resolve_into(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Write the answers into spec.yaml: each question goes to ``resolved_questions`` with its answer and
        who gave it; ``open_questions`` keeps only questions never asked."""
        asked = {q.text for q in self.questions if q.status != "unresolved"}     # an unresolved question stays open in spec.yaml
        spec = dict(spec)
        spec["open_questions"] = [o for o in spec.get("open_questions") or [] if o.get("question") not in asked]
        spec["resolved_questions"] = [*(spec.get("resolved_questions") or []),
                                      *({"question": q.text, "answer": q.answer, "status": q.status, "by": q.by,
                                         "default_reason": q.reason, "risk": q.risk,
                                         **({"waiver": q.waiver} if q.waiver else {})}
                                        for q in self.questions if q.status != "unresolved")]
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
            "defaulted": sum(q.get("status") == "defaulted" for q in qs), "waived": sum(q.get("status") == "waived" for q in qs),
            "unresolved": sum(q.get("status") == "unresolved" for q in qs), "level": new.get("level") or (prev or {}).get("level"), "questions": qs,
            **{k: new[k] for k in ("level_source", "waiver_problems", "requirements_stop") if k in new}}


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
    return "\n".join([_p("graph/interview/render_register_map_1"), *lines, *extra])


REG_TOPIC = re.compile(r"(?is)\b(?:registers?|regs?)\b.{0,80}\b(?:map|offsets?|address(?:es|ing)?|layout)\b"
                       r"|\b(?:offsets?|address(?:es|ing)?)\b.{0,80}\bregisters?\b|\bregister\s+map\b")
REQUEST_REGS = re.compile(r"(?i)\b(?:registers?|regs?|shell|usb[- ]?uart|uart|read(?:ing)?[ -]?back|host\s+(?:interface|bus|port)"
                          r"|command\s+set|axi\w*|apb|wishbone|bus|address(?:es)?)\b")      # 07a2 fix 7: any host-visible interface
REQUEST_OFFSETS = re.compile(r"(?i)\b(?:offsets?)\b|\|\s*(?:0x)?[0-9a-f]+\s*\|")


def is_register_question(text: str) -> bool:
    """07a2 fix 1: a question about register addressing, offsets or the register map."""
    return bool(REG_TOPIC.search(text or ""))


def request_needs_register_map(request: str) -> bool:
    """07a2 fix 1 + fix 6: the request names registers, the shell or the UART host interface but gives no offsets. Only the
    word "offset" or a table row "| 0x.. |" counts as giving them: a hex constant (an LFSR seed, an I2C
    address) is not a register offset (fix 6: three dev specs with such constants were exempted by the old test)."""
    return bool(REQUEST_REGS.search(request or "")) and not REQUEST_OFFSETS.search(request or "")


def proposed_register_default(spec: dict[str, Any]) -> str:
    """The Clarifier's own register map as the default of the question: "NAME: offset 0xNN, ACC, reset R" lines
    (the form ``answer_register_rows`` reads), or a plain sentence when the spec has none."""
    regs = spec.get("registers") if isinstance(spec.get("registers"), dict) else {}
    rows = []
    for r in regs.get("map") or []:
        if isinstance(r, dict) and r.get("name") is not None and r.get("offset") is not None:
            off = _offset_int(r["offset"])
            rows.append(f"{r['name']}: offset {('0x%02X' % off) if off is not None else r['offset']}, "
                        f"{str(r.get('access', 'RW')).upper()}, reset {r.get('reset', 0)}")
    return "; ".join(rows) if rows else _p("graph/interview/proposed_register_default_1")


def ensure_register_question(request: str, spec: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """07a2 fix 7 (1): the harness asks for the register map itself. Whenever the request has a host-visible interface (UART
    command set, bus, "register", "address") and does not give the map, the spec gets an open question asking for it, unless
    the Clarifier already asked one (open or resolved). Softmax run 2 and c14 tiny CNN: the model left the question out,
    so the oracle was never asked and the role's own map reached the hidden bench. Returns (spec, added)."""
    if not request_needs_register_map(request):
        return spec, False
    qs = [*(spec.get("open_questions") or []), *(spec.get("resolved_questions") or [])]
    if any(isinstance(q, dict) and is_register_question(str(q.get("question", ""))) for q in qs):
        return spec, False
    spec = dict(spec)
    spec["open_questions"] = [*(spec.get("open_questions") or []), {
        "question": _p("graph/interview/ensure_register_question_1"),
        "default": proposed_register_default(spec),
        "reason": _p("graph/interview/ensure_register_question_2")}]
    return spec, True


# ---- brief 190 (item 10): the new-protocol intake -------------------------------------------------------------------------------------------
# A request for a block that speaks an exchange or messaging protocol (a market-data feed, an order-entry session, a framed binary protocol)
# gets six standing questions the Clarifier may not have asked: how a session is set up, how messages are delimited, how each field is encoded,
# the largest message, how sequence numbers behave and how a gap is recovered. Each carries a default and the reason for it, so an interview
# that is off or an oracle that does not know still produces a documented choice. The list is ours, written for this agent; the idea of asking
# for these six things first, and building the golden model and byte map before any RTL, is from Edwards 2026, ch 7. The question text is
# in this public file, not in the pinned private prompts (the register-map question is a private prompt); it names no protocol by brand.
REQUEST_PROTOCOL = re.compile(
    r"(?i:\b(?:wire[- ]format|message[- ](?:format|feed|types?|set)|binary[- ](?:feed|protocol|messages?)|market[- ]data|feed[- ]handler|"
    r"order[- ]entry|(?:stock|trading|exchange)[- ](?:feed|protocol|messages?|venue)|datagrams?|MoldUDP\w*|SoupBinTCP|sequence[- ]numbers?)\b)"
    r"|\b(?:ITCH|OUCH|FIX|SBE)\b")           # the acronyms are matched in capitals only: the word "fix" is not a protocol
# a bare "protocol" or "framing" is not enough: a request for an SPI or UART block would get questions that do not apply


@dataclass(frozen=True)
class ProtocolQuestion:
    topic: str            # session | delimiting | encodings | largest | sequencing | gaps
    seen: str             # regex: an existing question on this topic means it is not asked again
    text: str
    default: str
    reason: str


PROTOCOL_QUESTIONS: tuple[ProtocolQuestion, ...] = (
    ProtocolQuestion(
        "session", r"(?i)\b(?:sessions?|log(?:in|on|out)|heartbeats?|keep-?alive|reconnect)",
        "How is a session set up, kept alive and ended: is there a login, an identity, heartbeats, a logout, and what happens on a reconnect?",
        "One session for the whole run, already established before the first message; no login or logout message is modelled; heartbeats are "
        "accepted and ignored; a reconnect is a reset of the block.",
        "The smallest model that can be checked end to end. A session state machine is built only when the spec states one, because every state "
        "added is a path the golden model and the testbench must also cover."),
    ProtocolQuestion(
        "delimiting", r"(?i)\b(?:delimit\w*|length[- ]prefix\w*|message length|terminator|packet boundar\w*|span\w* (?:two )?packets?)",
        "How is one message separated from the next: a length prefix, a fixed size per message type, a terminator or a packet boundary? May "
        "several messages share a packet, and may one message span two packets?",
        "Each message starts with a length field that gives the bytes after it; several messages may share a packet; no message spans two packets.",
        "Delimiting decides where every later field is found. Messages that straddle the datapath word, or share a packet, are where decoders go "
        "wrong, so the choice is fixed in writing before the byte map is."),
    ProtocolQuestion(
        "encodings", r"(?i)\b(?:endian\w*|byte[- ]order|encod\w+|field widths?|fixed[- ]point|space[- ]padded|signedness)",
        "For every field: its width, byte order, signedness and encoding (binary integer, fixed-point with a stated scale, text padded with spaces "
        "on the left or right, or a flag bit)?",
        "Binary fields are big-endian and unsigned; prices are integers with the decimal scale the spec states; text is left-justified and padded "
        "with spaces; every field is listed in a byte map (name, offset, length, encoding) before any RTL is written.",
        "Network byte order is the usual choice for these protocols, but it has to be confirmed field by field: a wrong order or scale shows up "
        "only as plausible-looking wrong values. The byte map is the one table the golden model, the decoder and the test stimulus all read."),
    ProtocolQuestion(
        "largest", r"(?i)\b(?:largest|maximum|max\.?) (?:message|packet|frame|payload)|\bMTU\b",
        "What is the largest message in bytes, and the largest packet or frame the block must accept?",
        "The largest message in the spec's own message table; if the spec gives none, a packet of at most 1,500 bytes of payload and a message "
        "of at most 255 bytes.",
        "It sets the buffer depth, the datapath width and the number of clocks a message can take, so it is a design input and not a detail "
        "found during test."),
    ProtocolQuestion(
        "sequencing", r"(?i)\bsequenc\w*|\bnumbered\b",
        "How are messages numbered: per message or per packet, starting at what value, wrapping or not, and shared across sessions or not?",
        "The packet header carries the sequence number of its first message; the next packet's number is that value plus the message count; "
        "numbering starts at 1 and does not wrap during a run; one counter per session.",
        "Gap and duplicate detection are arithmetic on these numbers, so the counting rule has to be exact. A per-packet and a per-message "
        "convention differ by the message count and look alike on a short test."),
    ProtocolQuestion(
        "gaps", r"(?i)\b(?:gaps?|retransmi\w+|re-?request\w*|duplicates?|overlap\w*|recover\w*)",
        "What must the block do on a gap, a duplicate or an overlap: drop, request a retransmission, or continue and flag it?",
        "Drop duplicates and the repeated part of an overlap and count them; on a gap stop applying messages, raise a flag and count it until "
        "software re-synchronises; no retransmission request is made in hardware.",
        "A silently applied gap makes downstream state wrong with no sign of it. Stopping and flagging is safe and observable, and the counters "
        "make each case testable."),
)


# ---- brief 241: the data-movement (DMA) intake -----------------------------------------------------------------------------------------------
# A request that moves blocks of data between memory and a stream (a DMA, a scatter-gather ring, a capture into DDR, a frame buffer) gets six
# standing questions the Clarifier may not have asked. Each has a default and the reason for it, so an interview that is off or an oracle that does
# not know still records a documented choice. The list is ours; the background is the KB skills `dma-engine-selection` and
# `dma-coherency-and-driver-contract` and AMD's AXI DMA (PG021), AXI CDMA (PG034) and the Zynq TRMs (UG585, UG1085).
REQUEST_DMA = re.compile(
    r"(?i:\bDMA\b|scatter[- ]gather|descriptor[s]? ring|ring buffer|frame[- ]?buffers?|burst(?:s)? (?:to|from) (?:DDR|DRAM|memory)|"
    r"(?:capture|stream|write|read)\w* (?:\w+ ){0,4}(?:into|to|from) (?:the )?(?:DDR|DRAM|PS memory|system memory)|\bAXI (?:CDMA|VDMA|MCDMA|DMA)\b)")


@dataclass(frozen=True)
class DmaQuestion:
    topic: str            # direction | size | port | completion | pressure | coherency
    seen: str             # regex: an existing question on this topic means it is not asked again
    text: str
    default: str
    reason: str


DMA_QUESTIONS: tuple[DmaQuestion, ...] = (
    DmaQuestion(
        "direction", r"(?i)\b(?:memory to stream|stream to memory|MM2S|S2MM|direction|who owns|buffer ownership)",
        "Which way does the data move (memory to stream, stream to memory, or memory to memory), and who owns a buffer at each moment: when may software "
        "write it, when may the hardware, and what tells each side the hand-over has happened?",
        "One direction per engine. Software owns a buffer until it publishes the descriptor (the head index), the hardware owns it until the descriptor's "
        "status word shows DONE and the tail index has passed it, and software does not touch it in between.",
        "A buffer written by both sides at once, or read before the hand-over, is the commonest DMA bug and nothing in the protocol checks it, so the contract is "
        "fixed in writing before any RTL."),
    DmaQuestion(
        "size", r"(?i)\b(?:transfer size|packet length|frame size|fixed (?:size|length)|unknown length|bytes per (?:transfer|frame|packet)|tlast)",
        "How large is one transfer, is it fixed or of unknown length (does the stream carry tlast to end it), and how often does one happen?",
        "A fixed length known to software before the transfer, a whole number of memory-bus beats, one transfer at least every few thousand clocks; the stream's "
        "tlast is not used to end a buffer.",
        "Size and rate decide whether a descriptor ring is worth its overhead, whether a plain register-driven engine is enough, and whether the engine must "
        "end a buffer on tlast (which needs a received-length report)."),
    DmaQuestion(
        "port", r"(?i)\b(?:HP[0-3]|HPC|ACP|S_AXI_HP|memory port|PS port|DDR controller|MIG|data width|bandwidth|MB/s|GB/s)",
        "Which memory does it reach (PS DDR through which PS port, a MIG-driven DDR or on-chip RAM), and what sustained bandwidth and worst-case latency "
        "must it meet?",
        "PS DDR through a high-performance (HP) port at the memory bus's full width, with the bandwidth the stream needs plus 25 percent; no latency bound "
        "beyond finishing before the next transfer starts.",
        "The port fixes the data width, the burst limit (16 beats on a Zynq-7000 PS port, 256 on UltraScale+), whether the caches are snooped and the "
        "ceiling the engine can reach; a bandwidth figure with no port is not a requirement."),
    DmaQuestion(
        "completion", r"(?i)\b(?:interrupt|coalesc\w*|polling|poll\b|doorbell|completion)",
        "How does software learn a transfer has finished: an interrupt per transfer, a coalesced interrupt, or polling a status word, and what is the longest "
        "it may wait?",
        "One interrupt per drained ring, or every N completions, with the status word in each descriptor as the source of truth; software may also poll "
        "the tail index.",
        "An interrupt per small transfer can cost the processor more than the copy, while a coalesced one adds latency; the choice sets the interrupt "
        "threshold and whether the engine needs an idle-flush rule."),
    DmaQuestion(
        "pressure", r"(?i)\b(?:back[- ]?pressure|overrun|underrun|stall|drop\w*|lossless|FIFO depth|sink (?:is )?not ready|source (?:is )?not ready)",
        "What happens when the other side stalls: may the stream source be held off (tready low) without losing data, or does it arrive at a fixed rate that "
        "cannot wait, and what must happen if memory is slow or answers an error?",
        "The stream is held off with tready (no data is lost); a memory error is recorded in the descriptor's status word and the engine goes on, "
        "while a failed descriptor fetch halts it until software clears the error.",
        "A source that cannot wait (an ADC, a video input) needs a buffer deep enough to cover the worst memory stall and an overrun flag; one that can wait "
        "needs only the handshake, and the two designs differ."),
    DmaQuestion(
        "coherency", r"(?i)\b(?:cache|coheren\w*|flush|invalidate|clean\b|snoop\w*|software cache)",
        "If the buffers are in PS memory, who keeps the processors' caches consistent with what the PL reads and writes: software cleans and invalidates "
        "around each transfer, a coherent port does it, or the buffers are uncached?",
        "Software cleans (flushes) a buffer before the PL reads it and invalidates it after the PL writes it, on a non-coherent HP port; the contract is "
        "written in spec.yaml as dma.cache_contract.",
        "Without a stated contract the PL reads stale data or the processor reads stale cache lines, with no error anywhere; the `dma_coherency` check "
        "flags a non-coherent port with no contract."),
)


def request_is_dma(request: str) -> bool:
    """The request moves blocks of data between memory and a stream (a DMA, a ring of descriptors, a capture into DDR, a frame buffer)."""
    return bool(REQUEST_DMA.search(request or ""))


def ensure_dma_questions(request: str, spec: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Brief 241: for a data-movement request, add the six DMA intake questions the spec does not already ask (open or resolved), each with its default and
    reason, to ``open_questions``. Returns (spec, topics added). Any other request, or a spec that has asked all six, is returned unchanged. The Interview's
    question limit (12) still applies: later questions are defaulted by the limit and the record says so."""
    if not request_is_dma(request):
        return spec, []
    asked = " \n ".join(str(q.get("question", "")) for q in [*(spec.get("open_questions") or []), *(spec.get("resolved_questions") or [])]
                        if isinstance(q, dict))
    add = [q for q in DMA_QUESTIONS if not re.search(q.seen, asked)]
    if not add:
        return spec, []
    spec = dict(spec)
    spec["open_questions"] = [*(spec.get("open_questions") or []),
                              *({"question": q.text, "default": q.default, "reason": q.reason} for q in add)]
    return spec, [q.topic for q in add]


RESET_MODEL_SEEN = r"(?i)\breset model\b|\breprogram\w*|\breconfigur\w*"
RESET_MODEL_QUESTION = ("This design has no reset input. Is every reset a reconfiguration of the FPGA (the device is reprogrammed, so every register "
                        "starts from its initial value), or does something restart the running design (then it needs a reset input)?")
RESET_MODEL_DEFAULT = ("Every reset is a reconfiguration of the FPGA (reset model: reprogram): registers get initial values, control state "
                       "included, and the design has no reset input. Record it in spec.yaml as reset: {model: reprogram}; a design that restarts while it runs "
                       "is reset: {model: reset} with a reset port.")
RESET_MODEL_REASON = ("With no reset input, a register can start only from its initial value, which the FPGA loads at configuration (owner, "
                      "2026-11-26: particularly useful for designs whose every reset reprograms the device). A design that must restart while "
                      "running needs a reset input and resets its control state; the two models are checked by different rules (STD-INIT-02).")


def has_reset_input(spec: dict[str, Any]) -> bool:
    """The spec names a reset port. ``reset: none`` / ``reset: {port: none}`` / no port at all means no reset input."""
    r = spec.get("reset")
    if isinstance(r, dict):
        port = r.get("port")
        return bool(port) and str(port).strip().lower() not in ("none", "n/a", "no", "-", "null")
    return bool(r) and str(r).strip().lower() not in ("none", "n/a", "no", "-", "null")


def ensure_reset_model_question(spec: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Brief 231 (owner, 2026-11-26): a spec with no reset input gets the reset-model question (reset or reprogram), with its default and
    reason, unless the spec already states the model (``reset.model``) or asked it. Returns (spec, whether it was added)."""
    if has_reset_input(spec) or (isinstance(spec.get("reset"), dict) and spec["reset"].get("model")):
        return spec, False
    asked = " \n ".join(str(q.get("question", "")) for q in [*(spec.get("open_questions") or []), *(spec.get("resolved_questions") or [])]
                        if isinstance(q, dict))
    if re.search(RESET_MODEL_SEEN, asked):
        return spec, False
    spec = dict(spec)
    spec["open_questions"] = [*(spec.get("open_questions") or []),
                              {"question": RESET_MODEL_QUESTION, "default": RESET_MODEL_DEFAULT, "reason": RESET_MODEL_REASON}]
    return spec, True


REQUEST_ASYNC_RESET = re.compile(r"(?i)\basync(?:hronous)?(?:ly)?[\s-]*(?:(?:active[\s-]*(?:low|high)|negative|positive)[\s-]*)?reset\b|\breset\b[^.\n]{0,30}\basynchronous|\bnegedge\s+rst|\bposedge\s+rst|\barst\w*")
ASYNC_RESET_SEEN = r"(?i)\basync(hronous)?\b.{0,40}\breset\b|\breset\b.{0,40}\basync(hronous)?\b"
ASYNC_RESET_CONFIRM = re.compile(r"(?is)\bconfirm(?:ed|s)?\b.{0,60}?\basync(?:hronous)?\b.{0,25}?\breset\b")
ASYNC_RESET_QUESTION = ("The request asks for an asynchronous reset on the design's own registers. We do not do that by default: AMD recommends synchronous resets "
                        "(UG949), an asynchronous reset costs timing closure (a recovery/removal check on every register and a reset tree that must be timed), and it "
                        "overrides our standard (gate STD-RST-01). A reset that arrives asynchronously from the board (a button, a PS reset, an external chip) is "
                        "fine: we synchronise it at the boundary and every register inside uses a synchronous reset. Do you want asynchronous resets on internal "
                        "registers anyway? Only an emphatic answer counts: write 'CONFIRM ASYNC RESET: <register names> - <why>'.")
ASYNC_RESET_DEFAULT = ("No. Every register inside uses a synchronous reset; a reset input that is asynchronous to the clock is taken through a reset "
                       "synchroniser at the top boundary (spec.yaml reset.asynchronous_input: true).")
ASYNC_RESET_REASON = ("House rule, owner 2026-11-27: a wording in the request alone is not accepted. The confirmation is recorded verbatim in spec.yaml "
                      "(reset.async_waivers) as the waiver of STD-RST-01 for the named registers.")


def ensure_async_reset_question(request: str, spec: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Brief 246 (house rule 2026-11-27): a request (or spec) that wants an asynchronous reset on internal registers gets ONE plain question with the
    cost stated and the synchronous default, unless the spec already asked it or records a waiver. Returns (spec, whether it was added)."""
    text = (request or "") + " \n " + " ".join(str(v) for v in (spec.get("summary"), spec.get("reset")) if v)
    if not REQUEST_ASYNC_RESET.search(text):
        return spec, False
    asked = " \n ".join(str(q.get("question", "")) for q in [*(spec.get("open_questions") or []), *(spec.get("resolved_questions") or [])]
                        if isinstance(q, dict))
    if re.search(ASYNC_RESET_SEEN, asked) or (isinstance(spec.get("reset"), dict) and spec["reset"].get("async_waivers")):
        return spec, False
    spec = dict(spec)
    spec["open_questions"] = [*(spec.get("open_questions") or []),
                              {"question": ASYNC_RESET_QUESTION, "default": ASYNC_RESET_DEFAULT, "reason": ASYNC_RESET_REASON}]
    return spec, True


def apply_async_reset_answer(spec: dict[str, Any]) -> dict[str, Any]:
    """Record an emphatic confirmation as the STD-RST-01 waiver: a resolved async-reset question whose answer reads 'CONFIRM ASYNC RESET: regs - why'
    (given by a person, never defaulted) becomes ``reset.async_waivers: [{registers, confirmation, by, rule}]``, the answer kept verbatim. Any other
    answer (including the default) records nothing, so the synchronous rule stands."""
    out = [w for w in ((spec.get("reset") or {}).get("async_waivers") or []) if isinstance(w, dict)] if isinstance(spec.get("reset"), dict) else []
    for q in spec.get("resolved_questions") or []:
        if not isinstance(q, dict) or not re.search(ASYNC_RESET_SEEN, str(q.get("question", ""))):
            continue
        ans = str(q.get("answer") or "")
        if q.get("status") != "answered" or q.get("by") in ("default", "oracle") or not ASYNC_RESET_CONFIRM.search(ans):
            continue
        tail = re.split(r"(?i)confirm(?:ed|s)?[^:]*:", ans, maxsplit=1)
        names = re.split(r"\s+-+\s+|\s+\u2014\s+|\n", tail[1].strip(), maxsplit=1)[0] if len(tail) > 1 else ""
        regs = [r for r in re.split(r"[,\s]+", names) if re.fullmatch(r"[A-Za-z_]\w*(\[[^\]]*\])?", r)]
        if regs and not any(w.get("confirmation") == ans for w in out):
            out.append({"rule": "STD-RST-01", "registers": regs, "confirmation": ans, "by": q.get("by") or "human"})
    if not out:
        return spec
    spec = dict(spec)
    rst = dict(spec["reset"]) if isinstance(spec.get("reset"), dict) else ({"port": str(spec["reset"])} if spec.get("reset") else {})
    rst["async_waivers"] = out
    spec["reset"] = rst
    return spec


CLOCK_RELATION_SEEN = r"(?i)\b(asynchronous|related|exclusive|same (MMCM|PLL|source)|clock relation|clock groups?)\b"
CLOCK_RELATION_REASON = ("The flow writes set_clock_groups from the declared relation of each clock pair (brief 242): asynchronous, related (outputs of one MMCM, "
                         "timed together) or exclusive (inputs of a clock mux). Without it Vivado times unrelated clocks against each other and the methodology "
                         "gate (TIMING-6/7) fails; a wrong answer would hide a real crossing, so the flow writes a group only where every crossing goes through "
                         "a recognised synchroniser.")


def spec_clock_names(spec: dict[str, Any]) -> list[str]:
    return [str(c["name"]) for c in spec.get("clocks") or [] if isinstance(c, dict) and c.get("name")]


def ensure_clock_relation_question(spec: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Brief 242: a spec with two or more clocks and no stated relation (``clock_relations``, or a question that asks it) gets the clock-relation
    question, with the safe default (asynchronous), unless the spec already states the relations. Returns (spec, whether it was added)."""
    names = spec_clock_names(spec)
    if len(names) < 2 or spec.get("clock_relations"):
        return spec, False
    asked = " \n ".join(str(q.get("question", "")) for q in [*(spec.get("open_questions") or []), *(spec.get("resolved_questions") or [])]
                        if isinstance(q, dict))
    if re.search(CLOCK_RELATION_SEEN, asked) or any(isinstance(c, dict) and c.get("relation") for c in spec.get("clocks") or []):
        return spec, False
    spec = dict(spec)
    spec["open_questions"] = [*(spec.get("open_questions") or []),
                              {"question": "How do the clocks of this design relate to each other: " + ", ".join(names) + "? For each pair say asynchronous "
                                           "(no common source), related (outputs of one MMCM or PLL), or exclusive (the inputs of a clock mux).",
                               "default": "Every pair is asynchronous unless both clocks come from one MMCM or PLL (then related) or are the inputs of a clock mux (then exclusive).",
                               "reason": CLOCK_RELATION_REASON}]
    return spec, True


def request_is_protocol(request: str) -> bool:
    """The request names an exchange or messaging protocol (market data, order entry, a framed binary protocol, sequence numbers)."""
    return bool(REQUEST_PROTOCOL.search(request or ""))


def ensure_protocol_questions(request: str, spec: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Brief 190: for a protocol request, add the six intake questions the spec does not already ask (open or resolved), each with its default
    and reason, to ``open_questions``. Returns (spec, topics added). A request with no protocol wording, or a spec that has asked all six, is
    returned unchanged. The Interview's question limit (12) still applies: later questions are defaulted by the limit and the record says so."""
    if not request_is_protocol(request):
        return spec, []
    asked = " \n ".join(str(q.get("question", "")) for q in [*(spec.get("open_questions") or []), *(spec.get("resolved_questions") or [])]
                        if isinstance(q, dict))
    add = [q for q in PROTOCOL_QUESTIONS if not re.search(q.seen, asked)]
    if not add:
        return spec, []
    spec = dict(spec)
    spec["open_questions"] = [*(spec.get("open_questions") or []),
                              *({"question": q.text, "default": q.default, "reason": q.reason} for q in add)]
    return spec, [q.topic for q in add]


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
        return [_p("graph/interview/register_map_errors_1")]
    regs = spec.get("registers") or {}
    have = {_offset_int(r.get("offset")) for r in (regs.get("map") or []) if isinstance(r, dict)} if isinstance(regs, dict) else set()
    errs = []
    for q in mine:
        if q.get("status") == "answered":
            want = {r["offset"] for r in answer_register_rows(str(q.get("answer", "")))}
            miss = sorted(w for w in want if w not in have)
            if miss:
                errs.append(_p("graph/interview/register_map_errors_2")
                            + ", ".join(f"0x{m:02X}" for m in miss) + _p("graph/interview/register_map_errors_3"))
            extra = sorted(h for h in have if h is not None and want and h not in want) if q.get("by") == "oracle" else []
            if extra:                              # 07a2 fix 6: the oracle's map is the whole map; invented registers are wrong
                errs.append(_p("graph/interview/register_map_errors_4")
                            + ", ".join(f"0x{m:02X}" for m in extra) + _p("graph/interview/register_map_errors_5"))
    return errs


REG_LINE = re.compile(r"^\s*([\w.]+): offset (0x[0-9a-fA-F]+|\d+)(?:\s*-\s*(0x[0-9a-fA-F]+|\d+))?, (\w+), reset (\S+?): (.*)$")
NAME_RANGE = re.compile(r"^(\D*?)(\d+)\.\.(\D*?)(\d+)$")


def answer_register_rows(answer: str) -> list[dict[str, Any]]:
    """07a2 fix 6: the registers of an answered register-map question, one dict per register. A line reads "NAME: offset
    0xNN, ACC, reset R: bits"; a range line ("X0..X3: offset 0x00-0x03, ...", "OUT0..OUT3: offset 0x20-0x23") is expanded
    to one register per offset (X0, X1, X2, X3). Softmax run 2: the oracle's range lines were not parsed, so the role's own
    one-register-per-score map stayed and the hidden bench found different registers."""
    rows: list[dict[str, Any]] = []
    for line in str(answer).splitlines():
        m = REG_LINE.match(line)
        if not m:
            continue
        name, lo, hi, acc, reset, bits = m.groups()
        first = _offset_int(lo)
        last = _offset_int(hi) if hi else first
        if first is None or last is None or last < first:
            continue
        n = last - first + 1
        nm = NAME_RANGE.match(name)
        if nm and int(nm.group(4)) - int(nm.group(2)) + 1 == n:
            names = [f"{nm.group(1)}{int(nm.group(2)) + i}" for i in range(n)]
        else:
            names = [name] if n == 1 else [f"{name}{i}" for i in range(n)]
        for i, nme in enumerate(names):
            rows.append({"offset": first + i, "name": nme, "access": acc,
                         "reset": _offset_int(reset) if _offset_int(reset) is not None else reset, "bits": bits})
    return rows


def apply_register_answer(spec: dict[str, Any]) -> dict[str, Any]:
    """07a2 fix 5 C + fix 6: a register map supplied in an answer overrides what the Clarifier proposed. Every line of the
    answered register-map question that reads "NAME: offset 0xNN, ACC, reset R: bits" (ranges expanded, see
    ``answer_register_rows``) replaces the name, access, reset and bits of the spec's entry at that offset; an offset the
    spec lacks is added. When the oracle gave the answer (the whole map of the hidden spec) the role's registers at other
    offsets are dropped: they were guesses (softmax run 2 kept an invented ID/CTRL/SCORE1..7 map beside the real one).
    Free-form human answers match no line and change nothing."""
    qs = [q for q in (spec.get("resolved_questions") or []) if isinstance(q, dict) and q.get("status") == "answered"
          and is_register_question(str(q.get("question", "")))]
    rows = [(r, q.get("by") == "oracle") for q in qs for r in answer_register_rows(str(q.get("answer", "")))]
    if not rows:
        return spec
    spec = dict(spec)
    regs = dict(spec.get("registers") or {})
    entries = [dict(e) if isinstance(e, dict) else e for e in regs.get("map") or []]
    if any(whole for _, whole in rows):
        keep = {r["offset"] for r, whole in rows if whole}
        entries = [e for e in entries if isinstance(e, dict) and _offset_int(e.get("offset")) in keep]
    for r, _ in rows:
        hit = next((e for e in entries if isinstance(e, dict) and _offset_int(e.get("offset")) == r["offset"]), None)
        if hit is None:
            hit = {"offset": r["offset"], "name": r["name"]}
            entries.append(hit)
        hit.update(r)
    regs["map"] = entries
    spec["registers"] = regs
    return spec


#: The oracle answers a register-addressing question with the whole map, one register per line.
def register_map_answer(rendered: str) -> tuple[str, str] | None:
    lines = rendered.splitlines()
    if len(lines) < 2:
        return None
    return "\n".join(lines[1:]), lines[1]


def _norm(t: str) -> str:
    return " ".join(str(t).replace("\u2019", "'").split()).strip(" \"'`-")


def _yaml_strings(text: str) -> str:
    """Every string value of the YAML document, one per line: a single-quoted scalar holds ``two''s`` in the file
    and ``two's`` once parsed, and the oracle's model quotes the parsed form (07a2 fix 5 B, c10_dds_sine)."""
    import yaml
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return ""
    out: list[str] = []

    def walk(x: Any) -> None:
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict):
            for k, v in x.items():
                walk(k)
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)

    walk(doc)
    return "\n".join(out)


class SpecOracle:
    """Answers only from a hidden full spec file. ``llm`` is a callable (system, user) -> dict with keys
    ``answer`` and ``quote``; the quote must appear verbatim in the hidden spec, else the answer is refused and
    counted as ``not specified`` (the oracle cannot invent requirements). The hidden file never enters any
    agent's state: the oracle is outside the graph's sub-agents."""

    name = "oracle"
    SYSTEM = _prompts.Lazy("graph/interview/oracle_system")

    def __init__(self, hidden_spec: Path, llm: Callable[[str, str], dict[str, Any]]):
        self._file = hidden_spec.read_text()
        rendered = render_register_map(self._file)                # 07a2-prep: register-map questions
        self._rendered = rendered
        self._text = self._file + ("\n\n" + rendered + "\n" if rendered else "")
        self._flat = _norm(self._text)
        self._decoded = _norm(_yaml_strings(self._file))     # 07a2 fix 5 B: quotes are checked against parsed values too
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
                                                        and _norm(str(quote)) not in self._flat
                                                        and _norm(str(quote)) not in self._decoded):
            self.log.append({"question": q.text, "refused": "quote not in the hidden spec", "raw": a})
            a, quote = NOT_SPECIFIED, None
        self.log.append({"question": q.text, "answer": a})
        return a, quote
