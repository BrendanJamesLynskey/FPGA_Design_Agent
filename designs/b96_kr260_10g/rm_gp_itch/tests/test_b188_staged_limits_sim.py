"""Brief 188 (#2): a half-written set of limits never takes effect. The whole core in xsim 2026.1 (as test_b127_stages_sim.py), driven by a host script.

Phase a: candidates play under the committed limits (4 orders). Phase b: IT_MAXPOS is lowered to 150 but NOT committed; the clears are committed-free commands; the candidates play again and
must see the OLD limits (4 more orders, no rej_pos), while a read of IT_MAXPOS returns the held value and a read of IT_CMD shows PENDING (bit 0). Phase c: COMMIT; PENDING falls to 0 and the
same candidates now meet the new limit (one order, three rej_pos). A write sequence that stops early therefore leaves the old, complete set in force. Skipped without xsim."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from designs.b110_itch_ouch.model import gen, proto
from designs.b96_kr260_10g.rm_gp_itch.host import b127_stages as S
from designs.b96_kr260_10g.rm_gp_itch.host import itch_bench as B
from designs.b96_kr260_10g.rm_gp_itch.host import itch_host as H
from designs.b96_kr260_10g.rm_gp_itch.tests import xsim_session as X

pytestmark = pytest.mark.skipif(not X.have_xsim(), reason="needs Vivado xsim 2026.1")


def test_half_written_limits_never_take_effect(tmp_path) -> None:
    run, owner = X.sim_runner(tmp_path / "staged")
    cfg = S.stage_cfg(max_pos=10**6)
    g = gen.Gen(404, cfg)
    pkts = [proto.mold_packet(b"SESSION001", 1, g.preamble()[:3]),
            proto.mold_packet(b"SESSION001", 4, [proto.itch_A(g.loc0, g._t(), g._newref(), "B", 100, cfg.watch[0], gen.MID - 100)])]
    seq = 5
    for k in range(4):
        pkts.append(proto.mold_packet(b"SESSION001", seq, [proto.itch_A(g.loc0, g._t(), g._newref(), "S", 100, cfg.watch[0], gen.MID + 100 + 10 * k)])); seq += 1
    frames = [(S.mk_frame(p, ident=i), 400, False) for i, p in enumerate(pkts)]
    clears = B.CMD["clr_flags"] | B.CMD["clr_book"] | B.CMD["clr_ref"] | B.CMD["clr_pos"]
    p = B.Plan()
    p.link()
    B.configure(p, cfg, rp_loops=1)
    B.load_replay(p, H.replay_image(frames))
    B.start_replay(p, wait_ms=300, frames=len(frames))
    p.d(len(frames) * 400 * 7 + 20_000)
    B.read_stats(p, "a.")
    p.r(B.ADDR["IT_CMD"], "cmd_a")
    p.w(B.ADDR["IT_MAXPOS"], 150).d(B.HS_NS)                       # staged only
    p.r(B.ADDR["IT_MAXPOS"], "maxpos_held").r(B.ADDR["IT_CMD"], "cmd_pending")
    p.w(B.ADDR["IT_CMD"], clears).d(B.HS_NS * 4)                    # no COMMIT
    B.start_replay(p, wait_ms=300, frames=len(frames))
    p.d(len(frames) * 400 * 7 + 20_000)
    B.read_stats(p, "b.")
    p.w(B.ADDR["IT_CMD"], clears | B.CMD["commit"]).d(B.HS_NS * 4)
    p.r(B.ADDR["IT_CMD"], "cmd_committed")
    B.start_replay(p, wait_ms=300, frames=len(frames))
    p.d(len(frames) * 400 * 7 + 20_000)
    B.read_stats(p, "c.")
    res = owner.execute(p)
    a_sent, b_sent, c_sent = res["a.ord.sent"], res["b.ord.sent"] - res["a.ord.sent"], res["c.ord.sent"] - res["b.ord.sent"]
    rec = {"orders_a": a_sent, "orders_b_uncommitted": b_sent, "orders_c_committed": c_sent, "maxpos_read_back": res["maxpos_held"], "cmd_bit0_staged": res["cmd_pending"] & 1,
           "cmd_bit0_before": res["cmd_a"] & 1, "cmd_bit0_after_commit": res["cmd_committed"] & 1, "rej_pos_b": res["b.itch.rej_pos"] - res["a.itch.rej_pos"],
           "rej_pos_c": res["c.itch.rej_pos"] - res["b.itch.rej_pos"], "sim": "whole core, xsim 2026.1"}
    if os.environ.get("B188_RECORD"):
        Path(os.environ["B188_RECORD"]).mkdir(parents=True, exist_ok=True)
        (Path(os.environ["B188_RECORD"]) / "staged_limits_sim.json").write_text(json.dumps(rec, indent=1))
    assert a_sent == 4, rec
    assert res["maxpos_held"] == 150 and rec["cmd_bit0_before"] == 0 and rec["cmd_bit0_staged"] == 1 and rec["cmd_bit0_after_commit"] == 0, rec
    assert b_sent == 4 and rec["rej_pos_b"] == 0, rec            # the old limit is still in force
    assert c_sent == 1 and rec["rej_pos_c"] == 3, rec            # the committed limit
