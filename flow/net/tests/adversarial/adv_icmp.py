"""Independent review's adversarial ICMP echo checks: expected replies built by scapy, not the repo models."""
import random
import cocotb
from cocotb.triggers import RisingEdge, Timer, ReadOnly
from scapy.all import Ether, IP, ICMP, Raw, ARP
from flow.net.tests import axis_tb

OWN_MAC, OWN_IP = "02:00:00:00:00:01", "192.168.10.2"
PC_MAC, PC_IP = "02:aa:00:00:00:09", "192.168.10.9"


def req(data, opts=None, flags=0, frag=0, badcs=False, ident=7, seq=3):
    ip = IP(src=PC_IP, dst=OWN_IP, ttl=17, id=0x1234, flags=flags, frag=frag)
    if opts is not None:
        ip.options = opts
    p = Ether(src=PC_MAC, dst=OWN_MAC) / ip / ICMP(type=8, id=ident, seq=seq) / Raw(data)
    b = bytearray(bytes(p))
    if badcs:
        ihl = (b[14] & 0xF) * 4
        b[14 + ihl + 2] ^= 0x01
    return bytes(b)


def expect_reply(frame):
    p = Ether(frame)
    ip, ic = p[IP], p[ICMP]
    data = bytes(ic.payload)
    r = Ether(src=OWN_MAC, dst=p.src) / IP(src=ip.dst, dst=ip.src, ttl=64, id=ip.id, flags=ip.flags, tos=ip.tos) / \
        ICMP(type=0, id=ic.id, seq=ic.seq) / Raw(data)
    return bytes(r)


async def run_case(dut, frames, gap_after=None):
    src = axis_tb.Source(dut, random.Random(1), gap=0.0)
    for f in frames:
        await src.send(f)
    await axis_tb.clocks(dut, 400)


@cocotb.test()
async def adversarial(dut):
    dut.own_mac.value = int(OWN_MAC.replace(":", ""), 16)
    dut.own_ip.value = 0xC0A80A02
    await axis_tb.start(dut)
    sink = axis_tb.Sink(dut, random.Random(2), ready=1.0)
    results = []
    # 1. odd lengths: data 1, 37, 101 bytes (odd ICMP byte count)
    for n in (1, 37, 101):
        f = req(bytes(random.Random(n).randrange(256) for _ in range(n)))
        before = len(sink.frames)
        await run_case(dut, [f])
        got = sink.frames[before:]
        ok = len(got) == 1 and got[0][0] == expect_reply(f)
        results.append((f"odd {n}", ok, got[0][0].hex() if got else None))
    # 2. odd count and a wrong checksum: no reply
    f = req(bytes(range(37)), badcs=True)
    before = len(sink.frames); await run_case(dut, [f])
    results.append(("bad csum odd", len(sink.frames) == before, None))
    # 3. IP options (a NOP x4): the contract says no reply
    f = req(bytes(range(20)), opts=[b"\x01\x01\x01\x01"])
    before = len(sink.frames); await run_case(dut, [f])
    results.append(("options -> none", len(sink.frames) == before, None))
    # 4. a last fragment (MF 0, offset 8): no reply; a first fragment (MF 1): no reply; DF set: reply
    for name, fl, fo, want in (("last frag", 0, 1, 0), ("first frag", 1, 0, 0), ("DF", 2, 0, 1)):
        f = req(bytes(range(40)), flags=fl, frag=fo)
        before = len(sink.frames); await run_case(dut, [f])
        got = sink.frames[before:]
        ok = len(got) == want and (want == 0 or got[0][0] == expect_reply(f))
        results.append((name, ok, None))
    # 5. back-to-back: an echo request, then a 60-byte ARP frame on the very next clock (always-ready input)
    f = req(bytes(range(100)))
    arp = bytes(Ether(src=PC_MAC, dst="ff:ff:ff:ff:ff:ff") / ARP(op=1, hwsrc=PC_MAC, psrc=PC_IP, pdst="192.168.10.50")).ljust(60, b"\x00")
    before = len(sink.frames)
    src = axis_tb.Source(dut, random.Random(1), gap=0.0)
    await src.send(f + b"")          # send() drops tvalid for zero clocks only if called again at once
    await src.send(arp)
    await axis_tb.clocks(dut, 400)
    got = sink.frames[before:]
    ok = len(got) == 1 and got[0][0] == expect_reply(f)
    results.append(("back-to-back", ok, got[0][0][:48].hex() if got else None))
    for r in results:
        dut._log.info(f"ADV {r[0]}: {'PASS' if r[1] else 'FAIL'} {r[2] or ''}")
    assert all(r[1] for r in results), [r[0] for r in results if not r[1]]
