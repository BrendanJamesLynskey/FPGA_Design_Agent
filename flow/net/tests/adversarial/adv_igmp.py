"""Independent review: igmp_join reports and leaves against scapy-built frames, and report timing in ticks (RFC 2236)."""
import random
import cocotb
from cocotb.triggers import RisingEdge, ReadOnly
from scapy.all import Ether, IP, Raw, IPOption_Router_Alert
from scapy.contrib.igmp import IGMP
from flow.net.tests import axis_tb

OWN_MAC, OWN_IP = "02:00:00:00:00:01", "192.168.10.2"
G0, G1 = "239.63.0.1", "239.1.200.3"
TICK = 4


def ip2i(s):
    return int.from_bytes(bytes(int(x) for x in s.split(".")), "big")


def mmac(ip):
    b = [int(x) for x in ip.split(".")]
    return "01:00:5e:%02x:%02x:%02x" % (b[1] & 0x7F, b[2], b[3])


FRAME_CLKS = 46          # a report or leave is 46 bytes, one a clock: the repeat's delay counts from its end


def host(typ, grp, ident):
    """scapy's IGMP layer sets TOS 0xC0 unless told otherwise; RFC 2236 asks nothing of TOS and the block sends 0."""
    dst = "224.0.0.2" if typ == 0x17 else grp
    return bytes(Ether(dst=mmac(dst), src=OWN_MAC) / IP(src=OWN_IP, dst=dst, ttl=1, id=ident, tos=0, options=[IPOption_Router_Alert()]) /
                 IGMP(type=typ, mrcode=0, gaddr=grp))


def query(grp, mrt):
    dst = "224.0.0.1" if grp == "0.0.0.0" else grp
    return bytes(Ether(dst=mmac(dst), src="02:bb:00:00:00:01") / IP(src="192.168.10.1", dst=dst, ttl=1, options=[IPOption_Router_Alert()]) /
                 IGMP(type=0x11, mrcode=mrt, gaddr=grp)).ljust(60, b"\x00")


@cocotb.test()
async def timing(dut):
    dut.own_mac.value = 0x020000000001
    dut.own_ip.value = ip2i(OWN_IP)
    dut.groups.value = (ip2i(G1) << 32) | ip2i(G0)
    dut.group_en.value = 0
    await axis_tb.start(dut)
    t = {"n": 0}
    times = []
    sink = axis_tb.Sink(dut, random.Random(2), ready=1.0)
    src = axis_tb.Source(dut, random.Random(1))

    async def clock():
        while True:
            await RisingEdge(dut.clk)
            t["n"] += 1
    cocotb.start_soon(clock())

    async def watch():
        k = 0
        while True:
            await RisingEdge(dut.clk)
            if len(sink.frames) > k:
                times.append(t["n"]); k = len(sink.frames)
    cocotb.start_soon(watch())
    res = []
    # join G0: one report now, one more within UNSOL_TICKS ticks
    t0 = t["n"]; dut.group_en.value = 1
    await axis_tb.clocks(dut, TICK * 12 + 200)
    fr = [f for f, _ in sink.frames]
    res.append(("join: two reports", len(fr) == 2, len(fr)))
    res.append(("report bytes == scapy", fr and fr[0] == host(0x16, G0, 0), fr[0].hex() if fr else None))
    if len(times) == 2:
        dt = (times[1] - times[0] - FRAME_CLKS) / TICK      # times are frame ends
        res.append(("unsolicited repeat within 1..10 ticks", 0.5 <= dt <= 10 + 1, dt))
    # general query, max response 20 ticks: one report within 20 ticks
    n0 = len(sink.frames); tq = t["n"]
    await src.send(query("0.0.0.0", 20))
    tq_end = t["n"]
    await axis_tb.clocks(dut, TICK * 25 + 200)
    got = sink.frames[n0:]
    dt = (times[n0] - tq_end) / TICK if len(times) > n0 else None
    res.append(("general query mrt 20: one report within 20 ticks", len(got) == 1 and dt is not None and dt <= 20 + 1, (len(got), dt)))
    if got:
        res.append(("query report bytes == scapy", got[0][0] == host(0x16, G0, n0), got[0][0].hex()))   # IP ID counts frames sent
    # v1 query (mrt 0): within 100 ticks, not before 1
    n0 = len(sink.frames)
    await src.send(query("0.0.0.0", 0))
    tq_end = t["n"]
    await axis_tb.clocks(dut, TICK * 105 + 200)
    dt = (times[n0] - tq_end) / TICK if len(times) > n0 else None
    res.append(("v1 query: report within 100 ticks", len(sink.frames) == n0 + 1 and dt is not None and dt <= 101, dt))
    # group-specific query for a group we are not in: nothing
    n0 = len(sink.frames)
    await src.send(query(G1, 10))
    await axis_tb.clocks(dut, TICK * 15 + 100)
    res.append(("query for G1 (not joined): nothing", len(sink.frames) == n0, len(sink.frames) - n0))
    # leave G0: we sent the last report, so a leave to 224.0.0.2
    n0 = len(sink.frames)
    dut.group_en.value = 0
    await axis_tb.clocks(dut, 200)
    got = sink.frames[n0:]
    res.append(("leave bytes == scapy", len(got) == 1 and got[0][0] == host(0x17, G0, n0), got[0][0].hex() if got else None))
    for r in res:
        dut._log.info(f"ADV {r[0]}: {'PASS' if r[1] else 'FAIL'} {r[2]}")
    assert all(r[1] for r in res), [r[0] for r in res if not r[1]]
