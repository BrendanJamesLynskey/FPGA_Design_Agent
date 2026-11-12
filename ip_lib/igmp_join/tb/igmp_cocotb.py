"""cocotb bench for ip_lib/igmp_join against RFC 2236 as written in ip_lib/igmp_join/model.py, with scapy decoding
every frame sent (test time only). Directed sequence with short ticks: joins (report now, one repeat), general,
group-specific and version 3 queries (a report within the Max Response Time), the timer-restart rule, suppression by
another host's report, a query with a bad checksum ignored, leaves (only after being the last reporter). Every frame
is compared byte for byte with the model's frame. Environment: IGMP_SEED."""
from __future__ import annotations

import os
import random

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge
from cocotb.utils import get_sim_time

from flow.net import inet
from flow.net.tests import axis_tb
from ip_lib.igmp_join import model

SEED = int(os.environ.get("IGMP_SEED", "1"))
OWN_MAC = inet.mac_b("02:00:00:00:00:01")
OWN_IP = inet.ip_b("192.168.10.2")
ROUTER = (inet.mac_b("02:ee:00:00:00:01"), inet.ip_b("192.168.10.1"))
OTHER = (inet.mac_b("02:ee:00:00:00:07"), inet.ip_b("192.168.10.7"))
try:
    from scapy.contrib.igmp import IGMP
    from scapy.layers.l2 import Ether
    HAVE_SCAPY = True
except ImportError:
    HAVE_SCAPY = False


@cocotb.test()
async def igmp(dut):
    ng, tick, unsol = int(dut.N_GROUPS.value), int(dut.TICK_CLKS.value), int(dut.UNSOL_TICKS.value)
    rng = random.Random(SEED + ng)
    groups = [inet.ip_b(f"239.{1 + i}.{rng.randrange(256)}.{rng.randrange(1, 255)}") for i in range(ng)]
    dut.own_mac.value = int.from_bytes(OWN_MAC, "big")
    dut.own_ip.value = int.from_bytes(OWN_IP, "big")
    dut.groups.value = sum(int.from_bytes(g, "big") << (32 * i) for i, g in enumerate(groups))
    dut.group_en.value = 0
    await axis_tb.start(dut)
    src = axis_tb.Source(dut, rng, gap=0.1)
    sink = axis_tb.Sink(dut, rng, ready=0.8)
    log = []                                             # (time in clocks, type, group) per frame sent
    n_supp = [0]

    def now():
        return int(get_sim_time("ns")) // 8

    async def mon():
        seen = 0
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            n_supp[0] += int(dut.ev_suppressed.value)
            while len(sink.frames) > seen:
                fr = sink.frames[seen][0]
                d = model.parse_host_frame(fr)
                assert d["ident"] == seen, (d["ident"], seen)
                assert fr == model.host_frame(OWN_MAC, OWN_IP, d["group"], d["type"] == 0x17, seen), fr.hex()
                if HAVE_SCAPY:
                    p = Ether(fr)
                    assert IGMP in p and p[IGMP].type == d["type"]
                log.append((now(), d["type"], d["group"]))
                seen += 1
    cocotb.start_soon(mon())

    def frames_since(t0, typ=None):
        return [x for x in log if x[0] >= t0 and (typ is None or x[1] == typ)]

    async def ticks(n):
        await axis_tb.clocks(dut, n * tick + 200)

    g0, g1 = groups[0], groups[min(1, ng - 1)]
    en = 0

    # 1. joins: a report at once, and one repeat within UNSOL_TICKS
    t0 = now()
    en = (1 << ng) - 1
    dut.group_en.value = en
    await ticks(unsol + 2)
    reps = frames_since(t0, 0x16)
    for g in groups:
        times = [t for t, _, gg in reps if gg == g]
        assert len(times) == 2, (g.hex(), times)
        assert times[0] - t0 < 100 * ng and times[1] - t0 <= unsol * tick + 100 * ng + 100, (times, t0)
    dut._log.info(f"joins: {len(reps)} reports for {ng} groups")

    # 2. a general query, then a version 3 query: every member group reports within the Max Response Time
    for v3 in (False, True):
        mrt = 5
        t0 = now()
        await src.send(model.query(*ROUTER, b"\x00" * 4, mrt, v3=v3))
        await ticks(mrt + 2)
        reps = frames_since(t0, 0x16)
        assert sorted(g for _, _, g in reps) == sorted(groups), (v3, reps)
        assert all(t - t0 <= mrt * tick + 100 * ng + 200 for t, _, _ in reps), (reps, t0)

    # 3. a group-specific query: that group only
    t0 = now()
    await src.send(model.query(*ROUTER, g1, 4))
    await ticks(6)
    assert [g for _, _, g in frames_since(t0)] == [g1]

    # 4. a running timer is restarted only by a shorter Max Response Time
    t0 = now()
    await src.send(model.query(*ROUTER, g0, 200))
    await axis_tb.clocks(dut, 2 * tick)
    t1 = now()
    await src.send(model.query(*ROUTER, g0, 3))
    await ticks(5)
    reps = frames_since(t0)
    assert len(reps) == 1 and reps[0][2] == g0 and reps[0][0] - t1 <= 3 * tick + 300, (reps, t1)

    # 5. a query with a bad IGMP checksum is ignored
    q = bytearray(model.query(*ROUTER, b"\x00" * 4, 2))
    q[40] ^= 0xFF
    t0 = now()
    await src.send(bytes(q))
    await ticks(4)
    assert not frames_since(t0)

    # 6. suppression: another host reports group 0 while our timer runs; group 0 is not reported by us
    t0 = now()
    s0 = n_supp[0]
    await src.send(model.query(*ROUTER, b"\x00" * 4, 100))
    await axis_tb.clocks(dut, 30)
    await src.send(model.other_report(*OTHER, g0))
    await ticks(102)
    reps = frames_since(t0, 0x16)
    assert sorted(g for _, _, g in reps) == sorted(groups[1:]), reps
    assert n_supp[0] - s0 == 1

    # 7. leaves: group 0 (another host reported last) sends none; the others do, to 224.0.0.2
    t0 = now()
    dut.group_en.value = 0
    await axis_tb.clocks(dut, 100 * ng + 200)
    lv = frames_since(t0)
    assert all(t == 0x17 for _, t, _ in lv) and sorted(g for _, _, g in lv) == sorted(groups[1:]), lv
    sink.stop()
    dut._log.info(f"igmp: {len(log)} frames sent, all checked against the model")
