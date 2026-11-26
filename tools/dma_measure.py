#!/usr/bin/env python3
"""Throughput, latency and descriptor-overhead measurements of ip_lib/sg_dma in simulation (brief 241), against the documented behaviour of AMD's
AXI DMA (ip_lib/sg_dma/amd_axi_dma_model.py), and the plots.

    python3 tools/dma_measure.py run  [--out results/241_dma/sim_measure.jsonl]     # cocotb `measure` test at each point (Icarus; minutes)
    python3 tools/dma_measure.py plot [--in results/241_dma/sim_measure.jsonl]      # results/241_dma/*.svg and summary.json

Every number in the README and DATASHEET comes from the JSON-lines file this writes. The memory model is ip_lib/sg_dma/tb/sg_dma_cocotb.py's `Mem`
with read latency RLAT and write-response latency WLAT clocks, no random gaps, an always-ready stream: the engine's own limits, not a loaded system's."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RES = ROOT / "results" / "241_dma"
SIZES = [64, 256, 1024, 4096, 16384]
CONFIGS = [  # (DIR, DATA_W, MAX_BURST, OUTSTANDING)
    (0, 32, 16, 4), (1, 32, 16, 4), (0, 64, 16, 4), (0, 32, 16, 1), (0, 32, 4, 4)]
RLAT, WLAT = 20, 15


AMD_LIKE = [(0, 32, 16, 4), (1, 32, 16, 4)]      # one 10,000-byte transfer, the size PG021's table 2 uses


def run(out: Path, like_only: bool = False) -> None:
    from flow import cocotb_run
    from flow.net import sim
    tb = ROOT / "ip_lib" / "sg_dma" / "tb"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not like_only:
        out.write_text("")
    for d, w, mb, oc in ([] if like_only else CONFIGS):
        for size in SIZES:
            for n in (1, 6):
                cocotb_run.run(f"sgm_d{d}_w{w}_b{mb}_o{oc}_s{size}_n{n}", "sg_dma", sim.rtl("sg_dma"), "sg_dma_cocotb", tb,
                               parameters={"DIR": d, "DATA_W": w, "MAX_BURST": mb, "OUTSTANDING": oc}, testcase="measure",
                               extra_env={"PYTHONPATH": str(ROOT), "SGD_N": str(n), "SGD_SIZE": str(size), "SGD_RLAT": str(RLAT),
                                          "SGD_WLAT": str(WLAT), "SGD_OUT": str(out)})
                print(d, w, mb, oc, size, n, flush=True)
    for d, w, mb, oc in AMD_LIKE:                       # the like-for-like point against PG021 table 2 (10,000 bytes, one descriptor)
        cocotb_run.run(f"sgm_d{d}_like", "sg_dma", sim.rtl("sg_dma"), "sg_dma_cocotb", tb,
                       parameters={"DIR": d, "DATA_W": w, "MAX_BURST": mb, "OUTSTANDING": oc}, testcase="measure",
                       extra_env={"PYTHONPATH": str(ROOT), "SGD_N": "1", "SGD_SIZE": "10000", "SGD_RLAT": str(RLAT), "SGD_WLAT": str(WLAT), "SGD_OUT": str(out)})


def plot(src: Path) -> None:
    import matplotlib
    matplotlib.use("svg")
    import matplotlib.pyplot as plt
    from ip_lib.sg_dma import amd_axi_dma_model as A
    rows = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]
    key = lambda r: (r["P"]["DIR"], r["P"]["DATA_W"], r["P"]["MAX_BURST"], r["P"]["OUTSTANDING"])
    summ = {"rlat": RLAT, "wlat": WLAT, "points": []}
    for r in (x for x in rows if x["size"] != 10000):
        bb = r["beat_bytes"]
        per_desc = r["head_to_last_b"] / r["n"] if r["n"] > 1 else None
        summ["points"].append({**{k: r[k] for k in ("n", "size", "head_to_first_ar", "first_beat", "last_beat", "head_to_last_b", "span_beats", "data_beats")},
                               "dir": r["P"]["DIR"], "data_w": r["P"]["DATA_W"], "max_burst": r["P"]["MAX_BURST"], "outstanding": r["P"]["OUTSTANDING"],
                               "port_limit_bytes_per_clock": bb, "bytes_per_clock_incl_descriptors": r["n"] * r["size"] / r["head_to_last_b"],
                               "fraction_of_port_limit": r["n"] * r["size"] / r["head_to_last_b"] / bb})
    summ["like_for_like"] = [{"dir": r["P"]["DIR"], "bytes": r["size"], "clocks_first_data_address_to_last_beat": r["first_data_addr_to_last_beat"],
                              "MB_per_s_at_100MHz": round(r["size"] / r["first_data_addr_to_last_beat"] * 100, 2),
                              "amd_documented_MB_per_s_at_100MHz": 399.04 if r["P"]["DIR"] == 0 else 298.59,
                              "amd_model_start_up_clocks": A.mm2s_clocks(r["size"])["first_beat"] if r["P"]["DIR"] == 0 else A.s2mm_clocks(r["size"])["first_aw"],
                              "ours_start_up_clocks_head_write_to_first_data_beat": r["first_beat"]} for r in rows if r["size"] == 10000]
    (RES / "summary.json").write_text(json.dumps(summ, indent=1) + "\n")
    col = {(0, 32, 16, 4): "#1f3a5f", (1, 32, 16, 4): "#7a3b2e", (0, 64, 16, 4): "#3b6e4f", (0, 32, 16, 1): "#888888", (0, 32, 4, 4): "#b08a2e"}
    name = lambda k: f"{'MM2S' if k[0] == 0 else 'S2MM'} {k[1]}-bit, burst {k[2]}, {k[3]} outstanding"
    # 1: fraction of the port limit against transfer size (6 descriptors back to back)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for k in sorted(set(map(key, rows))):
        pts = sorted((r["size"], r["n"] * r["size"] / r["head_to_last_b"] / r["beat_bytes"]) for r in rows if key(r) == k and r["n"] == 6)
        ax.plot(*zip(*pts), marker="o", color=col.get(k), label=name(k))
    xs = [64, 256, 1024, 4096, 16384]
    ax.plot(xs, [A.mm2s_throughput_bytes_per_clock(x) / 4 for x in xs], "k--", label="AXI DMA model MM2S (documented, 32-bit, incl. its start-up)")
    ax.plot(xs, [A.s2mm_throughput_bytes_per_clock(x) / 4 for x in xs], "k:", label="AXI DMA model S2MM (documented, 32-bit)")
    ax.set_xscale("log", base=2)
    ax.set_xlabel("descriptor size (bytes)")
    ax.set_ylabel("fraction of the memory port limit")
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=6.5, loc="lower right")
    ax.set_title(f"Sustained throughput, six descriptors back to back (memory latency {RLAT} read / {WLAT} write clocks)", fontsize=8)
    fig.tight_layout()
    fig.savefig(RES / "throughput_vs_size.svg")
    # 2: latency of one transfer, descriptor write to status response, and the descriptor overhead
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for k in sorted(set(map(key, rows))):
        pts = sorted((r["size"], r["head_to_last_b"] - r["size"] / r["beat_bytes"]) for r in rows if key(r) == k and r["n"] == 1 and r["size"] != 10000)
        ax.plot(*zip(*pts), marker="o", color=col.get(k), label=name(k))
    ax.set_xscale("log", base=2)
    ax.set_xlabel("descriptor size (bytes)")
    ax.set_ylabel("clocks beyond one beat per clock")
    ax.set_title("Descriptor overhead: HEAD write to status response, minus the data beats", fontsize=8)
    ax.legend(fontsize=6.5)
    fig.tight_layout()
    fig.savefig(RES / "latency_overhead.svg")
    print("wrote", RES / "summary.json")


def tables(src: Path | None = None) -> str:
    """The markdown tables of DATASHEET.md and results/241_dma/README.md, generated from summary.json (a test compares the files with this)."""
    s = json.loads((RES / "summary.json").read_text())
    cfg = lambda p: (p["dir"], p["data_w"], p["max_burst"], p["outstanding"])
    name = lambda k: f"{'MM2S' if k[0] == 0 else 'S2MM'}, {k[1]}-bit, burst {k[2]}, {k[3]} outstanding"
    sizes = sorted({p["size"] for p in s["points"]})
    L = ["| Configuration | " + " | ".join(f"{z} B" for z in sizes) + " |", "|---|" + "---|" * len(sizes)]
    for k in sorted({cfg(p) for p in s["points"]}):
        row = {p["size"]: p for p in s["points"] if cfg(p) == k and p["n"] == 6}
        L.append(f"| {name(k)} | " + " | ".join(f"{row[z]['fraction_of_port_limit']:.3f}" for z in sizes) + " |")
    L += ["", "| Configuration | " + " | ".join(f"{z} B" for z in sizes) + " |", "|---|" + "---|" * len(sizes)]
    for k in sorted({cfg(p) for p in s["points"]}):
        row = {p["size"]: p for p in s["points"] if cfg(p) == k and p["n"] == 1}
        L.append(f"| {name(k)} | " + " | ".join(f"{row[z]['head_to_last_b']}" for z in sizes) + " |")
    L += ["", "| Direction | clocks, first data address to last beat | MB/s at 100 MHz | AMD AXI DMA, PG021 table 2 (MB/s) | start-up, AMD model | start-up, ours |", "|---|---|---|---|---|---|"]
    for r in s["like_for_like"]:
        L.append(f"| {'MM2S' if r['dir'] == 0 else 'S2MM'}, {r['bytes']} bytes | {r['clocks_first_data_address_to_last_beat']} | {r['MB_per_s_at_100MHz']} | "
                 f"{r['amd_documented_MB_per_s_at_100MHz']} | {r['amd_model_start_up_clocks']} | {r['ours_start_up_clocks_head_write_to_first_data_beat']} |")
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "like", "plot", "tables"])
    ap.add_argument("--out", default=str(RES / "sim_measure.jsonl"))
    ap.add_argument("--in", dest="inp", default=str(RES / "sim_measure.jsonl"))
    a = ap.parse_args()
    if a.cmd == "tables":
        print(tables())
    else:
        run(Path(a.out), a.cmd == "like") if a.cmd in ("run", "like") else plot(Path(a.inp))
