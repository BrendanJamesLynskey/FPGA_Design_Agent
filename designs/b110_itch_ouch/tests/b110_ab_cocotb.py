"""cocotb bench of the A/B feed arbiter in front of the parser (rtl/feed_arb.sv, itch_ouch_top DUAL_FEED=1), brief 191.

Both feeds carry the same MoldUDP64 packets; each test builds the two feeds' schedules (a packet's words are presented on the feed's port from a start clock, so
the feeds have skews, jitter and losses of their own) and feeds the model, packet by packet, the single clean stream the parser should see. The checks are the
model's checks of the whole path (messages, events, book updates, order frames, counters, flags) and the arbiter's own counters. Run with PARAMETER DUAL_FEED=1.
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

import cocotb

from b110_cocotb import MID, TK, Bench, Day, compare_all, pk, small_cfg
from designs.b110_itch_ouch.model import gen, proto
from designs.b110_itch_ouch.model.ref import Model

SESSION = b"SESSION001"
CNT_AB = ("fwd_a", "fwd_b", "old_a", "old_b", "gap", "sess", "ovf")


def ab_counters(b: Bench) -> dict:
    v = int(b.dut.cnt_ab.value)
    return {k: (v >> (32 * i)) & 0xFFFFFFFF for i, k in enumerate(CNT_AB)}


class Sched:
    """Per feed: clock offset -> (v, d, sof, eof, keep, err)."""

    def __init__(self) -> None:
        self.w: dict[int, tuple] = {}

    def add(self, start: int, pkt: bytes, err: bool = False) -> int:
        ws = proto.words(pkt)
        for i, (word, keep) in enumerate(ws):
            assert start + i not in self.w, f"two packets of one feed overlap at {start + i}"
            last = i == len(ws) - 1
            self.w[start + i] = (1, word, int(i == 0), int(last), keep if last else 0xFF, int(err and last))
        return start + len(ws) - 1


async def play(b: Bench, sa: Sched, sb: Sched, extra: int = 80) -> int:
    """Present both schedules from the next clock; returns the cycle number of offset 0."""
    d = b.dut
    base = b.cyc
    end = max(max(sa.w, default=0), max(sb.w, default=0)) + extra
    for k in range(end):
        for pre, sc in (("s", sa), ("sb", sb)):
            v, dd, sof, eof, keep, err = sc.w.get(k, (0, 0, 0, 0, 0, 0))
            getattr(d, f"{pre}_v").value = v
            getattr(d, f"{pre}_d").value = dd
            getattr(d, f"{pre}_sof").value = sof
            getattr(d, f"{pre}_eof").value = eof
            getattr(d, f"{pre}_keep").value = keep
            getattr(d, f"{pre}_err").value = err
        await b.tick()
        if int(d.r_v.value):                                                   # the stream the parser sees: remember where packets start and end
            if int(d.r_sof.value):
                if b.last_eof is not None:
                    b.min_gap = min(b.min_gap, b.cyc - b.last_eof - 1)
            if int(d.r_eof.value):
                b.last_eof = b.cyc
    for pre in ("s", "sb"):
        getattr(d, f"{pre}_v").value = 0
        getattr(d, f"{pre}_sof").value = 0
        getattr(d, f"{pre}_eof").value = 0
    return base


async def fresh_ab(dut, cfg=None):
    b = Bench(dut, cfg or small_cfg(), spec=False)
    await b.start()
    b.last_eof, b.min_gap = None, 1 << 30            # idle clocks between packets at the parser's input (smallest seen)
    return b, Model(b.cfg)


def day_packets(d: Day, n: int, r: random.Random) -> list[bytes]:
    """The opening (S, R x n_inst) and n packets of 1 to 3 Add/Delete messages, as bytes; the day's sequence number advances."""
    pkts = []
    c = d.b.cfg
    msgs = [proto.itch_S(0, d.t(), "O")] + [proto.itch_R(d.loc0 + i, d.t(), c.watch[i]) for i in range(c.n_inst)]
    pkts.append(pk(d.seq, msgs))
    d.seq += len(msgs)
    ref = 1
    for k in range(n):
        ms = []
        for j in range(r.randrange(1, 4)):
            ref += 1
            if r.random() < 0.6:
                ms.append(d.A(r.randrange(c.n_inst), ref, r.choice("BS"), 100 + r.randrange(50), MID + r.randrange(-6, 6) * TK))
            else:
                ms.append(proto.itch_D(d.loc0, d.t(), ref - 1))
        pkts.append(pk(d.seq, ms))
        d.seq += len(ms)
    return pkts


async def run_stream(dut, pitch: int, skew, lossA=(), lossB=(), n=40, seed=5, err_idx=(), cfg=None):
    """Packets on both feeds with `skew(i)` = (offset on A, offset on B) from the packet's slot; packets in lossA / lossB are missing on that feed."""
    b, m = await fresh_ab(dut, cfg)
    d = Day(b, m)
    r = random.Random(seed)
    pkts = day_packets(d, n, r)
    sa, sb = Sched(), Sched()
    t = 10
    for i, p in enumerate(pkts):
        oa, ob = skew(i)
        if i not in lossA:
            sa.add(t + oa, p, i in err_idx)
        if i not in lossB:
            sb.add(t + ob, p)
        if i not in lossA or i not in lossB:
            m.feed(p, i in err_idx and i not in lossA)
        t += pitch
    await play(b, sa, sb)
    return b, m, pkts


@cocotb.test()
async def ab_same(dut):
    """Both feeds complete, skews of either sign and jitter: the parser sees each packet once, in order; the model's counters and outputs equal those of a single feed."""
    rows = {}
    for name, skew in (("zero", lambda i: (0, 0)), ("b_late_3", lambda i: (0, 3)), ("b_early_3", lambda i: (3, 0)), ("b_late_20", lambda i: (0, 20)),
                       ("jitter", lambda i: ((i * 7) % 6, (i * 5 + 3) % 9))):
        b, m, pkts = await run_stream(dut, 40, skew, n=30)
        compare_all(b, m)
        c = ab_counters(b)
        assert c["fwd_a"] + c["fwd_b"] == len(pkts) and c["old_a"] + c["old_b"] == len(pkts) and c["gap"] == 0 and c["sess"] == 0 and c["ovf"] == 0, (name, c)
        assert b.counters()["gap"] == 0 and b.counters()["dup"] == 0
        rows[name] = c
    dut._log.info("ab_same: %s", json.dumps(rows))


@cocotb.test()
async def ab_loss(dut):
    """One feed drops packets (not the same packet on both): the other feed's copy fills each gap and the parser sees no gap."""
    r = random.Random(11)
    for name, skew in (("b_late_5", lambda i: (0, 5)), ("a_late_5", lambda i: (5, 0))):
        lossA = {i for i in range(1, 40) if r.random() < 0.2}
        lossB = {i for i in range(1, 40) if r.random() < 0.2 and i not in lossA}
        b, m, pkts = await run_stream(dut, 40, skew, lossA, lossB, n=38, seed=r.randrange(1000))
        compare_all(b, m)
        c = ab_counters(b)
        assert b.counters()["gap"] == 0 and c["gap"] == 0, (name, c, b.counters()["gap"])
        assert c["fwd_a"] + c["fwd_b"] == len(pkts), c
        dut._log.info("ab_loss %s: lost A %d, lost B %d, %s", name, len(lossA), len(lossB), c)
        assert (c["fwd_b"] > 0) if name == "b_late_5" else (c["fwd_a"] > 0)


@cocotb.test()
async def ab_both_lost(dut):
    """A packet missing on both feeds is a real gap: the arbiter passes the next packet on, counts `gap`, and the parser counts the gap and halts trading as before."""
    skew = lambda i: (0, 4)       # noqa: E731
    b, m, pkts = await run_stream(dut, 40, skew, lossA={5, 12}, lossB={5})
    compare_all(b, m)
    c = ab_counters(b)
    assert c["gap"] == 1 and b.counters()["gap"] == 1 and c["fwd_a"] + c["fwd_b"] == len(pkts) - 1, (c, b.counters()["gap"])


@cocotb.test()
async def fill_window(dut):
    """Where the fill ends: packet 6 is lost on A and B's copy starts `skew` clocks after A's slot; A's next packet starts `pitch` clocks after. The gap is filled when B's
    third word is in before A's next packet's third word, that is for skew < pitch, and not for skew >= pitch (A is judged first on a tie)."""
    pitch = 40
    res = {}
    for skew in (0, 10, 20, 38, 39, 40, 41, 60):
        b, m, pkts = await run_stream(dut, pitch, lambda i, s=skew: (0, s if i == 6 else 0), lossA={6}, lossB={7, 8}, n=12)
        filled = b.counters()["gap"] == 0
        res[skew] = filled
        assert filled == (skew < pitch), f"skew {skew}: filled {filled}"
        if filled:
            compare_all(b, m)
    rec = os.environ.get("B110_RECORD")
    if rec:
        Path(rec).mkdir(parents=True, exist_ok=True)
        (Path(rec) / "feed_arb_fill_window.json").write_text(json.dumps({"pitch_clocks": pitch, "skew_of_B_copy_clocks": list(res), "gap_filled": {str(k): v for k, v in res.items()},
                                                                         "rule": "filled iff skew < pitch: the other feed's third word must be in before the first feed's next packet's third word"}, indent=2) + "\n")


@cocotb.test()
async def ab_heartbeats(dut):
    """The same heartbeat on both feeds reaches the parser once; heartbeats of one feed far apart (more than HB_WIN clocks) all pass; an end of session likewise."""
    b, m = await fresh_ab(dut)
    d = Day(b, m)
    sa, sb = Sched(), Sched()
    c = b.cfg
    p0 = pk(d.seq, [proto.itch_S(0, d.t(), "O")] + [proto.itch_R(d.loc0 + i, d.t(), c.watch[i]) for i in range(c.n_inst)])
    d.seq += 1 + c.n_inst
    sa.add(10, p0); sb.add(14, p0); m.feed(p0)
    hb1 = proto.heartbeat(SESSION, d.seq)
    sa.add(80, hb1); sb.add(83, hb1); m.feed(hb1)                                # one heartbeat on both feeds: reaches the parser once
    sa.add(150, hb1)                                                             # the same heartbeat again on A, 70 clocks later: inside HB_WIN, taken as a copy and dropped
    p1 = pk(d.seq, [d.A(0, 7, "B", 100, MID - 100)]); d.seq += 1
    sa.add(220, p1); sb.add(224, p1); m.feed(p1)
    hb2 = proto.heartbeat(SESSION, d.seq)
    sa.add(300, hb2); m.feed(hb2)                                                # a heartbeat on one feed only: forwarded
    sa.add(5000, hb2); sb.add(4996, hb2); m.feed(hb2)                            # the same number once more, 4700 clocks later (more than HB_WIN), B first: a new heartbeat, once
    eos = proto.end_of_session(SESSION, d.seq)
    sa.add(5200, eos); sb.add(5203, eos); m.feed(eos)                            # an end of session with the number of the heartbeat before it: a different kind, forwarded
    await play(b, sa, sb)
    compare_all(b, m)
    cc = b.counters()
    assert cc["hb"] == 3 and cc["eos"] == 1, cc
    assert ab_counters(b)["old_a"] >= 1 and ab_counters(b)["fwd_a"] + ab_counters(b)["fwd_b"] == 6, ab_counters(b)


@cocotb.test()
async def ab_error_frame(dut):
    """The first copy ends with a bad frame check: it is forwarded and flagged exactly as without the arbiter (the parser's `pkt_err` and `untrusted`); B's good copy is dropped as old."""
    skew = lambda i: (0, 3)        # noqa: E731
    b, m, pkts = await run_stream(dut, 40, skew, n=10, err_idx={4})
    compare_all(b, m)
    assert b.counters()["pkt_err"] == 1 and int(b.dut.flags.value) & 2
    assert ab_counters(b)["old_b"] >= 1


@cocotb.test()
async def ab_session_overlap(dut):
    """A packet of another session is passed on (counted `sess`, dropped by the parser as without the arbiter); a packet that overlaps the forwarded range is forwarded and trimmed by the parser."""
    b, m = await fresh_ab(dut)
    d = Day(b, m)
    c = b.cfg
    sa, sb = Sched(), Sched()
    p0 = pk(d.seq, [proto.itch_S(0, d.t(), "O")] + [proto.itch_R(d.loc0 + i, d.t(), c.watch[i]) for i in range(c.n_inst)])
    s0 = d.seq
    d.seq += 1 + c.n_inst
    sa.add(10, p0); sb.add(12, p0); m.feed(p0)
    other = pk(d.seq, [d.A(0, 3, "B", 100, MID - 100)], b"OTHERSESS1")
    sa.add(80, other); sb.add(82, other); m.feed(other); m.feed(other)           # both feeds: forwarded twice (the arbiter does not dedupe another session), dropped twice by the parser
    ma = [d.A(0, 4, "B", 100, MID - 100), d.A(0, 5, "S", 100, MID + 100)]
    pa = pk(d.seq, ma)
    sa.add(150, pa); m.feed(pa)
    mb = ma + [d.A(0, 6, "S", 100, MID + 200)]                                   # B's copy carries one more message: seq range overlaps A's
    pb = pk(d.seq, mb)
    sb.add(190, pb); m.feed(pb)
    d.seq += 3
    del s0
    await play(b, sa, sb)
    compare_all(b, m)
    cc = ab_counters(b)
    assert cc["sess"] == 2 and b.counters()["sess"] == 2 and b.counters()["ovlp"] == 2, (cc, b.counters())


@cocotb.test()
async def ab_burst(dut):
    """Packets of 8 words back to back on each feed (4 idle clocks, the smallest gap), the B copy ahead of the A copy by 0, 6, 12, 24 or 36 clocks (up to three packets: the later
    packets wait in A's FIFO behind the copy being forwarded) and then A ahead: the parser sees one clean stream (4 idle clocks between packets) equal to the model's."""
    for lag in (0, 6, 12, 24, 36, -12, -36):
        b, m = await fresh_ab(dut)
        d = Day(b, m)
        c = b.cfg
        sa, sb = Sched(), Sched()
        p0 = pk(d.seq, [proto.itch_S(0, d.t(), "O")] + [proto.itch_R(d.loc0 + i, d.t(), c.watch[i]) for i in range(c.n_inst)])
        d.seq += 1 + c.n_inst
        sa.add(10, p0); sb.add(10, p0); m.feed(p0)
        pitch = 8 + 4
        for i in range(30):
            p = pk(d.seq, [d.A(i % 2, 100 + i, "B" if i % 3 else "S", 100, MID + (i % 5 - 2) * TK)])
            assert len(proto.words(p)) == 8
            d.seq += 1
            t = 200 + pitch * i
            sb.add(t + max(lag, 0), p)
            sa.add(t + max(-lag, 0), p)
            m.feed(p)
        await play(b, sa, sb, extra=200)
        compare_all(b, m)
        cc = ab_counters(b)
        assert cc["ovf"] == 0 and b.counters()["gap"] == 0 and b.counters()["dup"] == 0, (lag, cc, b.counters())
        assert cc["fwd_a"] + cc["fwd_b"] == 31 and cc["old_a"] + cc["old_b"] == 31, (lag, cc)


@cocotb.test()
async def ab_interleave(dut):
    """Each feed carries every other packet (the other feed lost the rest): packets from the two feeds can start at the very clock after the other feed's previous packet ended (gap 0 to 5 clocks
    between them at the arbiter's inputs, where the parser needs 4 idle clocks): the arbiter inserts the idle clocks, and the parser sees the clean sequence of the model."""
    for g in range(6):
        b, m = await fresh_ab(dut)
        d = Day(b, m)
        c = b.cfg
        sa, sb = Sched(), Sched()
        p0 = pk(d.seq, [proto.itch_S(0, d.t(), "O")] + [proto.itch_R(d.loc0 + i, d.t(), c.watch[i]) for i in range(c.n_inst)])
        d.seq += 1 + c.n_inst
        sa.add(10, p0); sb.add(10, p0); m.feed(p0)
        t = 200
        for i in range(20):
            p = pk(d.seq, [d.A(i % 2, 100 + i, "B" if i % 3 else "S", 100, MID + (i % 5 - 2) * TK)])
            assert len(proto.words(p)) == 8
            d.seq += 1
            (sa if i % 2 == 0 else sb).add(t, p)
            m.feed(p)
            t += 8 + g if i % 2 == 0 else 8 + 12
        await play(b, sa, sb, extra=200)
        compare_all(b, m)
        cc = ab_counters(b)
        assert cc["gap"] == 0 and b.counters()["gap"] == 0 and b.counters()["dup"] == 0 and cc["ovf"] == 0, (g, cc)
        assert b.min_gap >= 4, f"packets reach the parser {b.min_gap} idle clocks apart (it needs 4)"


@cocotb.test()
async def ab_runts(dut):
    """Runt packets (they end before their third word: no sequence number to judge) are forwarded unchanged from each feed that has them, and counted by the parser as short."""
    b, m = await fresh_ab(dut)
    d = Day(b, m)
    c = b.cfg
    sa, sb = Sched(), Sched()
    p0 = pk(d.seq, [proto.itch_S(0, d.t(), "O")] + [proto.itch_R(d.loc0 + i, d.t(), c.watch[i]) for i in range(c.n_inst)])
    d.seq += 1 + c.n_inst
    sa.add(10, p0); sb.add(12, p0); m.feed(p0)
    for k, n in enumerate((5, 8, 15, 16, 20)):                                   # 1, 2 and 3 word runts (and a packet with a 4-byte third word)
        r = (b"\x11\x22\x33\x44\x55\x66\x77\x88" * 3)[:n]
        sa.add(60 + 30 * k, r); sb.add(63 + 30 * k, r); m.feed(r); m.feed(r)
    p1 = pk(d.seq, [d.A(0, 9, "B", 100, MID - 100)]); d.seq += 1
    sa.add(300, p1); sb.add(303, p1); m.feed(p1)
    await play(b, sa, sb)
    dut._log.info("runts: arb %s parser %s", ab_counters(b), {k: v for k, v in b.counters().items() if v and k in ("pkt", "msg", "short", "sess", "trunc", "badlen", "pkt_err")})
    compare_all(b, m)
    assert b.counters()["short"] == 8 and ab_counters(b)["sess"] == 2, (b.counters(), ab_counters(b))      # 1 and 2 word runts, from both feeds; the 20 byte one is another session


@cocotb.test()
async def ab_deep_skew(dut):
    """B lost packet n; A's copy of n is a long packet being forwarded while B's next packet (a real, new one) has its header in: B's packet waits in its FIFO for the whole of A's. With a FIFO
    that holds the skew (ARB_AW 8) the stream is clean and equals the model; with the default 2^5 words the words that do not fit are dropped, `ovf` counts them and the packet's last word
    carries s_err, so the parser marks the path untrusted (it never passes a corrupt packet as good)."""
    aw = int(os.environ.get("B110_ARB_AW", "5"))
    b, m = await fresh_ab(dut)
    d = Day(b, m)
    c = b.cfg
    sa, sb = Sched(), Sched()
    p0 = pk(d.seq, [proto.itch_S(0, d.t(), "O")] + [proto.itch_R(d.loc0 + i, d.t(), c.watch[i]) for i in range(c.n_inst)])
    d.seq += 1 + c.n_inst
    sa.add(10, p0); sb.add(10, p0); m.feed(p0)
    big = pk(d.seq, [d.A(0, 100 + k, "B" if k % 2 else "S", 100, MID - 1000 - 10 * k) for k in range(24)])      # 20 + 24 x 38 = 932 bytes: 117 words
    d.seq += 24
    nxt = pk(d.seq, [d.A(0, 200 + k, "B", 100, MID - 5000 - 10 * k) for k in range(10)])                         # 20 + 10 x 38 = 400 bytes: 50 words
    d.seq += 10
    sa.add(200, big); m.feed(big)                                                # A only: B lost it
    sb.add(240, nxt)                                                             # B's next packet starts while A's is still being forwarded
    sa.add(200 + 117 + 4 + 40, nxt)                                              # A's copy comes after (old by then if the first was forwarded)
    m.feed(nxt, err=(aw == 5))
    await play(b, sa, sb, extra=400)
    cc = ab_counters(b)
    if aw >= 8:
        compare_all(b, m)
        assert cc["ovf"] == 0 and b.counters()["pkt_err"] == 0, cc
    else:
        assert cc["ovf"] > 0 and b.counters()["pkt_err"] == 1 and int(b.dut.flags.value) & 2, (cc, b.counters())
    rec = os.environ.get("B110_RECORD")
    if rec:
        Path(rec).mkdir(parents=True, exist_ok=True)
        (Path(rec) / f"feed_arb_deep_skew_aw{aw}.json").write_text(json.dumps({"arb_aw": aw, "fifo_words": 1 << aw, "ab_counters": cc, "parser_pkt_err": b.counters()["pkt_err"],
                                                                                "untrusted": bool(int(b.dut.flags.value) & 2)}, indent=2) + "\n")


@cocotb.test()
async def ab_random(dut):
    """Seeded random sessions from the generator: random skews of either sign and random single-feed losses; the single clean stream equals the model's."""
    for seed in (1, 2, 3):
        r = random.Random(seed)
        cfg = small_cfg()
        b, m = await fresh_ab(dut, cfg)
        g = gen.Gen(seed, cfg)
        items = g.stream(150, p_hb=0.03)
        sa, sb = Sched(), Sched()
        t = 10
        lost = 0
        for it in items:
            n = len(proto.words(it.pkt))
            oa, ob = r.randrange(0, 8), r.randrange(0, 8)
            lose = r.random()
            if lose < 0.08:
                sa_on, sb_on = False, True
                lost += 1
            elif lose < 0.16:
                sa_on, sb_on = True, False
                lost += 1
            else:
                sa_on, sb_on = True, True
            if sa_on:
                sa.add(t + oa, it.pkt, it.err)
            if sb_on:
                sb.add(t + ob, it.pkt)
            m.feed(it.pkt, it.err and sa_on)
            t += n + 8 + 8 + 4
        await play(b, sa, sb, extra=200)
        compare_all(b, m, allow_dropped=False)
        c = ab_counters(b)
        dut._log.info("ab_random seed %d: lost on one feed %d, counters %s, parser gaps %d", seed, lost, c, b.counters()["gap"])
        assert c["ovf"] == 0


@cocotb.test()
async def ab_latency(dut):
    """Latency in clocks from the clock the last byte of a candidate is presented (T) on either feed (the other idle) to the book update, against the single feed's 7: the arbiter adds a fixed number of clocks."""
    out = {}
    for feed in ("a", "b"):
        b, m = await fresh_ab(dut)
        d = Day(b, m)
        c = b.cfg
        sa, sb = Sched(), Sched()
        sch = sa if feed == "a" else sb
        p0 = pk(d.seq, [proto.itch_S(0, d.t(), "O")] + [proto.itch_R(d.loc0 + i, d.t(), c.watch[i]) for i in range(c.n_inst)])
        d.seq += 1 + c.n_inst
        p1 = pk(d.seq, [d.A(0, 1, "B", 100, MID - 100)])
        d.seq += 1
        p2 = pk(d.seq, [d.A(0, 2, "S", 100, MID + 100)])
        sch.add(10, p0); sch.add(80, p1)
        T = sch.add(160, p2)
        for p in (p0, p1, p2):
            m.feed(p)
        base = await play(b, sa, sb)
        compare_all(b, m)
        tu = b.tus[-1]["cyc"]
        out[feed] = {"book_update_clocks_after_last_byte": tu - (base + T), "first_order_word_clocks_after_last_byte": b.frames[0]["cyc"] - (base + T)}
        assert out[feed]["book_update_clocks_after_last_byte"] == 7 + 4, out
    rec = os.environ.get("B110_RECORD")
    if rec:
        Path(rec).mkdir(parents=True, exist_ok=True)
        (Path(rec) / "feed_arb_latency.json").write_text(json.dumps({"unit": "clocks from the clock the last byte of the message is presented (T)", "single_feed_book_update": 7,
                                                                      "single_feed_first_order_word": 8, **out}, indent=2) + "\n")
