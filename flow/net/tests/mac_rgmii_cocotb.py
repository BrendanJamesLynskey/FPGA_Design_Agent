"""cocotb bench for ip_lib/eth_mac_rgmii (brief 58A step 0, the tri-mode MAC entry).

A Python RGMII PHY drives the receive pins (DDR at 1000 Mb/s, one nibble per RX_CLK at 100 and 10 Mb/s) and samples
the transmit pins at TXC's edges. Expected results come from the standards (zlib's CRC-32 for the FCS), never from the
RTL. Environment: MAC_SPEEDS (e.g. "2,1,0"), MAC_N (frames per check), MAC_SEED."""

from __future__ import annotations

import os
import random
import struct
import zlib

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge, Timer

SEED = int(os.environ.get("MAC_SEED", "1"))
SPEEDS = [int(s) for s in os.environ.get("MAC_SPEEDS", "2").split(",")]
N = int(os.environ.get("MAC_N", "24"))
PERIOD_NS = {2: 8, 1: 40, 0: 400}
PRE = bytes([0x55] * 7 + [0xD5])


def fcs(b: bytes) -> bytes:
    return struct.pack("<I", zlib.crc32(b) & 0xFFFFFFFF)


def param(dut, name: str) -> int:
    return int(getattr(dut, name).value)


class Phy:
    def __init__(self, dut, speed: int):
        self.dut, self.speed = dut, speed
        self.T = PERIOD_NS[speed]
        self.tx_frames: list[bytes] = []
        self.tx_gaps: list[int] = []        # idle byte times before each frame after the first

    async def rx_idle(self, n: int):
        """n byte times of idle on the receive pins (RX_CLK keeps running)."""
        d = self.dut
        per_byte = 1 if self.speed == 2 else 2
        for _ in range(n * per_byte):
            d.rgmii_rxd.value = 0
            d.rgmii_rx_ctl.value = 0
            await self._clk_cycle()

    async def _clk_cycle(self, hi_nibble=None, ctl_f=None):
        d, q = self.dut, self.T / 4
        await Timer(q, unit="ns")
        d.rgmii_rx_clk.value = 1
        await Timer(q, unit="ns")
        if hi_nibble is not None:
            d.rgmii_rxd.value = hi_nibble
            d.rgmii_rx_ctl.value = ctl_f
        await Timer(q, unit="ns")
        d.rgmii_rx_clk.value = 0
        await Timer(q, unit="ns")

    async def rx_frame(self, wire: bytes, er_at: int = -1):
        d = self.dut
        for k, b in enumerate(wire):
            er = k == er_at
            if self.speed == 2:
                d.rgmii_rxd.value = b & 0xF
                d.rgmii_rx_ctl.value = 1
                await self._clk_cycle(b >> 4, 1 ^ er)
            else:
                for nib in (b & 0xF, b >> 4):
                    d.rgmii_rxd.value = nib
                    d.rgmii_rx_ctl.value = 1
                    await self._clk_cycle(nib, 1 ^ er)
        d.rgmii_rx_ctl.value = 0

    async def tx_monitor(self):
        """Frames on the transmit pins, preamble included, and the idle byte times between them."""
        d = self.dut
        cur = None
        nib = []
        idle = 0
        while True:
            await RisingEdge(d.rgmii_txc)
            lo = int(d.rgmii_txd.value)
            en = int(d.rgmii_tx_ctl.value)
            if self.speed == 2:
                await FallingEdge(d.rgmii_txc)
                b = lo | (int(d.rgmii_txd.value) << 4)
                if en:
                    if cur is None:
                        cur = bytearray()
                        if self.tx_frames:
                            self.tx_gaps.append(idle)
                    cur.append(b)
                else:
                    if cur is not None:
                        self.tx_frames.append(bytes(cur))
                        cur, idle = None, 0
                    idle += 1
            else:
                if en:
                    if cur is None:
                        cur, nib = bytearray(), []
                        if self.tx_frames:
                            self.tx_gaps.append(idle // 2)
                    nib.append(lo)
                    if len(nib) == 2:
                        cur.append(nib[0] | nib[1] << 4)
                        nib = []
                else:
                    if cur is not None:
                        self.tx_frames.append(bytes(cur))
                        cur, idle = None, 0
                    idle += 1


async def setup(dut, speed: int) -> Phy:
    cocotb.start_soon(Clock(dut.clk, 8, unit="ns").start())    # cocotb ends every test's coroutines, clocks too

    async def clk90():
        await Timer(2, unit="ns")
        await cocotb.start(Clock(dut.clk90, 8, unit="ns").start())
    cocotb.start_soon(clk90())
    dut.speed.value = speed
    dut.rgmii_rx_clk.value = 0
    dut.rgmii_rxd.value = 0
    dut.rgmii_rx_ctl.value = 0
    dut.m_axis_tready.value = 1
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tdata.value = 0
    dut.s_axis_tlast.value = 0
    dut.s_axis_tuser.value = 0
    dut.tx_poison.value = 0
    dut.rst.value = 1
    phy = Phy(dut, speed)
    await phy.rx_idle(8)                                  # RX_CLK runs during reset (the RX reset is synchronised to it)
    for _ in range(4):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await phy.rx_idle(16)
    return phy


def rx_cases(rng: random.Random, n: int, max_frame: int, min_frame: int, speed: int) -> list[tuple[bytes, int, str]]:
    """(frame with FCS, RX_ER byte or -1, what) for the receive checks."""
    out = []
    for k in range(n):
        ln = rng.choice([min_frame - 4, 60, 64, 128, 300, max_frame - 4]) if speed == 2 else rng.choice([60, 64, 90])
        body = bytes(rng.randrange(256) for _ in range(ln))
        kind = rng.choice(["good"] * 5 + ["fcs", "runt", "giant", "er"]) if k else "good"
        if speed != 2 and kind == "giant":
            kind = "fcs"
        if kind == "good":
            out.append((body + fcs(body), -1, kind))
        elif kind == "fcs":
            f = bytearray(body + fcs(body))
            f[-1] ^= 0x40
            out.append((bytes(f), -1, kind))
        elif kind == "runt":
            b = body[:min_frame - 8]
            out.append((b + fcs(b), -1, kind))
        elif kind == "giant":
            b = bytes(rng.randrange(256) for _ in range(max_frame + 4))
            out.append((b + fcs(b), -1, kind))
        else:
            out.append((body + fcs(body), 9 + rng.randrange(len(body) - 2), kind))
    return out


@cocotb.test()
async def receive(dut):
    """Every frame's bytes on the cut-through outputs and its verdict; with CUT_THROUGH = 0 the good frames, FCS
    removed, on the AXI-Stream output under random back-pressure, and the bad ones dropped and counted. Back-to-back
    frames with the minimum gap at 1000 Mb/s."""
    ct = param(dut, "CUT_THROUGH")
    minf, maxf = param(dut, "MIN_FRAME"), param(dut, "MAX_FRAME")
    for speed in SPEEDS:
        phy = await setup(dut, speed)
        rng = random.Random(SEED + speed)
        cases = rx_cases(rng, N if speed == 2 else max(3, N // 8), maxf, minf, speed)
        seen, ends, axis = [], [], []
        dropped = 0

        async def mon():
            nonlocal dropped
            cur = bytearray()
            acur = bytearray()
            while True:
                await RisingEdge(dut.clk)
                await ReadOnly()
                if int(dut.rx_valid.value):
                    if int(dut.rx_sof.value):
                        cur = bytearray()
                    assert int(dut.rx_idx.value) == len(cur)
                    cur.append(int(dut.rx_data.value))
                if int(dut.rx_end_valid.value):
                    seen.append(bytes(cur))
                    ends.append({k: int(getattr(dut, "rx_end_" + k).value) for k in
                                 ("good", "fcs_err", "runt", "giant", "er", "len")})
                tv = int(dut.m_axis_tvalid.value)
                td, tl = (int(dut.m_axis_tdata.value), int(dut.m_axis_tlast.value)) if tv else (0, 0)
                if int(dut.rx_sf_dropped.value):
                    dropped += 1
                await Timer(1, unit="ns")
                ready = 1 if rng.random() < 0.7 else 0            # tready for the coming edge
                dut.m_axis_tready.value = ready
                if tv and ready:
                    acur.append(td)
                    if tl:
                        axis.append(bytes(acur))
                        acur = bytearray()

        mon_task = cocotb.start_soon(mon())
        for k, (fr, er, kind) in enumerate(cases):
            await phy.rx_frame(PRE + fr, er_at=(8 + er) if er >= 0 else -1)
            await phy.rx_idle(12 if speed == 2 and k % 3 == 0 else 20)
        await phy.rx_idle(64)
        for _ in range(4000):
            await RisingEdge(dut.clk)
        mon_task.cancel()
        assert len(seen) == len(cases), (len(seen), len(cases))
        for (fr, er, kind), got, e in zip(cases, seen, ends):
            assert got == fr[:2047], f"{kind}: bytes differ"
            assert e["len"] == len(fr)
            assert e["good"] == (kind == "good"), (kind, e)
            assert e["fcs_err"] == (kind in ("fcs",)), (kind, e)
            assert e["runt"] == (kind == "runt") and e["giant"] == (kind == "giant") and e["er"] == (kind == "er")
        if ct == 0:
            want = [fr[:-4] for fr, er, kind in cases if kind == "good"]
            assert axis == want, f"store-and-forward: {len(axis)} frames out, {len(want)} expected"
            assert dropped == len(cases) - len(want)
        else:
            assert not axis
        dut._log.info(f"receive speed {speed}: {len(cases)} frames ({sum(k == 'good' for *_, k in cases)} good)")


@cocotb.test()
async def transmit(dut):
    """AXI-Stream frames to the wire: preamble and SFD, the bytes, zero padding to MIN_DATA, the FCS, the gap; tuser
    and an underrun each end a frame with a bad FCS."""
    min_data, ifg = param(dut, "MIN_DATA"), param(dut, "IFG_BYTES")
    for speed in SPEEDS:
        phy = await setup(dut, speed)
        txmon = cocotb.start_soon(phy.tx_monitor())
        rng = random.Random(SEED + 10 + speed)
        n = N if speed == 2 else max(3, N // 8)
        frames, marks = [], []
        underruns = 0
        for k in range(n):
            ln = rng.choice([1, 20, min_data - 1, min_data, 100, 1514]) if speed == 2 else rng.choice([10, 64])
            frames.append(bytes(rng.randrange(256) for _ in range(ln)))
            marks.append("good" if k == 0 else rng.choice(["good"] * 6 + ["tuser", "underrun"]))
        for k, (fr, mark) in enumerate(zip(frames, marks)):
            if mark == "underrun" and len(fr) < 3:
                marks[k] = mark = "good"
            gap_at = rng.randrange(1, len(fr) - 1) if mark == "underrun" else -1
            i = 0
            while i < len(fr):
                stall = i == gap_at
                dut.s_axis_tvalid.value = 0 if stall else 1
                dut.s_axis_tdata.value = fr[i]
                dut.s_axis_tlast.value = int(i == len(fr) - 1)
                dut.s_axis_tuser.value = int(mark == "tuser" and i == len(fr) - 1)
                await ReadOnly()
                took = (not stall) and int(dut.s_axis_tready.value)
                await RisingEdge(dut.clk)
                await ReadOnly()
                if int(dut.tx_underrun.value):
                    underruns += 1
                    await RisingEdge(dut.clk)
                    break
                await Timer(1, unit="ns")
                if took:
                    i += 1
            dut.s_axis_tvalid.value = 0
            dut.s_axis_tlast.value = 0
            dut.s_axis_tuser.value = 0
            # wait for the MAC to finish this frame
            for _ in range(200000):
                await RisingEdge(dut.clk)
                await ReadOnly()
                if int(dut.tx_last_pulse.value):
                    break
            await RisingEdge(dut.clk)
        for _ in range(PERIOD_NS[speed] * 40):
            await RisingEdge(dut.clk)
        txmon.cancel()
        assert len(phy.tx_frames) == n, (len(phy.tx_frames), n, speed)
        for fr, mark, w in zip(frames, marks, phy.tx_frames):
            assert w[:8] == PRE, (speed, w[:16].hex(), len(w), len(fr), mark)
            body, f = w[8:-4], w[-4:]
            if mark == "underrun":
                assert fcs(body) != f and len(body) >= min_data
                continue
            want = fr + bytes(max(0, min_data - len(fr)))
            assert body == want, f"{mark}: data differ ({len(body)} vs {len(want)})"
            assert (fcs(body) == f) == (mark == "good"), mark
        assert all(g >= ifg for g in phy.tx_gaps), phy.tx_gaps
        if speed == 2:          # frames offered at once: the gap is IFG_BYTES idle byte times plus the start clock
            assert min(phy.tx_gaps) == ifg + 1, (min(phy.tx_gaps), ifg)
        assert underruns == marks.count("underrun")
        dut._log.info(f"transmit speed {speed}: {n} frames, gaps min {min(phy.tx_gaps or [0])}")
