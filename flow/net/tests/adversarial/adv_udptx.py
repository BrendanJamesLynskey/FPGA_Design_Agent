"""Independent review: ipv4_udp_tx frames against scapy's from-scratch build (checksums, lengths, ident)."""
import random
import cocotb
from scapy.all import Ether, IP, UDP, Raw
from flow.net.tests import axis_tb

OWN_MAC, OWN_IP = "02:00:00:00:00:01", "192.168.10.2"


@cocotb.test()
async def vs_scapy(dut):
    dut.own_mac.value = 0x020000000001
    dut.own_ip.value = 0xC0A80A02
    dut.s_dst_mac.value = 0x02AA00000009
    dut.s_dst_ip.value = 0xC0A80A09
    dut.s_src_port.value = 5000
    dut.s_dst_port.value = 40000
    await axis_tb.start(dut)
    sink = axis_tb.Sink(dut, random.Random(2), ready=0.7)
    src = axis_tb.Source(dut, random.Random(1), gap=0.2, user=False)
    rng = random.Random(5)
    # payload whose UDP checksum computes to zero (must go out as 0xFFFF)
    for x in range(65536):
        p2 = x.to_bytes(2, "big")
        raw = bytes(IP(src=OWN_IP, dst="192.168.10.9") / UDP(sport=5000, dport=40000) / Raw(p2))
        if raw[26:28] == b"\xff\xff":
            break
    pays = [bytes([rng.randrange(256) for _ in range(n)]) for n in (1, 2, 3, 17, 18, 255, 1471, 1472)] + [p2]
    bad = []
    for i, p in enumerate(pays):
        n0 = len(sink.frames)
        await src.send(p)
        for _ in range(20000):
            if len(sink.frames) > n0:
                break
            await axis_tb.clocks(dut, 1)
        g = sink.frames[n0][0]
        w = bytes(Ether(dst="02:aa:00:00:00:09", src=OWN_MAC) /
                  IP(src=OWN_IP, dst="192.168.10.9", ttl=int(dut.TTL.value), id=i, flags=0) /
                  UDP(sport=5000, dport=40000) / Raw(p))
        if g != w:
            bad.append((len(p), g[:44].hex(), w[:44].hex()))
    dut._log.info(f"ADV udp_tx vs scapy: {len(pays) - len(bad)} of {len(pays)} identical; zero-csum payload {p2.hex()} -> {sink.frames[-1][0][40:42].hex()}")
    assert not bad, bad
