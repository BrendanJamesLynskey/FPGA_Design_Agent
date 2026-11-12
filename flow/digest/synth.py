"""Synthesis messages that break area closure (goal G3, brief 62A): inferred latches and RAM implemented in registers.

Matched on Vivado's own words as well as the message IDs, so a renumbered ID still counts:

- latch: ``[Synth 8-327] inferring latch for variable 'x'``;
- RAM in registers: ``[Synth 8-4767] Trying to implement RAM 'm' in registers. Block RAM or DRAM implementation is not
  possible``, ``[Synth 8-5858] ... will most likely be implemented in registers``, and the like;
- simulation/synthesis disagreement: ``[Synth 8-6858/6859] multi-driven net`` and ``[Synth 8-13373/13374] Removed
  Unreachable/Macro Instance`` (the closure controller fails G1 on them).
"""

from __future__ import annotations

import re
from typing import Any

_LATCH = re.compile(r"\[Synth 8-327\][^\n]*|inferring latch for variable[^\n]*", re.I)
_RAM_REGS = re.compile(r"\[Synth 8-(?:4767|5858)\][^\n]*|implement(?:ed)? RAM [^\n]*in registers[^\n]*", re.I)
_MULTI = re.compile(r"\[Synth 8-685[89]\][^\n]*|multi-driven net[^\n]*", re.I)
_REMOVED = re.compile(r"\[Synth 8-1337[34]\][^\n]*|Removed (?:Unreachable|Macro) [Ii]nstance[^\n]*")
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
    multi = _MULTI.findall(log)
    removed = sorted({l.strip()[:160] for l in _REMOVED.findall(log)})
    # brief 62A: a multi-driven net or a removed instance means the netlist is not the simulated design (c13_orig_plan,
    # 2026-11-12: two always_ff blocks drove the same registers; Icarus passed, synthesis tied them to GND and removed the core)
    return {"latches": latches, "ram_in_registers": rams, "multi_driven": len(multi), "removed_instances": removed,
            "clean": not latches and not rams and not multi and not removed}
