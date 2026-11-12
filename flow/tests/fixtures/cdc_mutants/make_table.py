#!/usr/bin/env python3
"""The mutant table of brief 16: report_cdc alone against the new CDC gate, for every fixture in rtl/.

    python3 flow/tests/fixtures/cdc_mutants/make_table.py [--seeds 3] [--out results/16_cdc_gate]

report_cdc alone  = the flow's existing gate (post_synth_cdc_no_critical): no Critical row in golden/<f>/cdc_synth.rpt
structure         = flow/cdc_structure.py on golden/<f>/{cdc_paths_synth,cdc_synth}.rpt (Vivado 2025.2 synthesis of the
                    fixture; regenerate with run_all.sh, which needs a heavy slot)
simulation        = the fixture's own cocotb test (tb/cdcfx_tb.py) plain and with synchroniser-delay injection, seeds 1..N
new gate          = structure clean AND the injected simulation passes
A mutant is caught by the gate when the new gate fails; a correct variant must pass. Writes mutant_table.json and .md."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from flow import cdc_structure, gates  # noqa: E402

DESCR = {
    "c1": "toggle, 2-flop ASYNC_REG vector", "c2": "toggle, 3-flop ASYNC_REG vector", "c3": "xpm_cdc_single",
    "c4": "pulse to toggle, scalar ASYNC_REG flops", "c5": "xpm_cdc_pulse", "c6": "hand-built Gray bus + max-delay/bus-skew",
    "c7": "xpm_cdc_gray", "c8": "hand-built 4-phase handshake", "c9": "xpm_cdc_handshake", "c10": "hand-built Gray async FIFO",
    "c11": "xpm_fifo_async", "c12": "reset bridge (async assert, sync release)",
    "m1": "two flops, no ASYNC_REG", "m1b": "no synchroniser (one flop)", "m2": "one bit into two flops, compared",
    "m3": "binary counter bit by bit", "m4": "two toggles XORed before the synchroniser", "m5": "pulse into a level synchroniser",
    "m6a": "Gray bus with no max-delay/bus-skew exception", "m7": "two flags synchronised separately, then compared",
    "m8": "source reset clears a destination register", "m10": "raw reset released asynchronously into clk_b flops",
}


def order(p: Path) -> tuple:
    short = p.stem.replace("cdcfx_", "")
    num = "".join(ch for ch in short if ch.isdigit())
    return (short[0] != "c", int(num), short)


NOT_PORTED = ("Not ported: M6b and M6c (the same RTL as M6a with route-through LUT padding: hardware skew, nothing to see in "
              "RTL or at synthesis beyond M6a's missing exception), M9 and M11 and C13 (one-sided reset of a FIFO or handshake: "
              "they need the rig's asynchronous-reset release injection, which the cycle-level model does not have).")


def sim(name: str, seed: int) -> tuple[bool, float]:
    t0 = time.time()
    p = subprocess.run([sys.executable, str(HERE / "run_fixture.py"), name, str(seed)], capture_output=True, text=True, cwd=ROOT)
    return p.returncode == 0, time.time() - t0


def build(seeds: int, gdir: Path | None = None) -> list[dict]:
    rows = []
    for rtl in sorted(HERE.joinpath("rtl").glob("*.sv"), key=order):
        name = rtl.stem
        short = name.replace("cdcfx_", "")
        g = (gdir or HERE / "golden") / name
        cdc = gates.parse_cdc((g / "cdc_synth.rpt").read_text())
        crit = sum(r["count"] for r in cdc["rules"] if r["severity"] == "Critical")
        st = cdc_structure.evaluate(g / "cdc_paths_synth.rpt", g / "cdc_synth.rpt")
        plain_ok, t_plain = sim(name, 0)
        inj = [sim(name, s) for s in range(1, seeds + 1)]
        inj_ok = all(ok for ok, _ in inj)
        rows.append({
            "fixture": short, "kind": "correct" if short.startswith("c") else "mutant", "what": DESCR.get(short, ""),
            "report_cdc_critical_rows": crit, "report_cdc_alone_flags": crit > 0,
            "report_cdc_rules": sorted({f"{r['rule']}({r['severity']})" for r in cdc["rules"]}),
            "structure_unsafe": sorted({u["rule"] for u in st["unsafe"]}), "structure_flags": not st["pass"],
            "sim_plain_pass": plain_ok, "sim_injected_pass": inj_ok, "sim_flags": plain_ok and not inj_ok,
            "gate_flags": (not st["pass"]) or (plain_ok and not inj_ok),
            "sim_s_per_run": round((t_plain + sum(t for _, t in inj)) / (1 + seeds), 1),
        })
    return rows


def md(rows: list[dict], seeds: int) -> str:
    yn = lambda b: "yes" if b else "no"
    out = [f"| fixture | what | report_cdc alone flags | structure flags | injected sim flags (seeds 1-{seeds}) | new gate flags |",
           "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['fixture'].upper()} | {r['what']} | {yn(r['report_cdc_alone_flags'])} | "
                   f"{yn(r['structure_flags'])}{' (' + ', '.join(r['structure_unsafe']) + ')' if r['structure_unsafe'] else ''} | "
                   f"{yn(r['sim_flags'])}{'' if r['sim_plain_pass'] else ' (plain run fails)'} | {yn(r['gate_flags'])} |")
    return "\n".join(out) + "\n\n" + NOT_PORTED + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--out", default="results/16_cdc_gate")
    ap.add_argument("--golden", default=None, help="report directory (brief 49: the 2026.1 set lives under results/)")
    ap.add_argument("--vivado", default="2025.2")
    a = ap.parse_args()
    rows = build(a.seeds, ROOT / a.golden if a.golden else None)
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "mutant_table.json").write_text(json.dumps({"vivado": a.vivado, "seeds": a.seeds, "rows": rows}, indent=1) + "\n")
    (out / "mutant_table.md").write_text(md(rows, a.seeds))
    print(md(rows, a.seeds))
    bad_c = [r["fixture"] for r in rows if r["kind"] == "correct" and r["gate_flags"]]
    miss = [r["fixture"] for r in rows if r["kind"] == "mutant" and not r["gate_flags"]]
    print("correct variants flagged by the new gate:", bad_c or "none")
    print("mutants the new gate passes:", miss or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
