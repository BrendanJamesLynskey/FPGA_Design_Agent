"""Reviewer's adversarial tests (not part of the PR): a bad trigger frame whose verdict arrives within a few clocks of
the decision (frame truncated just after the price field), speculative and safe mode."""
from __future__ import annotations

import os

import cocotb

from designs.b58a_trigger.model import benchfeed as bf
from designs.b58a_trigger.model import rules as rl
from designs.b58a_trigger.model.ref_model import Config
from designs.b58a_trigger.tests.b58a_cocotb import Bench, standard_rules

SPEC = int(os.environ.get("REV_SPEC", "1"))


def orders_since(b: Bench, c0: int):
    out = []
    for c, f, ok in b.a_frames():
        if c < c0 or f[12:14] != b"\x08\x00":
            continue
        o = bf.parse_order(f)
        out.append((c, o.type, o.order_id, ok))
    return out


@cocotb.test()
async def truncated_trigger_sweep(dut):
    b = Bench(dut)
    await b.start()
    cfg = Config(spec_en=bool(SPEC), bucket=1000, max_pos=100000)
    table = rl.table_words(rl.validate_table(standard_rules()))
    await b.config(cfg, table)
    trig = bf.Msg(bf.ADD, bf.ASK, 3, 9950, 10)
    quiet = bf.Msg(bf.ADD, bf.BID, 5, 9000, 1)
    seq = 1
    problems = []
    for k in range(0, 10):
        c0 = b.cyc
        full = bf.feed_frame(seq, [trig])
        cut = full[:58 + k]                                  # b=57 is the last price byte
        bad = cut                                            # ends k bytes after the price field; FCS wrong
        b.send(bad, gap=12)                                  # minimum-ish IFG
        b.send(bf.with_fcs(bf.feed_frame(seq + 1, [quiet])), gap=300)   # good, no trigger
        await b.drain(300)
        bad_orders = orders_since(b, c0)
        news = [o for o in bad_orders if o[1] == bf.NEW_ORDER]
        cans = {o[2] for o in bad_orders if o[1] == bf.CANCEL_ORDER}
        for c, t, oid, ok in news:
            if ok and oid not in cans:
                problems.append(f"k={k}: order {oid} from a bad frame left with a good FCS and no cancel")
        # the slot must still work: a good trigger frame gives one clean order
        c1 = b.cyc
        b.send(bf.with_fcs(bf.feed_frame(seq + 2, [trig])), gap=300)
        await b.drain(300)
        good = [o for o in orders_since(b, c1) if o[1] == bf.NEW_ORDER and o[3]]
        if len(good) != 1:
            problems.append(f"k={k}: good trigger after it gave {len(good)} clean orders (slot hung?)")
        dut._log.info(f"k={k} len={len(bad)} bad-frame orders={news} cancels={sorted(cans)} next-good={len(good)}")
        seq += 3
    hw = await b.counters()
    dut._log.info(f"counters { {k: v for k, v in hw.items() if v} }")
    assert not problems, "\n".join(problems)


@cocotb.test()
async def non_runt_second_message(dut):
    """Message 1 does not trigger, message 2 does; the frame (>= 64 bytes, so not a runt) ends 0..2 bytes after
    message 2's price field with a wrong FCS."""
    b = Bench(dut)
    await b.start()
    cfg = Config(spec_en=bool(SPEC), bucket=1000, max_pos=100000)
    await b.config(cfg, rl.table_words(rl.validate_table(standard_rules())))
    trig = bf.Msg(bf.ADD, bf.ASK, 3, 9950, 10)
    quiet = bf.Msg(bf.ADD, bf.BID, 5, 9000, 1)
    problems = []
    for k in range(0, 3):
        c0 = b.cyc
        f = bf.feed_frame(1 + 3 * k, [quiet, trig])[:74 + k]
        b.send(f, gap=12)
        b.send(bf.with_fcs(bf.feed_frame(2 + 3 * k, [quiet])), gap=300)
        await b.drain(300)
        o = orders_since(b, c0)
        cans = {x[2] for x in o if x[1] == bf.CANCEL_ORDER}
        bad = [x for x in o if x[1] == bf.NEW_ORDER and x[3] and x[2] not in cans]
        dut._log.info(f"k={k} len={len(f)} orders={o}")
        if bad:
            problems.append(f"k={k} len={len(f)}: {bad}")
    assert not problems, problems


@cocotb.test()
async def good_frames_after_arp(dut):
    """All frames good: an ARP request keeps the transmit MAC busy; a trigger frame follows after a gap g, so its
    order waits (queued) for the MAC. Sweep g; after each pair a further trigger must still produce an order."""
    b = Bench(dut)
    await b.start()
    cfg = Config(spec_en=bool(SPEC), bucket=100000, max_pos=10**7)
    await b.config(cfg, rl.table_words(rl.validate_table(standard_rules())))
    trig = bf.Msg(bf.ADD, bf.ASK, 3, 9950, 1)
    problems = []
    seq = 1
    for g in range(0, 14):
        b.send(bf.with_fcs(bf.arp_request(bf.VENUE_MAC, bf.VENUE_IP, bf.BOARD_IP)), gap=g)
        b.send(bf.with_fcs(bf.feed_frame(seq, [trig])), gap=400)
        await b.drain(200)
        c1 = b.cyc
        b.send(bf.with_fcs(bf.feed_frame(seq + 1, [trig])), gap=400)
        await b.drain(200)
        n = [o for o in orders_since(b, c1) if o[1] == bf.NEW_ORDER]
        if len(n) != 1:
            problems.append(f"g={g}: follow-up trigger gave {len(n)} orders (slot hung?)")
            break
        seq += 2
    hw = await b.counters()
    dut._log.info(f"counters { {k: v for k, v in hw.items() if v} }")
    assert not problems, problems
