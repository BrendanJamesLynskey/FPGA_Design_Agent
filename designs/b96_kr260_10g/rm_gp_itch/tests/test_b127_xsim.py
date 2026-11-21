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
