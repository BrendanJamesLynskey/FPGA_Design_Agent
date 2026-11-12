#!/usr/bin/env python3
"""Brief 55: the translation table from the committed result files (scores/, vivado/, blocks/), printed as Markdown.

    python3 results/55_vhdl/make_table.py > results/55_vhdl/table.md
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOARD = ["t1_gray_stepper", "t1_elevator_fsm", "d24_registered_outputs", "t1_sync_fifo_regs", "t1_debounce_bank"]
AREA = {"t1_gray_stepper": "T1", "t1_elevator_fsm": "FSM", "d24_registered_outputs": "FSM drill (registered outputs)",
        "t1_sync_fifo_regs": "memory (FIFO)", "t1_debounce_bank": "T1, asynchronous inputs"}


def load(p: Path):
    return json.loads(p.read_text()) if p.is_file() else None


def bench(tag: str, t: str) -> str:
    s = load(HERE / "scores" / f"{tag}_{t}.json")
    if not s:
        return "not run"
    n = len(s["tests"])
    ok = sum(s["tests"].values())
    if not s.get("built", True) and not n:
        return "FAIL (does not build)"
    return f"{'PASS' if s['pass'] else 'FAIL'} {ok}/{n}"


def viv(t: str, lang: str) -> dict | None:
    return load(HERE / "vivado" / f"{t}__{lang}.json")


def cell(v: dict | None) -> str:
    if not v:
        return "not built"
    u, tm = v["utilization"], v["timing"]
    return (f"{'pass' if v['pass'] else 'FAIL at ' + str(v['first_failed_stage'])}; {u['lut']} LUT / {u['ff']} FF"
            f"{' / ' + str(u['bram_tile']) + ' BRAM' if u.get('bram_tile') else ''}; WNS {tm['wns_ns']:+.3f} ns")


def main() -> None:
    print("| Task | Area | Arm A | Arm B | Vivado 2026.1, SystemVerilog reference | Vivado 2026.1, VHDL |")
    print("|---|---|---|---|---|---|")
    for t in BOARD:
        print(f"| `{t}` | {AREA[t]} | {bench('A', t)} | {bench('B', t)} | {cell(viv(t, 'sv'))} | {cell(viv(t, 'vhdl'))} |")
    a = {r["drill"]: r for r in (load(HERE / "scores" / "A_blocks.json") or [])}
    b = {r["drill"]: r for r in (load(HERE / "scores" / "B_blocks.json") or [])}
    bs = load(HERE / "blocks.json") or {}
    for d, area in (("cdcfx_c10", "CDC (async FIFO), block"), ("cdcfx_c8", "CDC (handshake), block"), ("axil_regs", "AXI4-Lite slave, block")):
        ra = "PASS" if a.get(d, {}).get("pass") else ("FAIL" if d in a else "not run")
        rb = "PASS" if b.get(d, {}).get("pass") else ("FAIL" if d in b else "not run")
        sv = bs.get(f"{d}__sv") or bs.get(f"{d}__v")
        vh = bs.get(f"{d}__vhdl") or bs.get(f"{d}__vhdl_B")
        f = lambda x: "not built" if not x else f"{x.get('lut')} LUT / {x.get('ff')} FF; WNS {x.get('wns_ns')}" + (
            f"; CDC gate {x['cdc_gate']}" if x.get("cdc_gate") else "")
        print(f"| `{d}` | {area} | {ra} | {rb} | {f(sv)} | {f(vh)} |")


if __name__ == "__main__":
    main()
