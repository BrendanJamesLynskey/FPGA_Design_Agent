"""Independent review's adversarial ipv4_udp_rx checks, expectations from scapy-built frames and plain reasoning."""
import random
import cocotb
from scapy.all import Ether, IP, UDP, Raw
from flow.net.tests import axis_tb

OWN_MAC, OWN_IP = "02:00:00:00:00:01", "192.168.10.2"
PC = dict(src="02:aa:00:00:00:09")


def fr(payload, ip_kw=None, udp_kw=None, opts=None, mangle=None, pad=True):
    ip = IP(src="192.168.10.9", dst=OWN_IP, **(ip_kw or {}))
    if opts is not None:
        ip.options = opts
    p = Ether(dst=OWN_MAC, **PC) / ip / UDP(sport=1234, dport=5000, **(udp_kw or {})) / Raw(payload)
    b = bytearray(bytes(p))
    if mangle:
        mangle(b)
    b = bytes(b)
    return b.ljust(60, b"\x00") if pad else b


@cocotb.test()
async def adversarial(dut):
    dut.own_ip.value = 0xC0A80A02
    dut.ports.value = 5000
    dut.port_en.value = 1
    await axis_tb.start(dut)
    sink = axis_tb.Sink(dut, random.Random(2), ready=1.0, user=True)
    src = axis_tb.Source(dut, random.Random(1))
    res = []

    async def one(name, f, want_payload, want_tuser=0):
        n0 = len(sink.frames)
        await src.send(f)
        await axis_tb.clocks(dut, 50)
        got = sink.frames[n0:]
        if want_payload is None:
            ok = not got
        else:
            ok = len(got) == 1 and got[0][0] == want_payload and got[0][1]["tuser"] == want_tuser
        res.append((name, ok, got))

    pay = bytes(range(33))
    await one("plain odd payload", fr(pay), pay)
    await one("IHL 15 (40 bytes of options)", fr(pay, opts=[b"\x01" * 40]), pay)
    await one("last fragment MF0 offset 3", fr(pay, ip_kw=dict(frag=3)), None)
    await one("first fragment MF1", fr(pay, ip_kw=dict(flags=1)), None)
    await one("DF set", fr(pay, ip_kw=dict(flags=2)), pay)
    await one("UDP checksum 0 (absent)", fr(pay, udp_kw=dict(chksum=0)), pay)

    def badip(b):
        b[24] ^= 0x10
    await one("bad IP header checksum", fr(pay, mangle=badip), None)

    def badudp(b):
        b[41] ^= 0x01
    await one("bad UDP checksum, odd count", fr(pay, mangle=badudp), pay, 1)
    # a UDP length one larger than the IP payload holds: dropped
    await one("UDP length > IP payload", fr(pay, udp_kw=dict(len=8 + len(pay) + 1)), None)
    # a UDP length shorter than the IP payload: only ulen bytes go out. scapy computes the checksum over the whole
    # payload, not the ulen bytes, so the case is sent without a checksum (0)
    await one("UDP length < IP payload", fr(pay, udp_kw=dict(len=8 + 10, chksum=0)), pay[:10])
    # IP total length larger than the frame (truncated datagram): payload marked to discard or dropped
    def trunc_tl(b):
        pass
    f = fr(pay, pad=False)[:-5]
    n0 = len(sink.frames); await src.send(f); await axis_tb.clocks(dut, 50)
    got = sink.frames[n0:]
    res.append(("truncated frame", (not got) or got[0][1]["tuser"] == 1, got))
    # UDP checksum that is legitimately 0xFFFF on the wire: find a payload whose checksum computes to 0
    for x in range(65536):
        p2 = x.to_bytes(2, "big")
        c = UDP(bytes(IP(src="192.168.10.9", dst=OWN_IP) / UDP(sport=1234, dport=5000) / Raw(p2))[20:]).chksum
        raw = bytes(IP(src="192.168.10.9", dst=OWN_IP) / UDP(sport=1234, dport=5000) / Raw(p2))
        if raw[26:28] == b"\xff\xff":
            break
    await one("UDP checksum 0xFFFF on the wire", fr(p2), p2)
    for r in res:
        dut._log.info(f"ADV {r[0]}: {'PASS' if r[1] else 'FAIL'} {r[2] if not r[1] else ''}")
    assert all(r[1] for r in res), [r[0] for r in res if not r[1]]
