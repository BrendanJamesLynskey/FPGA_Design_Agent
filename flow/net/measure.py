#!/usr/bin/env python3
"""Line rate, latency and table update cost of the packet-processing blocks, measured in simulation (brief 40).

    python3 flow/net/measure.py [--out results/b40]

Writes <out>/measure.json and <out>/measure.md. Every number is a count of clocks from a recorded simulation; rates
in packets per second are those clocks converted at a stated clock frequency (the real Fmax comes from the OOC
synthesis runs, which are not part of this file). Theory for comparison: Ethernet minimum frame = 64 bytes + 8
preamble/SFD + 12 inter-frame gap = 84 byte times, so 148,809 frames/s at 100 Mb/s and 1,488,095 at 1 Gb/s.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import tempfile
from pathlib import Path

from flow.net import model, pktio, sim, traffic
from flow.net.tests import (test_40_mac_rtl as mac, test_40_parser_rtl as par, test_40_queues_rtl as que,
                            test_40_rewrite_rtl as rew, test_40_switch_rtl as swt, test_40_tables_rtl as tab)

THEORY_100M = 100e6 / (84 * 8)
THEORY_1G = 1e9 / (84 * 8)


def tables(tmp: Path) -> dict:
    out = {}
    # exact: insert/delete/age costs at the core, and lookups a clock
    lks, cmds, states, want, t = tab.exact_case(1, idx_w=10, stash=4, n_keys=600, n_lk=4000)
    res, polls, meta = tab.run(tmp, 0, {"KEY_W": 48, "ACT_W": 16, "IDX_W": 10, "STASH": 4}, lks, cmds)
    r = pktio.read_resp(tmp / "resp.txt")
    c = [x[0] for x in r["words"]["C"]]
    k = [x[0] for x in r["words"]["K"]]
    ops = [w[1][0] for w in r["words"]["C"]]
    lat = [kk - cc for cc, kk in zip(c, k)]
    by = {}
    for o, l in zip(ops, lat):
        by.setdefault({1: "insert", 2: "delete", 3: "age_sweep", 9: "bad_op"}.get(o, str(o)), set()).add(l)
    axil_cycles = statistics.median([b - a for a, b in zip([p for p, _ in polls], [p for p, _ in polls][1:])])
    out["exact"] = {"params": "KEY_W 48, IDX_W 10 (2 x 1024 buckets), STASH 4", "lookup_latency_clocks": tab.LAT[0],
                    "lookups_per_clock": 1, "core_clocks_per_command": {k2: sorted(v) for k2, v in by.items()},
                    "capacity_entries": 2 * 1024 + 4, "inserted_ok_of_600": sum(1 for s in want[:600] if s == 0),
                    "median_clocks_per_command_through_axil_incl_poll": axil_cycles}
    # LPM and ternary: from their own runs
    words, alloc = model.lpm_compile(tab.lpm_routes(random.Random(4), 250), 12, (16, 32, 64))
    out["lpm"] = {"params": "strides 8-8-8-8, L1/L2/L3 = 16/32/64 nodes", "words_for_250_routes": len(words),
                  "lookups_per_clock": 1, "update": "one word a command; a route add touches 1..256 words"}
    def core_cost(d, table, params, cmds):
        tab.run(d, table, params, [(0, 1)] * 50, cmds)
        r = pktio.read_resp(d / "resp.txt")
        return sorted({k[0] - c[0] for c, k in zip(r["words"]["C"], r["words"]["K"])})

    tc = []
    for e in range(8):
        tab.prog_cmd(tc, 1, addr=e, key=e, care=0xFF, act=e)
    tc_del = []
    tab.prog_cmd(tc_del, 2, addr=3)
    d2 = tmp / "tern"
    d2.mkdir()
    tp = {"KEY_W": 40, "ACT_W": 16, "ENTRIES": 32, "CHUNK_W": 5}
    out["ternary"] = {"params": "KEY_W 40, CHUNK_W 5, 32 entries", "lookups_per_clock": 1,
                      "lookup_latency_clocks": tab.LAT[2] if 2 in tab.LAT else None,
                      "core_clocks_per_write": core_cost(d2, 2, tp, tc), "core_clocks_per_delete": core_cost(d2, 2, tp, tc_del)}
    lc = []
    for i in range(8):
        tab.prog_cmd(lc, 1, addr=i, raw=i)
    d3 = tmp / "lpmc"
    d3.mkdir()
    out["lpm"]["core_clocks_per_word_write"] = core_cost(d3, 1, {"KEY_W": 32, "ACT_W": 12, "L1_NODES": 16,
                                                              "L2_NODES": 32, "L3_NODES": 64}, lc)
    out["lpm"]["lookup_latency_clocks"] = tab.LAT[1]
    return out


def switch(tmp: Path) -> dict:
    """Core clocks per frame under backlog: minimum frames offered on all four ports."""
    r0 = random.Random(8)
    ports = [[] for _ in range(4)]
    for p in range(4):
        for i in range(60):
            src = 0x020000000000 | (p << 8) | 1
            dst = 0x020000000000 | (((p + 1) % 4) << 8) | 1
            ports[p].append((dst.to_bytes(6, "big") + src.to_bytes(6, "big") + b"\x08\x00" +
                             bytes(r0.randrange(256) for _ in range(46)), 0))
    old = dict(swt.VLANS)
    swt.VLANS.clear()
    swt.VLANS.update({10: 0b1111, 20: 0b1111, 30: 0b1111})
    try:
        r = swt.run(tmp, ports, (), sched="continuous", seed=1, p_valid=1.0)
    finally:
        swt.VLANS.clear()
        swt.VLANS.update(old)
    picks = [c for c, _ in r["words"]["P"]]
    gaps = [b - a for a, b in zip(picks[20:], picks[21:])]
    per = statistics.median(gaps)
    return {"frames_offered": 240, "frames_taken": len(picks), "in_drops": r["meta"]["in_drops"],
            "core_clocks_per_60B_frame": per,
            "frames_per_s_at_50MHz": 50e6 / per, "frames_per_s_at_100MHz": 100e6 / per,
            "ports_at_100M_line_rate_supported_at_50MHz": round(50e6 / per / THEORY_100M, 2),
            "ports_at_100M_line_rate_supported_at_100MHz": round(100e6 / per / THEORY_100M, 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/b40")
    a = ap.parse_args()
    res = {}
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        for name, fn in (("mac_rx", mac.line_rate_rx), ("parser", par.line_rate), ("rewrite", rew.line_rate),
                         ("queues", que.line_rate), ("tables", tables), ("switch", switch)):
            d = t / name
            d.mkdir()
            res[name] = fn(d)
            print(name, res[name], flush=True)
    res["theory"] = {"min_frames_per_s_100M": THEORY_100M, "min_frames_per_s_1G": THEORY_1G,
                     "byte_wide_1G_needs_MHz": 125.0}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "measure.json").write_text(json.dumps(res, indent=1, default=list) + "\n")
    print("wrote", out / "measure.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
