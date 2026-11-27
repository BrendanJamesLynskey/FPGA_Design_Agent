"""Brief 241: the six data-movement (DMA) intake questions, added the way the protocol intake of brief 190 is."""
from __future__ import annotations

import re

from agent.graph.interview import DMA_QUESTIONS, Question, ensure_dma_questions, request_is_dma

TOPICS = ["direction", "size", "port", "completion", "pressure", "coherency"]
REQ = "Capture a 32-bit stream into a DDR ring buffer and report to software."


def test_each_question_is_well_formed_and_sees_itself() -> None:
    assert [q.topic for q in DMA_QUESTIONS] == TOPICS
    for q in DMA_QUESTIONS:
        assert q.text.endswith("?") and len(q.default) > 40 and len(q.reason) > 60
        Question(id="x", text=q.text, default=q.default, reason=q.reason)
        assert re.search(q.seen, q.text), q.topic


def test_a_dma_request_gets_all_six_and_a_plain_request_none() -> None:
    spec, added = ensure_dma_questions(REQ, {"open_questions": [{"question": "Which board?", "default": "kr260", "reason": "only one"}]})
    assert added == TOPICS and len(spec["open_questions"]) == 7 and spec["open_questions"][0]["question"] == "Which board?"
    for plain in ("Blink an LED at 1 Hz.", "A UART echo with a register map.", "A FIR filter with 16 taps.", ""):
        assert not request_is_dma(plain)
        same, none = ensure_dma_questions(plain, {"open_questions": []})
        assert none == [] and same == {"open_questions": []}


def test_named_cases_match() -> None:
    for r in ("a scatter-gather DMA", "AXI VDMA frame buffer for video", "write ADC samples into DDR", "a descriptor ring in memory", "an AXI CDMA copy"):
        assert request_is_dma(r), r


def test_topics_the_spec_already_asked_are_not_asked_again() -> None:
    spec = {"open_questions": [{"question": "Who owns a buffer, and is a cache flush needed?", "default": "sw", "reason": "r"}]}
    _, added = ensure_dma_questions(REQ, spec)
    assert "direction" not in added and "coherency" not in added and "size" in added
