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
STYLE = {"ex": "stall in EX", "mem": "complete in MEM"}
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
            core = "pinned core" if cfg == "baseline" else (f"with crc32_step `{c['variant']}` (latency "
                                                            f"{c['latency_clocks']}), {STYLE[c.get('style') or 'ex']}")
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
            L.append(f"| `{c['variant']}`, {STYLE[c.get('style') or 'ex']} | {NAMES[ref]} | " + " | ".join(
                f"{base[ref][n]['cycles'] / c['kernels']['cfu'][n]['cycles']:.2f}x" for n in sizes) + " |")
    return "\n".join(L)


def ooc_table(o: dict) -> str:
    L = ["| Core | SoC LUTs | SoC FFs | core LUTs | wrapper (LUTs / FFs) | library unit inside it (LUTs / FFs) | DSP | WNS at "
         f"{o['clock_ns']:g} ns (ns) | Fmax estimate (MHz) |", "|---|---|---|---|---|---|---|---|---|"]
    lf = lambda u: "-" if not u else f"{u['lut']} / {u['ff']}"                       # noqa: E731
    for cfg, c in o["configs"].items():
        if c.get("status") != "ok":
            L.append(f"| {cfg} | {c.get('status')} | | | | | | | |")
            continue
        parts = cfg.split("_")
        name = ("pinned core" if cfg == "baseline" else f"with crc32_step `{parts[1]}`, " +
                ("complete in MEM" if "mem" in parts else "stall in EX") + (", hierarchy kept" if "keep" in parts else ""))
        L.append(f"| {name} | {c['soc']['lut']} | {c['soc']['ff']} | {c['core']['lut']} | {lf(c.get('cfu'))} | "
                 f"{lf(c.get('cfu_unit'))} | {c['soc']['dsp']} | {c['wns_ns']:.3f} | {c['fmax_mhz']:.1f} |")
    return "\n".join(L)


def growth_table(base: dict, cfgs: dict) -> str:
    """Core LUT and FF growth over the pinned core, per style and variant."""
    L = ["| Variant | style | core LUTs (growth) | core FFs (growth) | Fmax estimate (MHz) |", "|---|---|---|---|---|"]
    for cfg, c in cfgs.items():
        parts = cfg.split("_")
        L.append(f"| `{parts[1]}` | {'complete in MEM' if 'mem' in parts else 'stall in EX'} | {c['core']['lut']} "
                 f"(+{c['core']['lut'] - base['core']['lut']}) | {c['core']['ff']} (+{c['core']['ff'] - base['core']['ff']}) | "
                 f"{c['fmax_mhz']:.1f} |")
    return "\n".join(L)


if __name__ == "__main__":
    rec = json.loads((RES / "cfu_crc32.json").read_text())
    print(cycles_table(rec), "\n")
    print(speedups(rec), "\n")
    if (RES / "core_ooc.json").exists():
        print(ooc_table(json.loads((RES / "core_ooc.json").read_text())), "\n")
    if (RES / "core_ooc_styles.json").exists():                    # brief 64A2: both styles, baseline from 64A
        st = json.loads((RES / "core_ooc_styles.json").read_text())
        base = json.loads((RES / "core_ooc.json").read_text())["configs"]["baseline"]
        print(ooc_table({**st, "configs": {"baseline": base, **st["configs"]}}), "\n")
        print(growth_table(base, st["configs"]), "\n")
    if "stale_btb" in rec:
        print("| Configuration | stale-prediction program |\n|---|---|")
        for k, v in rec["stale_btb"]["results"].items():
            print(f"| {k} | {' '.join(v.split()[:2])} |")
