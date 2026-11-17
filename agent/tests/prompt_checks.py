"""Assertions about private prompt text without quoting it (brief 99): a phrase is kept as ``<sha256>:<length>`` and ``has`` slides a
window of that length over the text. ``phrase_id("...")`` makes an id when a test is written; the phrase itself is never committed."""

from __future__ import annotations

import hashlib


def phrase_id(phrase: str) -> str:
    return f"{hashlib.sha256(phrase.encode()).hexdigest()}:{len(phrase)}"


def has(text: str, pid: str) -> bool:
    sha, n = pid.split(":")
    n = int(n)
    return any(hashlib.sha256(text[i:i + n].encode()).hexdigest() == sha for i in range(len(text) - n + 1))
