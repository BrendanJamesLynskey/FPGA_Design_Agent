"""cocotb test of the brief 20 drills: every register a multicycle names changes only on one phase of the N-clock enable.

Run by lib/sim_enable_check.py (never by the acceptance bench). A setup-N multicycle on registers loaded by a 1-in-N enable is
true only if each of them changes on clocks that are N apart from each other's changes: so every change of every named
register must fall on the same clock index modulo N. This needs no knowledge of how the enable is built (a register, a
comparator, folded into D). Environment: FDA_MCP_SIGNALS (JSON list of hierarchical signal paths, "u_core.level_q"),
FDA_MCP_N, BENCH_TASK (the task directory; its hidden/mcp_stimulus.py has ``async def stimulus(board)``), FDA_MCP_OUT."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import cocotb
from benchmark.lib.bench import Board
from cocotb.triggers import ReadOnly, RisingEdge


def handle(dut, path: str):
    h = dut
    for part in path.split("."):
        h = getattr(h, part)
    return h


@cocotb.test()
async def test_multicycle_registers_change_on_one_phase(dut):
    sigs = json.loads(os.environ["FDA_MCP_SIGNALS"])
    n = int(os.environ["FDA_MCP_N"])
    hs = {s: handle(dut, s) for s in sigs}
    b = Board(dut, {})
    await b.start()
    phases: dict[str, dict[int, int]] = {s: {} for s in sigs}
    stop = False

    async def watch() -> None:
        prev = {s: str(h.value) for s, h in hs.items()}
        k = 0
        while not stop:
            await RisingEdge(b.clk)
            await ReadOnly()
            k += 1
            for s, h in hs.items():
                v = str(h.value)
                if v != prev[s]:
                    phases[s][k % n] = phases[s].get(k % n, 0) + 1
                prev[s] = v

    mon = cocotb.start_soon(watch())
    spec = importlib.util.spec_from_file_location("mcp_stimulus", Path(os.environ["BENCH_TASK"]) / "hidden" / "mcp_stimulus.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    await mod.stimulus(b)
    stop = True
    await b.cycles(2)
    mon.cancel()
    total: dict[int, int] = {}
    for p in phases.values():
        for r, c in p.items():
            total[r] = total.get(r, 0) + c
    main = max(total, key=total.get) if total else None
    off = {s: sum(c for r, c in p.items() if r != main) for s, p in phases.items()}
    off = {s: c for s, c in off.items() if c}
    Path(os.environ.get("FDA_MCP_OUT", "mcp_enable.json")).write_text(
        json.dumps({"n": n, "phase": main, "changes_by_phase": {s: {str(r): c for r, c in p.items()} for s, p in phases.items()},
                    "off_phase": off}))
    assert total, "no multicycle register changed during the stimulus"
    assert not off, f"registers changed off the enable's phase (mod {n}): {off}"
