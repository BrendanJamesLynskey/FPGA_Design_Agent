"""The whole core of build rm_gp_itch in xsim (real XPM macros, GT stand-in) driven by the host's plan (brief 127): bit-exact against brief 110's model and the latency in clocks.
Skipped without Vivado's xsim. B127_RECORD=<dir> writes the records (results/b127)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from designs.b110_itch_ouch.model import gen, proto
from designs.b110_itch_ouch.model.ref import Cfg, Model
from designs.b96_kr260_10g.rm_gp_itch.host import itch_bench as B
from designs.b96_kr260_10g.rm_gp_itch.host import itch_host as H
from designs.b96_kr260_10g.rm_gp_itch.tests import xsim_session as X

pytestmark = pytest.mark.skipif(not X.have_xsim(), reason="needs Vivado xsim 2026.1")


def mk_frame(payload: bytes, **kw) -> bytes:
    args = dict(dst_mac=H.DEFAULTS["my_mac"], src_mac=H.DEFAULTS["venue_mac"], src_ip="192.168.58.15", dst_ip="192.168.58.10", sport=26000, dport=5810)
    args.update(kw)
    return H.eth_ip_udp(payload, **args)


def small_session(cfg: Cfg, gap: int = 150):
    g = gen.Gen(21, cfg)
    pkts = [proto.mold_packet(b"SESSION001", 1, g.preamble()[:3])]
    seq = 4

    def add(side, inst, px):
        nonlocal seq
        ref = g._newref()
        m = proto.itch_A(g.loc0 + inst, g._t(), ref, side, 100, cfg.watch[inst], px)
        pkts.append(proto.mold_packet(b"SESSION001", seq, [m]))
        seq += 1
    add("B", 0, gen.MID - 100)
    for k in range(3):
        add("S", 0, gen.MID + 100 + 10 * k)
    add("S", 0, gen.MID + 900)
    frames = [(mk_frame(p, ident=i), gap) for i, p in enumerate(pkts)]
    return pkts, frames


def test_whole_core_session(tmp_path) -> None:
    for spec in (False, True):
        cfg = Cfg(thr=gen.MID + 3 * gen.TICK, max_pos=10**6, max_qty=1000, band=1_000_000)
        pkts, frames = small_session(cfg)
        m = Model(cfg)
        for p in pkts:
            m.feed(p, False)
        img = H.replay_image(frames)
        p = B.Plan()
        p.link()
        B.configure(p, cfg, spec=spec)
        B.load_replay(p, img)
        B.start_replay(p, wait_ms=5, frames=len(frames))
        p.d(60_000)
        B.read_stats(p)
        B.read_capture(p, slots=len(m.orders))
        log = X.run_plan(p, tmp_path / f"spec{int(spec)}")
        assert "DONE" in log, log[-500:]
        res = B.decode_log(p, log)
        assert not B.counters_vs_model(res, m), B.counters_vs_model(res, m)
        assert res["rp.frames"] == len(frames) and res["us.fwd"] == len(frames) and res["ord.sent"] == len(m.orders) and res["ord.drop"] == 0
        chk = B.order_frames_vs_model(res, m)
        assert not chk["problems"] and chk["compared"] == len(m.orders), chk
        # every top-of-book update record of the book, in order, equal to brief 110's model (bit exact), whole core
        tu = X.monitors(log)["tu"]
        want = [(r["inst"], r["side"], r["px"], r["sz"], int(r["ok"]), r["cause_px"]) for r in m.tus]
        assert tu == want, (len(tu), len(want), next((i for i, (a, b) in enumerate(zip(tu, want)) if a != b), None))
        # the order frames on the transmit side of the MAC: every non-idle XGMII word, parsed by the independent reference parser; the good ones equal the model's frames
        from designs.b96_kr260_10g.model import pcs
        wire = [f for f in pcs.parse_xgmii(X.monitors(log)["txw"] + [(0x0707070707070707, 0xFF)] * 4) if "data" in f]
        good = [f for f in wire if f.get("fcs_ok") and len(f["data"]) == 113 and f["data"][23] == 6]          # TCP frames of 113 bytes: the orders
        assert len(good) == len(m.orders), (len(good), len(m.orders))
        for k, (f, (fr, sq)) in enumerate(zip(good, [(o["frame"], 1 + 59 * i) for i, o in enumerate(m.orders)])):
            assert not H.check_order_frame(f["data"], fr, my_mac=H.DEFAULTS["my_mac"], venue_mac=H.DEFAULTS["venue_mac"], my_ip=H.DEFAULTS["my_ip"], venue_ip=H.DEFAULTS["venue_ip"],
                                           sport=H.DEFAULTS["sport"], dport=H.DEFAULTS["order_port"], seq=sq, ack=1), f"order {k} on the wire"


def test_latency_record(tmp_path) -> None:
    """The whole-core latency record (results/b127/core_sim.json) for the phases in B127_PHASES (default: 0 only; the committed record has four). Written to B127_CORE_RESULTS when set."""
    import os
    from designs.b96_kr260_10g.rm_gp_itch.tests import measure_xsim as M
    phases = [int(x) for x in os.environ.get("B127_PHASES", "0").split()]
    cfg = Cfg(thr=gen.MID + 3 * gen.TICK, max_pos=10**6, max_qty=1000, band=1_000_000)
    pkts, frames, meta = M.latency_session(cfg)
    m = Model(cfg)
    for p in pkts:
        m.feed(p, False)
    modes = (False, True)
    plan = M.plan_for(modes, cfg, frames)
    res = {"clock_ns": X.T_CLK, "orders_per_run": len(m.orders), "phases_ps": phases, "results": {}}
    for ph in phases:
        log = X.run_plan(plan, tmp_path / f"ph{ph}", phase_ps=ph)
        rd = B.decode_log(plan, log)
        for sp in (0, 1):
            pre = f"s{sp}."
            assert not B.counters_vs_model({k[len(pre):]: v for k, v in rd.items() if k.startswith(pre)}, m)
            assert rd[pre + "ord.sent"] == len(m.orders) and rd[pre + "ord.drop"] == 0
        rows = M.analyse(log, pkts, meta, modes, len(frames))
        res["results"][str(ph)] = {mode: {"rows": r} for mode, r in rows.items()}
    agg = M.aggregate(res)
    sp = agg["itch_to_order"]["speculative"]
    assert 5 <= sp["mac_word_to_sop_clocks"]["min"] and sp["mac_word_to_sop_clocks"]["max"] <= 9, sp
    if os.environ.get("B127_CORE_RESULTS"):
        Path(os.environ["B127_CORE_RESULTS"]).write_text(json.dumps(agg, indent=1))
