"""cocotb bench for ip_lib/eth_mac_rgmii (the tri-mode MAC entry).

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
OWN = bytes.fromhex("020000000001")       # a locally administered address
OWN_INT = int.from_bytes(OWN, "big")


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
    for name, v in (("mac_addr", OWN_INT), ("promisc", 0), ("bcast_en", 1), ("mcast_all", 0), ("mc_hash", 0),
                    ("mc_we", 0), ("mc_idx", 0), ("mc_addr", 0), ("mc_en", 0), ("pause_req", 0), ("pause_quanta", 0),
                    ("stat_clear", 0), ("stat_addr", 0)):
        getattr(dut, name).value = v
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
            assert got == fr[:2047 if maxf <= 2000 else 16383], f"{kind}: bytes differ"     # rx_idx saturates
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


# ---------------------------------------------------------------------------------------------------------------------
# 0.2 features: address filter, VLAN, pause, statistics, jumbo frames. Expected values from ip_lib/eth_mac_rgmii/model.py
# (written from IEEE 802.3 and 802.1Q), never from the RTL.
from ip_lib.eth_mac_rgmii import model as M  # noqa: E402

EXACT = [bytes.fromhex("01005e000001"), bytes.fromhex("01005e7f0002"), bytes.fromhex("01005e0000fb")]
HASHED = [bytes.fromhex("333300000001"), bytes.fromhex("01005e0a0b0c")]


async def read_stats(dut) -> dict:
    out = {}
    for i, name in enumerate(M.STAT_NAMES):
        dut.stat_addr.value = i
        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        await ReadOnly()
        out[name] = int(dut.stat_data.value)
        await RisingEdge(dut.clk)
    return out


async def configure(dut, c: M.FilterCfg, n_exact: int):
    dut.mac_addr.value = M.mac_int(c.own)
    dut.promisc.value = int(c.promisc)
    dut.bcast_en.value = int(c.bcast_en)
    dut.mcast_all.value = int(c.mcast_all)
    dut.mc_hash.value = c.hash_bits
    for i in range(n_exact):
        await RisingEdge(dut.clk)
        dut.mc_we.value, dut.mc_idx.value = 1, i
        dut.mc_addr.value = M.mac_int(c.exact[i]) if i < len(c.exact) else 0
        dut.mc_en.value = int(i < len(c.exact))
    await RisingEdge(dut.clk)
    dut.mc_we.value = 0


DA_KINDS = ["own", "bcast", "exact", "hash", "mcast", "other", "pause"]


def rand_da(rng: random.Random, c: M.FilterCfg, k: str | None = None) -> bytes:
    k = k or rng.choice(DA_KINDS)
    if k == "own":
        return c.own
    if k == "bcast":
        return M.BCAST
    if k == "exact" and c.exact:
        return rng.choice(c.exact)
    if k == "hash":
        return rng.choice(HASHED)
    if k == "pause":
        return M.PAUSE_DA
    if k == "mcast":
        return bytes([0x01, 0x00, 0x5E, rng.randrange(128), rng.randrange(256), rng.randrange(256)])
    return bytes([0x02, 0x11, 0x22, rng.randrange(256), rng.randrange(256), 0x10])


def rand_frame(rng: random.Random, c: M.FilterCfg, max_len: int = 300, kind: str | None = None) -> bytes:
    """A frame without FCS: a random destination (or one of `kind`), sometimes tagged, sometimes a MAC control
    (pause) frame."""
    da = rand_da(rng, c, kind)
    sa = bytes([0x02, 0x33, 0x44, 0x55, 0x66, rng.randrange(256)])
    u = rng.random()
    if u < 0.15:
        body = b"\x88\x08\x00\x01" + struct.pack(">H", rng.randrange(1, 4))     # pause, short quanta
    elif u < 0.2:
        body = b"\x88\x08\x00\x02"                                              # another MAC control opcode
    elif u < 0.45:
        tpid = rng.choice([b"\x81\x00", b"\x88\xa8"])
        body = tpid + struct.pack(">H", rng.randrange(65536)) + b"\x08\x00"
    else:
        body = b"\x08\x00"
    n = rng.randrange(60, max_len)
    return (da + sa + body + bytes(rng.randrange(256) for _ in range(n))).ljust(60, b"\x00")[:max(60, n)]


async def rx_run(dut, phy, frames_fcs, rng, ct: int):
    """Drive frames (with FCS) into the receive pins; return the cut-through verdicts and flags per frame and the
    store-and-forward frames with their TCI."""
    ends, axis = [], []

    async def mon():
        acur, atci = bytearray(), None
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            if int(dut.rx_end_valid.value):
                ends.append({k: int(getattr(dut, "rx_end_" + k).value) for k in
                             ("good", "len", "filtered", "bcast", "mcast", "vlan", "tci", "ctrl", "pause", "giant")})
            tv = int(dut.m_axis_tvalid.value)
            if tv:
                td, tl = int(dut.m_axis_tdata.value), int(dut.m_axis_tlast.value)
                tci = (int(dut.m_axis_tci.value), int(dut.m_axis_tagged.value))
            await Timer(1, unit="ns")
            ready = 1 if rng.random() < 0.8 else 0
            dut.m_axis_tready.value = ready
            if tv and ready:
                if not acur:
                    atci = tci
                assert tci == atci, "m_axis_tci changed inside a frame"
                acur.append(td)
                if tl:
                    axis.append((bytes(acur), atci[0] if atci[1] else None))
                    acur = bytearray()

    t = cocotb.start_soon(mon())
    for fr in frames_fcs:
        await phy.rx_frame(PRE + fr)
        await phy.rx_idle(12)
    await phy.rx_idle(64)
    for _ in range(3000 + sum(len(f) for f in frames_fcs) // 2):
        await RisingEdge(dut.clk)
    t.cancel()
    dut.m_axis_tready.value = 1
    return ends, axis


@cocotb.test()
async def filter_rx(dut):
    """Address filter, VLAN tag report and strip, MAC control frames consumed, statistics: three filter settings, each
    against the model frame by frame, then every counter and a clear."""
    ct, flt, vlan, pause = (param(dut, n) for n in ("CUT_THROUGH", "FILTER", "VLAN", "PAUSE"))
    n_exact = param(dut, "MC_EXACT")
    speed = SPEEDS[0]
    phy = await setup(dut, speed)
    rng = random.Random(SEED + 77)
    st = M.new_stats()
    settings = [M.FilterCfg(own=OWN, exact=EXACT[:min(n_exact, 2)], hash_bits=sum(1 << M.hash_index(h) for h in HASHED)),
                M.FilterCfg(own=OWN, promisc=True),
                M.FilterCfg(own=OWN, bcast_en=False, mcast_all=True)]
    for si, c in enumerate(settings):
        await configure(dut, c, n_exact)
        frames, kinds = [], []
        for k in range(N if speed == 2 else max(6, N // 3)):
            fr = rand_frame(rng, c, kind=DA_KINDS[k - 1] if 1 <= k <= len(DA_KINDS) else None)   # each kind once
            kind = "good" if k % 8 else rng.choice(["fcs", "runt"])
            if kind == "fcs":
                f = bytearray(fr + M.fcs(fr)); f[-1] ^= 1; frames.append(bytes(f))
            elif kind == "runt":
                fr = fr[:40]; frames.append(fr + M.fcs(fr))
            else:
                frames.append(fr + M.fcs(fr))
            kinds.append(kind)
        ends, axis = await rx_run(dut, phy, frames, rng, ct)
        assert len(ends) == len(frames), (len(ends), len(frames))
        want_axis = []
        for fr, kind, e in zip(frames, kinds, ends):
            f = M.classify(fr[:-4], c)
            assert e["good"] == (kind == "good"), (si, kind, e)
            assert e["len"] == len(fr)
            if kind == "good":
                assert e["filtered"] == (flt and not f["match"]), (si, fr[:6].hex(), e)
                assert e["bcast"] == f["bcast"] and e["mcast"] == f["mcast"], (si, fr[:6].hex(), e)
                assert e["ctrl"] == f["ctrl"]
                assert e["pause"] == (pause and f["pause"]), (fr[:18].hex(), e)
                assert e["vlan"] == (bool(vlan) and f["vlan"]) and e["tci"] == (f["tci"] if vlan else 0), (fr[:18].hex(), e)
                if (not flt or f["match"]) and not (pause and f["ctrl"]):
                    want_axis.append(M.sf_output(fr[:-4], vlan == 2))
            M.count_rx(st, fr, kind, c, bool(flt), bool(vlan), bool(pause))
        if ct == 0:
            assert axis == want_axis, f"setting {si}: {len(axis)} frames out, {len(want_axis)} expected"
        else:
            assert not axis
        dut._log.info(f"filter_rx setting {si}: {len(frames)} frames, {len(want_axis)} kept")
    if ct == 0:                     # the store-and-forward latency: rx_end_valid to the first m_axis beat, buffer empty
        await configure(dut, M.FilterCfg(own=OWN), n_exact)
        fr = OWN + bytes(range(6, 64))
        t = {}

        async def lat():
            n = 0
            while True:
                await RisingEdge(dut.clk)
                await ReadOnly()
                n += 1
                if int(dut.rx_end_valid.value) and "end" not in t:
                    t["end"] = n
                if int(dut.m_axis_tvalid.value) and "end" in t and "out" not in t:
                    t["out"] = n
        lt = cocotb.start_soon(lat())
        await phy.rx_frame(PRE + fr + M.fcs(fr))
        await phy.rx_idle(80)
        lt.cancel()
        assert t["out"] - t["end"] == 4, t
        dut._log.info(f"store-and-forward latency: {t['out'] - t['end']} clocks from rx_end_valid to m_axis_tvalid")
        st["rx_frames_good"] += 1
        st["rx_octets_good"] += len(fr) + 4
    if param(dut, "STATS"):
        got = await read_stats(dut)
        w = param(dut, "STAT_W")
        want = {k: v % (1 << w) for k, v in st.items()}
        assert got == want, {k: (got[k], want[k]) for k in want if got[k] != want[k]}
        dut.stat_clear.value = 1
        await RisingEdge(dut.clk)
        dut.stat_clear.value = 0
        got = await read_stats(dut)
        assert not any(got.values()), got
        dut._log.info(f"statistics: {want}")


async def send_frame(dut, data: bytes):
    """Offer one frame on s_axis without gaps; return when its last beat is taken."""
    i = 0
    while i < len(data):
        dut.s_axis_tvalid.value = 1
        dut.s_axis_tdata.value = data[i]
        dut.s_axis_tlast.value = int(i == len(data) - 1)
        await ReadOnly()
        took = int(dut.s_axis_tready.value)
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if took:
            i += 1
    dut.s_axis_tvalid.value = 0
    dut.s_axis_tlast.value = 0


@cocotb.test()
async def pause(dut):
    """802.3x: a requested pause frame goes out ahead of waiting data, bytes and FCS exact; a received pause holds new
    frames for quanta x 64 byte times, quanta 0 releases it at once; the counters agree."""
    min_data = param(dut, "MIN_DATA")
    for speed in SPEEDS:
        phy = await setup(dut, speed)
        bt = {2: 1, 1: 10, 0: 100}[speed]             # clocks per byte time
        txmon = cocotb.start_soon(phy.tx_monitor())
        st = M.new_stats()
        # 1. pause_req and a user frame together: the pause frame first
        user = bytes([0x02, 0x99, 0, 0, 0, 1]) + OWN + b"\x08\x00" + bytes(range(50))
        dut.pause_quanta.value = 0x1234
        dut.pause_req.value = 1
        await RisingEdge(dut.clk)
        dut.pause_req.value = 0
        await send_frame(dut, user)
        for _ in range(200 * bt):
            await RisingEdge(dut.clk)
        assert len(phy.tx_frames) == 2, len(phy.tx_frames)
        w = phy.tx_frames[0]
        assert w[:8] == PRE and w[8:-4] == M.pause_frame(OWN, 0x1234) and w[-4:] == M.fcs(w[8:-4]), w.hex()
        assert phy.tx_frames[1][8:-4] == user + bytes(max(0, min_data - len(user)))
        M.count_tx(st, M.pause_frame(OWN, 0x1234), True, min_data, pause=True)
        M.count_tx(st, user, True, min_data)
        # 1b. a second request while a pause frame is on the wire: that frame keeps its quanta, the next carries the new
        n1 = len(phy.tx_frames)
        dut.pause_quanta.value = 0x0101
        dut.pause_req.value = 1
        await RisingEdge(dut.clk)
        dut.pause_req.value = 0
        for _ in range(16 * bt):                          # into the first pause frame, before its quanta bytes
            await RisingEdge(dut.clk)
        dut.pause_quanta.value = 0x0202
        dut.pause_req.value = 1
        await RisingEdge(dut.clk)
        dut.pause_req.value = 0
        for _ in range(250 * bt):
            await RisingEdge(dut.clk)
        assert [f[8:-4] for f in phy.tx_frames[n1:]] == [M.pause_frame(OWN, 0x0101), M.pause_frame(OWN, 0x0202)], \
            [f[8:28].hex() for f in phy.tx_frames[n1:]]
        M.count_tx(st, M.pause_frame(OWN, 0x0101), True, min_data, pause=True)
        M.count_tx(st, M.pause_frame(OWN, 0x0202), True, min_data, pause=True)
        # 2. a received pause holds the next frame back for quanta x 64 byte times
        for q in (3, 0):
            pf = M.pause_frame(M.PAUSE_DA, q)[:6] + bytes.fromhex("021111111111") + M.pause_frame(OWN, q)[12:]
            t_end = []

            async def watch():
                while True:
                    await RisingEdge(dut.clk)
                    await ReadOnly()
                    if int(dut.rx_end_valid.value):
                        t_end.append(cocotb.utils.get_sim_time("ns"))
                        return
            wt = cocotb.start_soon(watch())
            await phy.rx_frame(PRE + pf + M.fcs(pf))
            await phy.rx_idle(4)
            while not t_end:
                await RisingEdge(dut.clk)
            await RisingEdge(dut.clk)
            await RisingEdge(dut.clk)
            await ReadOnly()
            assert bool(int(dut.tx_paused.value)) == (q != 0)
            await Timer(1, unit="ns")
            n0 = len(phy.tx_frames)
            firsts = []

            async def first():
                while True:
                    await RisingEdge(dut.clk)
                    await ReadOnly()
                    if int(dut.tx_first_pulse.value):
                        firsts.append(cocotb.utils.get_sim_time("ns"))
            ft = cocotb.start_soon(first())
            await send_frame(dut, user)
            for _ in range(200 * bt):
                await RisingEdge(dut.clk)
            ft.cancel()
            t_first = firsts[0] if firsts else None
            wt.cancel()
            assert t_first is not None and len(phy.tx_frames) == n0 + 1
            held = (t_first - t_end[0]) / 8 / bt                 # byte times from the pause's end to the next frame
            assert q * 64 <= held <= q * 64 + 40, (q, held)
            M.count_rx(st, pf + M.fcs(pf), "good", M.FilterCfg(own=OWN), bool(param(dut, "FILTER")), False, True)
            M.count_tx(st, user, True, min_data)
            dut._log.info(f"pause speed {speed}: quanta {q}, next frame {held:.0f} byte times after the pause frame")
        txmon.cancel()
        if param(dut, "STATS"):
            got = await read_stats(dut)
            for k in ("rx_pause", "tx_pause", "tx_frames_good", "tx_octets_good", "tx_mcast", "rx_frames_good"):
                assert got[k] == st[k], (k, got[k], st[k])


@cocotb.test()
async def jumbo(dut):
    """Jumbo frames: 9000-byte MTU frames (tagged and not), MAX_FRAME exactly, one byte over (giant), through the
    cut-through view and the store-and-forward buffer, and a 9014-byte frame transmitted."""
    maxf = param(dut, "MAX_FRAME")
    phy = await setup(dut, 2)
    rng = random.Random(SEED + 99)
    c = M.FilterCfg(own=OWN)

    def mk(n, tag=False):
        head = OWN + bytes.fromhex("023333333333") + ((b"\x81\x00\x00\x05") if tag else b"") + b"\x08\x00"
        return head + bytes(rng.randrange(256) for _ in range(n - len(head)))
    frames = [mk(14 + 9000), mk(18 + 9000, tag=True), mk(maxf - 4), mk(maxf - 3), mk(60)]
    fcsd = [f + M.fcs(f) for f in frames]
    ends, axis = await rx_run(dut, phy, fcsd, rng, 0)
    assert [e["len"] for e in ends] == [len(f) for f in fcsd]
    assert [e["good"] for e in ends] == [1, 1, 1, 0, 1], ends
    assert ends[3]["giant"] == 1
    if param(dut, "CUT_THROUGH") == 0:
        assert axis == [M.sf_output(f, param(dut, "VLAN") == 2) for f in (frames[0], frames[1], frames[2], frames[4])]
    txmon = cocotb.start_soon(phy.tx_monitor())
    big = mk(9014)
    await send_frame(dut, big)
    for _ in range(300):
        await RisingEdge(dut.clk)
    txmon.cancel()
    assert phy.tx_frames and phy.tx_frames[-1] == PRE + big + M.fcs(big)
    dut._log.info(f"jumbo: received {[len(f) for f in fcsd]}, sent {len(big) + 4}")
