#!/usr/bin/env python3
"""summarise_sweeps.py <crc log> <fir log>: median (p50) time per call for each path and size, from the DDR console logs of t_crc / t_fir
(lines `S <name> <bytes> n=<reps> unit=ns <min> <p50> <p95> <max> <mean>`), and the HP and ACP speed-up over the best software path."""
import re, sys
def load(p):
    d = {}
    for l in open(p):
        m = re.match(r"S (\S+) (\d+) n=(\d+) unit=ns (\S+) (\S+) (\S+) (\S+) (\S+)", l)
        if m: d.setdefault(int(m[2]), {})[m[1]] = (float(m[5]), float(m[6]), int(m[3]))   # p50, p95, reps
    return d
def table(title, d, sw):
    print(f"### {title}\n\n| bytes | reps | " + " | ".join(f"{k} p50 us" for k in sw) + " | HP p50 us | ACP p50 us | best SW / HP | best SW / ACP | winner |\n|" + "---|" * (len(sw) + 7))
    hp, acp = ("hp_crc", "acp_crc") if "crc" in sw[0] else ("hp_fir16", "acp_fir16")
    for b in sorted(d):
        r = d[b]; best = min(r[k][0] for k in sw)
        w = min([("SW", best), ("HP", r[hp][0]), ("ACP", r[acp][0])], key=lambda t: t[1])[0]
        print(f"| {b} | {r[hp][2]} | " + " | ".join(f"{r[k][0]/1e3:.2f}" for k in sw) + f" | {r[hp][0]/1e3:.2f} | {r[acp][0]/1e3:.2f} | {best/r[hp][0]:.2f} | {best/r[acp][0]:.2f} | {w} |")
    print()
table("CRC-32 (packet length in bytes)", load(sys.argv[1]), ["sw_crc_bytewise", "sw_crc_slice8"])
table("16-tap FIR (4 bytes per sample)", load(sys.argv[2]), ["sw_fir16"])
