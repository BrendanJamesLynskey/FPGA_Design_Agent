"""cocotb test of b63d_nexys_net_top (the UART BFM's timeouts assume a 10 ns clock; this design runs at 20 ns, so they are
passed explicitly): a model RMII PHY (100 Mb/s, dibits on the 50 MHz reference clock) carries a
host's frames to the design and takes its replies, and the test shell is driven over the UART. Every frame the design
sends is checked against the library entries' models (written from the RFCs); the statistics and event counters are
read back through the shell. The same sequence is what the board run does from a PC (designs/b63d_nexys_net/host)."""
from __future__ import annotations

import struct

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

from flow.net import inet
from flow.net import model as netmodel
from ip_lib.arp_responder import model as arpm
from ip_lib.eth_mac_rgmii import model as macm
from ip_lib.icmp_echo import model as icmpm
from ip_lib.igmp_join import model as igmpm
from shell.host import protocol as p
from shell.tests.uart_bfm import UartBfm

W = 0x80
OWN_MAC = inet.mac_b("02:00:00:00:00:63")
OWN_IP = inet.ip_b("192.168.63.2")
PC_MAC = inet.mac_b("02:00:00:00:00:01")
PC_IP = inet.ip_b("192.168.63.1")


class Shell:
    def __init__(self, bfm):
        self.bfm = bfm

    async def read(self, a):
        r = p.decode_response(await self.bfm.transact(p.encode_request(p.CMD_READ, a, 0), 2000))
        assert r.status == 0, (hex(a), r.status)
        return r.data

    async def write(self, a, v):
        assert p.decode_response(await self.bfm.transact(p.encode_request(p.CMD_WRITE, a, v), 2000)).status == 0


class Phy:
    """The PHY side of RMII at 100 Mb/s: frames in on CRS_DV/RXD, frames out from TX_EN/TXD (FCS checked)."""

    def __init__(self, dut):
        self.dut, self.tx = dut, []
        dut.ETH_CRSDV.value = 0
        dut.ETH_RXD.value = 0
        dut.ETH_RXERR.value = 0
        cocotb.start_soon(self.mon())

    async def send(self, frame: bytes):
        lines, _, _ = netmodel.rx_line([{"frame": frame}])
        for v, d, e in lines:
            await FallingEdge(self.dut.ETH_REFCLK)
            self.dut.ETH_CRSDV.value, self.dut.ETH_RXD.value, self.dut.ETH_RXERR.value = v, d, e
        await FallingEdge(self.dut.ETH_REFCLK)
        self.dut.ETH_CRSDV.value = 0

    async def mon(self):
        ds = []
        while True:
            await RisingEdge(self.dut.ETH_REFCLK)
            if str(self.dut.ETH_TXEN.value) == "1":
                ds.append(int(self.dut.ETH_TXD.value))
            elif ds:
                b = bytes(sum(ds[4 * i + j] << (2 * j) for j in range(4)) for i in range(len(ds) // 4))
                assert b[:8] == bytes([0x55] * 7 + [0xD5]), b[:8].hex()
                fr = b[8:]
                assert macm.fcs(fr[:-4]) == fr[-4:], "bad FCS on the wire"
                self.tx.append(fr[:-4])
                ds = []


def padded(fr: bytes) -> bytes:
    return fr.ljust(60, b"\x00")


@cocotb.test()
async def network(dut):
    cocotb.start_soon(Clock(dut.CLK100MHZ, 10, unit="ns").start())
    dut.CPU_RESETN.value = 0
    dut.UART_TXD_IN.value = 1                        # the UART line idles high from the start
    phy = Phy(dut)
    await ClockCycles(dut.CLK100MHZ, 20)
    dut.CPU_RESETN.value = 1
    await ClockCycles(dut.CLK100MHZ, 20)
    sh = Shell(UartBfm(dut.ETH_REFCLK, dut.UART_TXD_IN, dut.UART_RXD_OUT, int(dut.CLKS_PER_BIT.value)))
    assert await sh.read(0) == 0x4E363344, "DESIGN_ID is not N63D"
    assert await sh.read(W + 3) == int.from_bytes(OWN_IP, "big")
    sent = 0

    async def expect(n_new: int, clocks: int = 6000):
        for _ in range(clocks // 100):
            if len(phy.tx) >= n_new:
                break
            await ClockCycles(dut.ETH_REFCLK, 100)
        assert len(phy.tx) == n_new, (len(phy.tx), n_new)

    # 1. ARP: a request for our address is answered (and the PC is learnt)
    req = inet.eth(arpm.BCAST, PC_MAC, 0x0806, inet.arp(1, PC_MAC, PC_IP, b"\x00" * 6, OWN_IP))
    await phy.send(padded(req)); sent += 1
    await expect(1)
    assert phy.tx[0] == padded(arpm.reply(OWN_MAC, OWN_IP, {"sha": PC_MAC, "spa": PC_IP})), phy.tx[0].hex()

    # 2. ping
    ping = icmpm.request(PC_MAC, OWN_MAC, PC_IP, OWN_IP, 0x1234, 7, bytes(range(56)))
    await phy.send(ping); sent += 1
    await expect(2)
    assert phy.tx[1] == padded(icmpm.reply(ping, OWN_MAC, OWN_IP, 64)[0]), phy.tx[1].hex()

    # 3. a frame to another station's MAC is filtered: no answer
    other = inet.eth(inet.mac_b("02:00:00:00:00:99"), PC_MAC, 0x0800,
                     icmpm.request(PC_MAC, OWN_MAC, PC_IP, OWN_IP, 1, 1, b"x")[14:])
    await phy.send(padded(other)); sent += 1
    await ClockCycles(dut.ETH_REFCLK, 3000)
    assert len(phy.tx) == 2

    # 4. the UDP statistics service answers to the PC's port with "N63D" and the counters
    u = inet.udp(PC_IP, OWN_IP, 40000, 5000, b"stats please")
    dg = inet.eth(OWN_MAC, PC_MAC, 0x0800, inet.ipv4(PC_IP, OWN_IP, 17, u, ident=9))
    await phy.send(padded(dg)); sent += 1
    await expect(3, 20000)
    r = phy.tx[2]
    assert r[:6] == PC_MAC and r[6:12] == OWN_MAC and r[12:14] == b"\x08\x00"
    assert inet.ok(r[14:34]) and r[26:30] == OWN_IP and r[30:34] == PC_IP and r[23] == 17
    ud = r[34:34 + struct.unpack(">H", r[38:40])[0]]
    assert inet.udp_ok(OWN_IP, PC_IP, ud) and struct.unpack(">HH", ud[:4]) == (5000, 40000)
    pay = ud[8:]
    assert pay[:4] == b"N63D" and len(pay) == 88
    ctr = dict(zip(macm.STAT_NAMES, struct.unpack(">21I", pay[4:])))
    assert ctr["rx_frames_good"] == 4 and ctr["rx_filtered"] == 1 and ctr["tx_frames_good"] == 2, ctr
    assert ctr["rx_bcast"] == 1, ctr

    # 5. IGMP: joining group 0 sends a report to it (TTL 1, Router Alert)
    await sh.write(W + 7, 1)
    await expect(4, 6000)
    d = igmpm.parse_host_frame(phy.tx[3])
    assert d["type"] == 0x16 and d["group"] == inet.ip_b("239.63.0.1")
    assert phy.tx[3] == padded(igmpm.host_frame(OWN_MAC, OWN_IP, d["group"], False, d["ident"]))
    await expect(5, 3000)                            # the join's repeat, within UNSOL_TICKS (10 ticks of 200 clocks)
    assert phy.tx[4] == padded(igmpm.host_frame(OWN_MAC, OWN_IP, d["group"], False, d["ident"] + 1))

    # 6. the injector sends a host-written frame; the capture records a received one
    inj = padded(inet.eth(PC_MAC, OWN_MAC, 0x88B5, b"injected by the host"))
    await sh.write(W + 0x42, 0)
    for i in range(0, len(inj), 4):
        await sh.write(W + 0x41, int.from_bytes(inj[i:i + 4].ljust(4, b"\x00"), "big"))
    await sh.write(W + 0x40, (1 << 31) | len(inj))
    await expect(6, 4000)
    assert phy.tx[5] == inj, phy.tx[5].hex()
    await sh.write(W + 0x48, 1)
    cap = padded(inet.eth(OWN_MAC, PC_MAC, 0x88B5, b"captured by the design"))
    await phy.send(cap); sent += 1
    await ClockCycles(dut.ETH_REFCLK, 400)
    st = await sh.read(W + 0x48)
    assert st >> 31 and st & 0x7FF == len(cap) and not (st >> 30) & 1, hex(st)
    await sh.write(W + 0x49, 0)
    got = bytes([await sh.read(W + 0x4A) & 0xFF for _ in range(len(cap))])
    assert got == cap, got.hex()

    # 7. counters through the shell
    stats = {n: await sh.read(W + 0x10 + i) for i, n in enumerate(macm.STAT_NAMES)}
    assert stats["rx_frames_good"] == sent and stats["rx_filtered"] == 1 and stats["tx_frames_good"] == len(phy.tx), stats
    assert stats["rx_octets_good"] == 64 * 4 + len(ping) + 4, stats
    ev = [await sh.read(W + 0x30 + i) for i in range(5)]
    assert ev[0] == (1 << 16) | 1 and ev[1] == (1 << 16) | 1 and ev[4] >> 16 == 1, [hex(x) for x in ev]
    # MDIO: a write runs to completion (the line has no PHY model here; the mdio_master entry's bench has one)
    await sh.write(W + 4, (1 << 21) | (0 << 16) | 0x3100)
    await ClockCycles(dut.ETH_REFCLK, 64 * 26 + 50)
    assert not (await sh.read(W + 4)) >> 31
    # the XADC alarm latch: a short alarm between polls stays set until cleared
    assert await sh.read(W + 0x3C) == 0
    dut.u_xadc.alm_force.value = 1
    await ClockCycles(dut.ETH_REFCLK, 3)
    dut.u_xadc.alm_force.value = 0
    await ClockCycles(dut.ETH_REFCLK, 10)
    assert await sh.read(W + 0x3C) == 1
    await sh.write(W + 0x3C, 0)
    assert await sh.read(W + 0x3C) == 0
    dut._log.info(f"network: {len(phy.tx)} frames sent by the design, all checked; statistics {stats}")
