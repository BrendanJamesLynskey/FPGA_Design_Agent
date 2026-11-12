"""Synthesis messages that break area closure (goal G3, brief 62A): inferred latches and RAM implemented in registers.

Matched on Vivado's own words as well as the message IDs, so a renumbered ID still counts:

- latch: ``[Synth 8-327] inferring latch for variable 'x'``;
- RAM in registers: ``[Synth 8-4767] Trying to implement RAM 'm' in registers. Block RAM or DRAM implementation is not
  possible``, ``[Synth 8-5858] ... will most likely be implemented in registers``, and the like.
"""

from __future__ import annotations

import re
from typing import Any

_LATCH = re.compile(r"\[Synth 8-327\][^\n]*|inferring latch for variable[^\n]*", re.I)
_RAM_REGS = re.compile(r"\[Synth 8-(?:4767|5858)\][^\n]*|implement(?:ed)? RAM [^\n]*in registers[^\n]*", re.I)
_NAME = re.compile(r"'([^']+)'")


def _names(lines: list[str]) -> list[str]:
    out = []
    for l in lines:
        m = _NAME.search(l)
        n = m.group(1) if m else l[:120]
        if n not in out:
            out.append(n)
    return out


def scan(log: str) -> dict[str, Any]:
    latches = _names(_LATCH.findall(log))
    rams = _names(_RAM_REGS.findall(log))
    return {"latches": latches, "ram_in_registers": rams, "clean": not latches and not rams}
