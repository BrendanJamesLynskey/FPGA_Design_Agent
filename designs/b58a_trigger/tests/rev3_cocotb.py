"""Final re-review probes: soft reset at every offset around a speculative order from a bad frame, and soft reset held
continuously across the order and its cancel."""
from __future__ import annotations
import os
import cocotb
from cocotb.triggers import RisingEdge
from designs.b58a_trigger.model import benchfeed as bf
from designs.b58a_trigger.model import rules as rl
from designs.b58a_trigger.model.ref_model import Config
from designs.b58a_trigger.tests.b58a_cocotb import Bench, prime, standard_rules
from designs.b58a_trigger.tests.rev_adv_cocotb import orders_since

SPEC = int(os.environ.get("REV_SPEC", "1"))
TRIG = bf.Msg(bf.ADD, bf.ASK, 3, 9950, 1)
FILL = [bf.Msg(bf.ADD, bf.BID, 5, 9000 + k, 1) for k in range(6)]


async def setup(dut):
    b = Bench(dut)
    await b.start()
    await b.config(Config(spec_en=bool(SPEC), bucket=100000, max_pos=10**7),
                   rl.table_words(rl.validate_table(standard_rules())))
    prime(b, None, insts=(3, 5))
    await b.drain(100)
    return b


async def pulse_soft(b, n=1):
    d = b.dut
    d.h_addr.value = 0x003
    d.h_wdata.value = 1 << 7
    d.h_we.value = 1
    for _ in range(n):
        await RisingEdge(d.clk)
    d.h_we.value = 0


def escaped(o):
    cans = {x[2] for x in o if x[1] == bf.CANCEL_ORDER}
    return [x for x in o if x[1] == bf.NEW_ORDER and x[3] and x[2] not in cans]


@cocotb.test()
async def soft_reset_offset_sweep(dut):
    """Bad frame (trigger first, 6 fillers, wrong FCS); soft reset d clocks after the decision (d = 0..140)."""
    b = await setup(dut)
    problems = []
    seq = 1
    for d in range(0, 141, 1):
        c0 = b.cyc
        n0 = len(b.events["px"])
        b.send(bf.with_fcs(bf.feed_frame(seq, [TRIG] + FILL), bad=True), gap=60); seq += 1
        while len(b.events["px"]) == n0:
            await b.idle()
        await b.idle(d)
        await pulse_soft(b)
        await b.drain(300)
        o = orders_since(b, c0)
        if escaped(o):
            problems.append(f"d={d}: escaped {o}")
        v = await b.rd(0x009)
        if v & 1:
            problems.append(f"d={d}: slot not drained (0x009={v:#x})")
        c1 = b.cyc
        b.send(bf.with_fcs(bf.feed_frame(seq, [TRIG])), gap=60); seq += 1
        await b.drain(300)
        if len([x for x in orders_since(b, c1) if x[1] == bf.NEW_ORDER and x[3]]) != 1:
            problems.append(f"d={d}: next good trigger gave no clean order")
    hw = await b.counters()
    dut._log.info(f"counters { {k: v for k, v in hw.items() if v} }")
    assert not problems, "\n".join(problems[:20])


@cocotb.test()
async def soft_reset_held_through_cancel(dut):
    """Speculative only: a long bad frame so the order leaves clean and needs a cancel; soft reset held high every
    clock from the decision until well after the cancel would go."""
    if not SPEC:
        return
    b = await setup(dut)
    fill = [bf.Msg(bf.ADD, bf.BID, 5, 9000 + k, 1) for k in range(40)]
    c0 = b.cyc
    n0 = len(b.events["px"])
    b.send(bf.with_fcs(bf.feed_frame(1, [TRIG] + fill), bad=True), gap=300)
    f0 = len(b.events["first"])
    while len(b.events["first"]) == f0:
        await b.idle()
    await pulse_soft(b, n=1200)
    await b.drain(400)
    o = orders_since(b, c0)
    dut._log.info(f"orders={o}")
    assert any(x[1] == bf.CANCEL_ORDER for x in o), o
    assert not escaped(o), o
