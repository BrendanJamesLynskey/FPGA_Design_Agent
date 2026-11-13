"""Independent review: arp_responder against RFC 826 scenarios; frames built by scapy."""
import random
import cocotb
from cocotb.triggers import RisingEdge, ReadOnly, Timer
from scapy.all import Ether, ARP
from flow.net.tests import axis_tb

OWN_MAC, OWN_IP = "02:00:00:00:00:01", "192.168.10.2"


def ip2i(s):
    return int.from_bytes(bytes(int(x) for x in s.split(".")), "big")


def arp(op, hwsrc, psrc, pdst, hwdst="00:00:00:00:00:00", dst="ff:ff:ff:ff:ff:ff"):
    return bytes(Ether(dst=dst, src=hwsrc) / ARP(op=op, hwsrc=hwsrc, psrc=psrc, hwdst=hwdst, pdst=pdst)).ljust(60, b"\x00")


async def lookup(dut, ip):
    dut.lk_ip.value = ip2i(ip)
    dut.lk_valid.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.lk_valid.value = 0
    await ReadOnly()
    hit, mac = int(dut.lk_hit.value), int(dut.lk_mac.value)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    return hit, "%012x" % mac


@cocotb.test()
async def scenarios(dut):
    dut.own_mac.value = 0x020000000001
    dut.own_ip.value = ip2i(OWN_IP)
    dut.lk_valid.value = 0
    dut.lk_ip.value = 0
    dut.flush.value = 0
    await axis_tb.start(dut)
    sink = axis_tb.Sink(dut, random.Random(2), ready=1.0)
    src = axis_tb.Source(dut, random.Random(1))
    res = []

    async def send(f):
        n0 = len(sink.frames)
        await src.send(f)
        await axis_tb.clocks(dut, 80)
        return [f for f in sink.frames[n0:] if f[0][21] == 2]      # replies only (lookups send requests)
    # a request for another IP: no reply, not learnt
    got = await send(arp(1, "02:aa:00:00:00:01", "192.168.10.11", "192.168.10.99"))
    res.append(("request for other IP: no reply", not got, len(got)))
    res.append(("  ...and not learnt", (await lookup(dut, "192.168.10.11"))[0] == 0, None))
    # a gratuitous ARP from an unknown host: not learnt (RFC 826: only merge when already known)
    got = await send(arp(1, "02:aa:00:00:00:02", "192.168.10.12", "192.168.10.12"))
    res.append(("gratuitous unknown: no reply", not got, len(got)))
    res.append(("gratuitous unknown: not learnt", (await lookup(dut, "192.168.10.12"))[0] == 0, None))
    # a request for us: reply exact, sender learnt
    r = arp(1, "02:aa:00:00:00:03", "192.168.10.13", OWN_IP)
    got = await send(r)
    want = bytes(Ether(dst="02:aa:00:00:00:03", src=OWN_MAC) / ARP(op=2, hwsrc=OWN_MAC, psrc=OWN_IP, hwdst="02:aa:00:00:00:03", pdst="192.168.10.13"))
    res.append(("reply bytes == scapy", len(got) == 1 and got[0][0] == want, got[0][0].hex() if got else None))
    res.append(("requester learnt", await lookup(dut, "192.168.10.13") == (1, "02aa00000003"), None))
    # a gratuitous ARP from the known host with a new MAC: updated (merge)
    await send(arp(1, "02:aa:00:00:00:33", "192.168.10.13", "192.168.10.13"))
    res.append(("gratuitous known: updated", await lookup(dut, "192.168.10.13") == (1, "02aa00000033"), None))
    # a gratuitous reply (op 2) from the known host: updated
    await send(arp(2, "02:aa:00:00:00:44", "192.168.10.13", "192.168.10.13"))
    res.append(("gratuitous reply known: updated", await lookup(dut, "192.168.10.13") == (1, "02aa00000044"), None))
    # an ARP probe (sender 0.0.0.0) for our address: answered, nothing learnt
    got = await send(arp(1, "02:aa:00:00:00:05", "0.0.0.0", OWN_IP))
    res.append(("probe for us: answered", len(got) == 1, len(got)))
    res.append(("probe: 0.0.0.0 not learnt", (await lookup(dut, "0.0.0.0"))[0] == 0, None))
    # full cache (CACHE_N 2): three senders -> round robin keeps the newest two
    for i in (21, 22, 23):
        await send(arp(1, "02:aa:00:00:00:%02x" % i, "192.168.10.%d" % i, OWN_IP))
    hits = [(await lookup(dut, "192.168.10.%d" % i))[0] for i in (13, 21, 22, 23)]
    res.append(("full cache: 2 entries kept", sum(hits) == 2, hits))
    # a conflict: another station claims OUR address (gratuitous). Never learnt; ev_conflict pulses (RFC 5227)
    nconf = [0]

    async def count_conf():
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            nconf[0] += int(dut.ev_conflict.value)
    ct = cocotb.start_soon(count_conf())
    await send(arp(1, "02:aa:00:00:00:66", OWN_IP, OWN_IP))
    await send(arp(2, "02:aa:00:00:00:67", OWN_IP, "192.168.10.13"))
    ct.cancel()
    res.append(("own IP claimed by another station: not learnt", (await lookup(dut, OWN_IP))[0] == 0, None))
    res.append(("  ...and reported as a conflict (twice)", nconf[0] == 2, nconf[0]))
    for r in res:
        dut._log.info(f"ADV {r[0]}: {'PASS' if r[1] else 'FAIL'} {r[2]}")
    assert all(r[1] for r in res), [r[0] for r in res if not r[1]]
