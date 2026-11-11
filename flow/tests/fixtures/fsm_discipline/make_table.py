#!/usr/bin/env python3
"""Tables of the brief 24 reference-controller measurements (Vivado 2025.2, out of context) from the *.kv files of run_all.sh.

    python3 make_table.py <kv dir> <out md> <out json> [--period 2.5]

Per variant: LUTs, FFs, flop types, control sets, logic levels and slack (ns) of each path group at the given period
(reg2reg, in2reg, reg2out, in2out), and the FSM Vivado extracted (state count and encoding, from the log). Fmax (reg2reg) is
1000 / (period - slack): the path delay the tool found, not a measurement of a routed design unless the suffix is _route.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def read_kv(p: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in p.read_text().splitlines():
        k, _, v = line.partition(" ")
        out[k] = v
    return out


def fsm_info(log: Path) -> str:
    if not log.exists():
        log = log.with_suffix(".fsm.txt")          # the committed copy: only the FSM lines of the log
    if not log.exists():
        return ""
    t = log.read_text(errors="replace")
    m = re.search(r"encoded FSM with state register '[^']+' using encoding '([^']+)'", t)
    n = len(re.findall(r"^\s+\w+ \|\s+[01]+ \|\s+[01]+\s*$", t, re.M))
    return f"{n} states, {m.group(1)}" if m else "not extracted"


def fnum(x: str | None, nd=2) -> str:
    try:
        return f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return "-"


def fmax(period: float, slack: str | None) -> str:
    try:
        return f"{1000 / (period - float(slack)):.0f}"
    except (TypeError, ValueError, ZeroDivisionError):
        return "-"


def main() -> int:
    d, md, js = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    period = float(sys.argv[sys.argv.index("--period") + 1]) if "--period" in sys.argv else 2.5
    sfx = sys.argv[sys.argv.index("--suffix") + 1] if "--suffix" in sys.argv else ""      # "_route": the numbers after opt/place/route
    rows = {p.stem: read_kv(p) for p in sorted(d.glob("*.kv"))}
    for n, r in rows.items():
        r["fsm"] = fsm_info(d / f"{n}.log")
    js.write_text(json.dumps({"period_ns": period, "variants": rows}, indent=1) + "\n")

    def tbl(title: str, names: list[str], note: str = "", cols=("LUT", "FF", "CTRLSETS", "LVL_r2r", "WNS_r2r", "Fmax", "WNS_in2r",
                                                                 "WNS_r2out", "WNS_in2out", "fsm")) -> str:
        head = {"LUT": "LUTs", "FF": "FFs", "CTRLSETS": "control sets", "LVL_r2r": "levels r2r", "WNS_r2r": "WNS r2r", "Fmax": "Fmax r2r (MHz)",
                "WNS_fsm": "WNS FSM->FSM", "WNS_in2r": "WNS in->reg", "WNS_r2out": "WNS reg->out", "WNS_in2out": "WNS in->out", "fsm": "FSM (extracted)"}
        out = [f"### {title}", "", note, "", "| variant | " + " | ".join(head[c] for c in cols) + " | flops (RE/CE/PE/SE) |",
               "|---|" + "---|" * (len(cols) + 1)]
        for n in names:
            r = rows.get(n)
            if not r:
                continue
            cells = []
            for c in cols:
                if c == "Fmax":
                    cells.append(fmax(period, r.get("WNS_r2r" + sfx)))
                elif c.startswith("WNS"):
                    cells.append(fnum(r.get(c + sfx)))
                else:
                    cells.append(r.get(c if c == "fsm" else c + sfx, "-"))
            out.append(f"| {n} | " + " | ".join(cells) + f" | {r.get('FDRE','-')}/{r.get('FDCE','-')}/{r.get('FDPE','-')}/{r.get('FDSE','-')} |")
        return "\n".join(out) + "\n"

    parts = [f"# Reference controller measurements (Vivado 2025.2, out of context, xc7a100tcsg324-1)\n\n"
             f"Clock {period} ns, input and output delay 0.5 ns. Slack in ns; negative = the path is longer than the budget. "
             + ("After opt_design, place_design and route_design (routed timing).\n" if sfx else "Synthesis only (no placement, so wire delay is an estimate: use it for order, not for Fmax).\n")]
    parts.append(tbl("Separation", ["sep_base", "sep_z1", "mono_base"], "Separated FSM (11 states + 4-bit counter, zero flag combinational or registered) against the "
                                                                     "monolithic FSM (23 states, no counter)."))
    parts.append(tbl("Outputs", ["sep_base", "sep_out1", "sep_out2", "mono_base", "mono_out1", "mono_out2"],
                     "OUT 0 combinational Moore decode, 1 registered decode (one cycle later), 2 lookahead (decode of the next state, registered)."))
    parts.append(tbl("Inputs", ["sep_base", "sep_in1", "sep_in2"], "IN 0 raw, 1 one register, 2 two ASYNC_REG registers."))
    names = [n for n in rows if "_enc_" in n]
    parts.append(tbl("Encoding", ["sep_base"] + [n for n in names if n.startswith("sep")] + ["mono_base"] + [n for n in names if n.startswith("mono")],
                     "`-fsm_extraction` mode (base = auto)."))
    parts.append(tbl("Reset style", ["sep_base", "sep_rst1", "sep_rst2", "sep_rst3"],
                     "0 async (FDCE), 1 sync (FDRE), 2 none (initial value), 3 async assert + 2-flop release."))
    parts.append(tbl("Reset style with a clock enable", [n for n in rows if n.startswith("sep_ce_rst")],
                     "The FSM advances only on `ce`. rst 4 = a synchronous reset looked at only when `ce` is high."))
    parts.append(tbl("Enable ratio (slow-FSM pattern)", [n for n in rows if n.startswith("ratio_")],
                     "One-in-N enable from a free-running counter; `_mc` adds `set_multicycle_path N -setup` and `N-1 -hold` on the FSM's own "
                     "registers (brief 20 pattern). WNS r2r is over every register pair, so it includes the enable counter; WNS FSM->FSM is the "
                     "FSM's own registers only.", cols=("LUT", "FF", "LVL_r2r", "WNS_r2r", "WNS_fsm", "Fmax")))
    parts.append(tbl("Input from another clock", [n for n in rows if n.startswith("cdc_")], "IN 0 / 1 / 2 on an `ack` launched by an unrelated clock."))
    md.write_text("\n".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
