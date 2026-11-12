"""Re-review probes: frame-generation wrap (rq_gen), soft reset with a speculative order on the wire."""
from __future__ import annotations
import os
import cocotb
from designs.b58a_trigger.model import benchfeed as bf
from designs.b58a_trigger.model import rules as rl
from designs.b58a_trigger.model.ref_model import Config
from designs.b58a_trigger.tests.b58a_cocotb import Bench, prime, standard_rules
from designs.b58a_trigger.tests.rev_adv_cocotb import orders_since

SPEC = int(os.environ.get("REV_SPEC", "1"))


@cocotb.test()
async def gen_wrap(dut):
    """A trigger, then N good non-trigger frames, then a trigger: for every N the second must give an order."""
    b = Bench(dut)
    await b.start()
    await b.config(Config(spec_en=bool(SPEC), bucket=10000, max_pos=10**6),
                   rl.table_words(rl.validate_table(standard_rules())))
    prime(b, None, insts=(3, 5))
    await b.drain(100)
    trig = bf.Msg(bf.ADD, bf.ASK, 3, 9950, 1)
    quiet = bf.Msg(bf.ADD, bf.BID, 5, 9000, 1)
    seq = 1
    bad = []
    for n in (253, 254, 255, 256):
        b.send(bf.with_fcs(bf.feed_frame(seq, [trig])), gap=200); seq += 1
        for _ in range(n):
            b.send(bf.with_fcs(bf.feed_frame(seq, [quiet])), gap=12); seq += 1
        await b.drain(300)
        c1 = b.cyc
        b.send(bf.with_fcs(bf.feed_frame(seq, [trig])), gap=200); seq += 1
        await b.drain(300)
        k = len([o for o in orders_since(b, c1) if o[1] == bf.NEW_ORDER])
        dut._log.info(f"N={n}: orders after = {k}")
        if k != 1:
            bad.append((n, k))
    hw = await b.counters()
    dut._log.info(f"counters { {k: v for k, v in hw.items() if v} }")
    assert not bad, bad


@cocotb.test()
async def soft_reset_in_flight(dut):
    """Speculative order on the wire from a frame that will turn out bad; the host pulses soft reset (PULSE[7]) while
    the order is being sent. Is the order still poisoned or cancelled?"""
    b = Bench(dut)
    await b.start()
    await b.config(Config(spec_en=True, bucket=1000, max_pos=10**6),
                   rl.table_words(rl.validate_table(standard_rules())))
    prime(b, None, insts=(3, 5))
    await b.drain(100)
    trig = bf.Msg(bf.ADD, bf.ASK, 3, 9950, 1)
    filler = [bf.Msg(bf.ADD, bf.BID, 5, 9000 + k, 1) for k in range(20)]
    c0 = b.cyc
    n0 = len(b.events["first"])
    b.send(bf.with_fcs(bf.feed_frame(1, [trig] + filler), bad=True), gap=300)
    while len(b.events["first"]) == n0:
        await b.idle()
    await b.wr(0x003, 1 << 7)
    await b.drain(600)
    o = orders_since(b, c0)
    dut._log.info(f"orders={o}")
    cans = {x[2] for x in o if x[1] == bf.CANCEL_ORDER}
    escaped = [x for x in o if x[1] == bf.NEW_ORDER and x[3] and x[2] not in cans]
    assert not escaped, f"escaped after soft reset: {o}"
