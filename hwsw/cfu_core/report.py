#!/usr/bin/env python3
"""Markdown tables from results/64a_hwsw/cfu_crc32.json and core_ooc.json (brief 64A+), for docs/hwsw.md and the
results README. Every number printed comes from those two files.

    python3 hwsw/cfu_core/report.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results" / "64a_hwsw"
NAMES = {"table": "table-driven C (1 KB table)", "bitwise": "bitwise C (no table)",
         "clmul": "carry-less multiply (Zbkc, Zbkb)", "cfu": "custom instruction crc32.w"}


def cycles_table(rec: dict) -> str:
    sizes = [str(n) for n in rec["sizes_bytes"]]
    L = ["| Core | Kernel | " + " | ".join(f"{n} B" for n in sizes) + " | cycles per byte at " + sizes[-1] + " B |",
         "|---|---|" + "---|" * (len(sizes) + 1)]
    for cfg, c in rec["configs"].items():
        for k, by in c["kernels"].items():
            if cfg != "baseline" and k != "cfu":
                continue                                   # the software kernels are the same on every core
            core = "pinned core" if cfg == "baseline" else f"with crc32_step `{c['variant']}` (latency {c['latency_clocks']})"
            L.append(f"| {core} | {NAMES[k]} | " + " | ".join(str(by[n]["cycles"]) for n in sizes) +
                     f" | {by[sizes[-1]]['cycles_per_byte']:.2f} |")
    return "\n".join(L)


def speedups(rec: dict) -> str:
    base = rec["configs"]["baseline"]["kernels"]
    sizes = [str(n) for n in rec["sizes_bytes"]]
    L = ["| Custom instruction | against | " + " | ".join(f"{n} B" for n in sizes) + " |", "|---|---|" + "---|" * len(sizes)]
    for cfg, c in rec["configs"].items():
        if cfg == "baseline":
            continue
        for ref in ("table", "clmul"):
            L.append(f"| `{c['variant']}` | {NAMES[ref]} | " + " | ".join(
                f"{base[ref][n]['cycles'] / c['kernels']['cfu'][n]['cycles']:.2f}x" for n in sizes) + " |")
    return "\n".join(L)


def ooc_table(o: dict) -> str:
    L = ["| Core | SoC LUTs | SoC FFs | core LUTs | the unit (LUTs / FFs) | DSP | WNS at " + f"{o['clock_ns']:g} ns (ns) | Fmax estimate (MHz) |",
         "|---|---|---|---|---|---|---|---|"]
    for cfg, c in o["configs"].items():
        if c.get("status") != "ok":
            L.append(f"| {cfg} | {c.get('status')} | | | | | | |")
            continue
        u = c.get("cfu")
        name = "pinned core" if cfg == "baseline" else f"with crc32_step `{cfg.split('_', 1)[1]}`"
        L.append(f"| {name} | {c['soc']['lut']} | {c['soc']['ff']} | {c['core']['lut']} | "
                 f"{'-' if not u else str(u['lut']) + ' / ' + str(u['ff'])} | {c['soc']['dsp']} | {c['wns_ns']:.3f} | {c['fmax_mhz']:.1f} |")
    return "\n".join(L)


if __name__ == "__main__":
    rec = json.loads((RES / "cfu_crc32.json").read_text())
    print(cycles_table(rec), "\n")
    print(speedups(rec), "\n")
    if (RES / "core_ooc.json").exists():
        print(ooc_table(json.loads((RES / "core_ooc.json").read_text())))
