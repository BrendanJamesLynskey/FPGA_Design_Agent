"""Whole-core latency and equivalence records of build rm_gp_itch from xsim (brief 127): `python3 -m designs.b96_kr260_10g.rm_gp_itch.tests.measure_xsim <out dir> [phase ps ...]`.

Per phase between the receive and transmit user clocks and per speculation setting, one plan: link up, configuration, a replayed session (preamble, a bid, then one candidate packet for each
alignment of the message end in its 64-bit word), counters and the order frames' TX words. Writes <out>/latency_sim.json and one log per run. Clocks are 6.2058 ns; times are the ns of the clock
edge that LOADS each signal (sim/tb_itch_core.sv)."""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

from designs.b110_itch_ouch.model import gen, proto
from designs.b110_itch_ouch.model.ref import Cfg, Model
from designs.b96_kr260_10g.model import pcs
from designs.b96_kr260_10g.rm_gp_itch.host import itch_bench as B
from designs.b96_kr260_10g.rm_gp_itch.host import itch_host as H
from designs.b96_kr260_10g.rm_gp_itch.tests import xsim_session as X

T = X.T_CLK


def mk_frame(payload: bytes, **kw) -> bytes:
    args = dict(dst_mac=H.DEFAULTS["my_mac"], src_mac=H.DEFAULTS["venue_mac"], src_ip="192.168.58.15", dst_ip="192.168.58.10", sport=26000, dport=5810)
    args.update(kw)
    return H.eth_ip_udp(payload, **args)


def latency_session(cfg: Cfg, gap: int = 120, reps: int = 1):
    """Packets: the preamble, a bid, then `reps` x 8 candidate packets (a filler message of 12 to 19 bytes before the candidate Add moves the candidate's last byte through all 8 alignments).
    Returns (packets, frames, meta) with meta = [(packet length, index of the packet)] of the candidate packets."""
    g = gen.Gen(7, cfg)
    pre = g.preamble()[:3]
    pkts = [proto.mold_packet(b"SESSION001", 1, pre)]
    seq = 1 + len(pre)
    pkts.append(proto.mold_packet(b"SESSION001", seq, [proto.itch_A(g.loc0, g._t(), g._newref(), "B", 100, cfg.watch[0], gen.MID - 100)]))
    seq += 1
    meta = []
    for _ in range(reps):
        for n in range(12, 20):
            filler = proto.itch_other("P", n, g.loc0, 5)
            cand = proto.itch_A(g.loc0, g._t(), g._newref(), "S", 100, cfg.watch[0], gen.MID + 100)
            pkts.append(proto.mold_packet(b"SESSION001", seq, [filler, cand]))
            seq += 2
            meta.append((len(pkts[-1]), len(pkts) - 1))
    frames = [(mk_frame(p, ident=i), gap) for i, p in enumerate(pkts)]
    return pkts, frames, meta


def plan_for(spec_modes, cfg, frames, nwords_ok=True):
    p = B.Plan()
    p.link()
    for spec in spec_modes:
        p.mark(f"SPEC {int(spec)}")
        B.configure(p, cfg, spec=spec)
        B.load_replay(p, H.replay_image(frames))
        B.start_replay(p, wait_ms=5, frames=len(frames))
        p.d(len(frames) * 140 * 7 + 20_000)
        B.read_stats(p, prefix=f"s{int(spec)}.")
    return p


def analyse(log: str, pkts, meta, spec_modes, nframes: int):
    """Per order: the PCS-output word and the MAC word carrying the message's last byte, `go`, and the order's start strobe, from the monitors.
    The trigger frame of an order is the last frame start (receiver PCS output) before its `go`; the orders come back as frames too, but always after their own start strobe."""
    xw: dict[int, dict[int, float]] = {}
    mwf: list[dict[int, float]] = []           # MAC output words, one dict per frame, in order
    sessions: list[dict] = []
    for l in log.splitlines():
        t = l.split()
        if not t:
            continue
        if t[0] == "MARK":
            sessions.append({"go": [], "osop": []})
        elif t[0] == "XW":
            xw.setdefault(int(t[1]), {})[int(t[2])] = float(t[3])
        elif t[0] == "MW":
            i, tm = int(t[1]), float(t[2])
            if i == 0:
                mwf.append({})
            if mwf:
                mwf[-1][i] = tm
        elif t[0] == "GO" and sessions:
            sessions[-1]["go"].append(float(t[1]))
        elif t[0] == "OSOP" and sessions:
            sessions[-1]["osop"].append(float(t[1]))
    starts = sorted((d[0], n) for n, d in xw.items() if 0 in d)
    out = {}
    for si, spec in enumerate(spec_modes):
        ss = sessions[si]
        rows = []
        for k, ((pl, pidx), g_, s_o) in enumerate(zip(meta, ss["go"], ss["osop"])):
            q = 42 + pl - 1
            fstart, fn = max((t_, n) for t_, n in starts if t_ < g_)
            wx = 1 + (q >> 3)
            t_x = xw[fn].get(wx)
            mf = next((m_ for m_ in mwf if m_.get(0, 0) > fstart), None)
            t_m = mf.get(q >> 3) if mf else None
            rows.append({"end_byte_in_word": q & 7, "t_x_pcs": t_x, "t_x_mac": t_m, "t_go": g_, "t_sop": s_o,
                         "tick_to_trade_gt_clocks": (s_o - (t_x - T)) / T + 2 if t_x is not None else None,
                         "mac_word_to_sop_clocks": (s_o - t_m) / T if t_m is not None else None,
                         "pcs_word_to_mac_word_clocks": (t_m - t_x) / T if t_x is not None and t_m is not None else None,
                         "go_to_sop_clocks": (s_o - g_) / T})
        out["speculative" if spec else "at_verdict"] = rows
    return out


def summarise(rows, key):
    v = [r[key] for r in rows if r.get(key) is not None]
    return {"n": len(v), "min": round(min(v), 2), "mean": round(st.mean(v), 2), "max": round(max(v), 2)} if v else None


def aggregate(res: dict) -> dict:
    """results/b127/core_sim.json: per mode and quantity, the minimum, mean and maximum over every order of every phase (the layout latency_stages.yaml reads)."""
    out = {"what": "whole core of build rm_gp_itch in xsim 2026.1 with AMD's real XPM macros and the GT stand-in (tests/measure_xsim.py), clocks of 6.2058 ns, all orders of all phases", "phases_ps": res["phases_ps"], "itch_to_order": {}}
    for mode in ("speculative", "at_verdict"):
        out["itch_to_order"][mode] = {}
        for q in ("tick_to_trade_gt_clocks", "mac_word_to_sop_clocks", "pcs_word_to_mac_word_clocks", "go_to_sop_clocks"):
            v = [r[q] for ph in res["results"].values() for r in ph[mode]["rows"] if r.get(q) is not None]
            out["itch_to_order"][mode][q] = {"n": len(v), "min": round(min(v), 2), "mean": round(st.mean(v), 2), "max": round(max(v), 2)}
    return out


def main() -> None:
    out = Path(sys.argv[1])
    phases = [int(x) for x in sys.argv[2:]] or [0, 1550, 3100, 4650]
    out.mkdir(parents=True, exist_ok=True)
    cfg = Cfg(thr=gen.MID + 3 * gen.TICK, max_pos=10**6, max_qty=1000, band=1_000_000)
    pkts, frames, meta = latency_session(cfg)
    m = Model(cfg)
    for p in pkts:
        m.feed(p, False)
    modes = (False, True)
    plan = plan_for(modes, cfg, frames)
    res = {"clock_ns": T, "orders_per_run": len(m.orders), "phases_ps": phases, "results": {}}
    for ph in phases:
        log = X.run_plan(plan, out / f"run_ph{ph}", phase_ps=ph)
        (out / f"xsim_ph{ph}.log").write_text(log)
        rd = B.decode_log(plan, log)
        for sp in (0, 1):
            pre = f"s{sp}."
            bad = {k: v for k, v in B.counters_vs_model({k[len(pre):]: v for k, v in rd.items() if k.startswith(pre)}, m).items()}
            assert not bad, (ph, sp, bad)
            assert rd[pre + "ord.sent"] == len(m.orders) and rd[pre + "ord.drop"] == 0, (ph, sp)
        rows = analyse(log, pkts, meta, modes, len(frames))
        res["results"][str(ph)] = {mode: {k: summarise(r, k) for k in ("tick_to_trade_gt_clocks", "mac_word_to_sop_clocks", "pcs_word_to_mac_word_clocks", "go_to_sop_clocks")} | {"rows": r}
                                   for mode, r in rows.items()}
        print(ph, {mode: v["tick_to_trade_gt_clocks"] for mode, v in res["results"][str(ph)].items()})
    (out / "latency_sim.json").write_text(json.dumps(res, indent=1))
    (out / "core_sim.json").write_text(json.dumps(aggregate(res), indent=1))


if __name__ == "__main__":
    main()
