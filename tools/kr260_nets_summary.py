#!/usr/bin/env python3
"""Brief 162: per-net routed length of the KR260 carrier's PL-facing nets, from a dump of AMD's Allegro board file.

    python3 tools/kr260_nets_summary.py --dump <dir with nets.csv and net_vias.csv> [--out results/162_kr260_si/kr260_net_lengths.csv]

The dump comes from a local, uncommitted parser run on ``BRD_05101_01_rev_b01_aa.brd`` (AMD xtp756, AMD copyright, never committed;
the parser is KiCad's GPL Allegro importer, built stand-alone in a scratch folder). Only these derived per-net numbers are committed.
Lengths are copper track length on the carrier (centre-line, straight segments plus arcs); they exclude the K26 SOM's own routing and the BGA/connector escape,
and the via stubs. ``total_mil`` is the sum over layers.
"""
from __future__ import annotations

import argparse
import collections
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUPS = [
    ("rgmii_phy2_hpa", re.compile(r"^HPA0\d(?:[NP]|_CC[NP]|P_CLK)$")),       # the PHY2 (port A) page's HPA0x nets; unconnected (_NC) pins excluded
    ("rgmii_phy3_hpb", re.compile(r"^HPB0\d(?:[NP]|_CC[NP]|P_CLK)$")),
    ("pmod_connector_side", re.compile(r"^PMOD[1-4]_IO[1-8]_HD[AB]\d+(_CC)?$")),
    ("pmod_som_side", re.compile(r"^HD[AB]\d+(_CC)?$")),
    ("phy_misc", re.compile(r"^(PL_)?GEM[23]_(RESET_B|GPIO[01]|INT_PWDN|XTAL_IN|XTAL_IN_R|RBIAS|JTAG|LED[012]_CA)$")),
    ("uart_ftdi", re.compile(r"^FTDI_UARTB_[RT]XD$")),
    ("sfp_ctl", re.compile(r"^SFP_RS[01]$")),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True)
    ap.add_argument("--out", default=str(ROOT / "results/162_kr260_si/kr260_net_lengths.csv"))
    a = ap.parse_args()
    d = Path(a.dump)
    lay = collections.defaultdict(dict)
    wid = {}
    for r in csv.DictReader((d / "nets.csv").open()):
        name = r["layer"].split(" ")[-1]
        lay[r["net"]][name] = lay[r["net"]].get(name, 0.0) + float(r["length_mil"])
        wid[r["net"]] = (float(r["min_width_mil"]), float(r["max_width_mil"]))
    vias = {r["net"]: int(r["n_vias"]) for r in csv.DictReader((d / "net_vias.csv").open())}
    rows = []
    for net in sorted(lay):
        for g, rx in GROUPS:
            if rx.match(net):
                tot = sum(lay[net].values())
                rows.append({"group": g, "net": net, "total_mil": round(tot, 1), "total_in": round(tot / 1000, 3), "vias": vias.get(net, 0),
                             "layers": " ".join(f"{k}={v:.0f}" for k, v in sorted(lay[net].items(), key=lambda kv: -kv[1])),
                             "trace_width_mil": f"{wid[net][0]:g}-{wid[net][1]:g}"})
                break
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    by = collections.defaultdict(list)
    for r in rows:
        by[r["group"]].append(r["total_in"])
    for g, v in by.items():
        print(f"{g}: {len(v)} nets, {min(v):.2f} to {max(v):.2f} in, median {sorted(v)[len(v) // 2]:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
