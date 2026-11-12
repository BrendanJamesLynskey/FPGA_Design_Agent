"""Byte-wide AXI-Stream source and sink for the brief 63D cocotb benches (valid/ready handshake checked as it goes).

The sink checks the AXI-Stream rules it can see: once tvalid is high it stays high, with tdata, tlast and the sideband
signals steady, until the beat is taken."""
from __future__ import annotations

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge, Timer


async def start(dut, period_ns: int = 8, reset_clocks: int = 5):
    cocotb.start_soon(Clock(dut.clk, period_ns, unit="ns").start())
    dut.rst.value = 1
    for _ in range(reset_clocks):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)


class Source:
    """Drives s_axis_*: frames with optional tuser on the last beat and random idle clocks between beats."""

    def __init__(self, dut, rng: random.Random, gap: float = 0.0, prefix: str = "s_axis_", user: bool = True):
        self.dut, self.rng, self.gap, self.p, self.user = dut, rng, gap, prefix, user
        self.sig("tvalid").value = 0
        self.sig("tlast").value = 0
        self.sig("tdata").value = 0
        if user:
            self.sig("tuser").value = 0

    def sig(self, n):
        return getattr(self.dut, self.p + n)

    async def send(self, data: bytes, bad: bool = False, side: dict | None = None):
        i = 0
        while i < len(data):
            if self.gap and self.rng.random() < self.gap:
                self.sig("tvalid").value = 0
                await RisingEdge(self.dut.clk)
                await Timer(1, unit="ns")
                continue
            self.sig("tvalid").value = 1
            self.sig("tdata").value = data[i]
            self.sig("tlast").value = int(i == len(data) - 1)
            if self.user:
                self.sig("tuser").value = int(bad and i == len(data) - 1)
            for k, v in (side or {}).items():
                getattr(self.dut, k).value = v
            await ReadOnly()
            took = int(self.sig("tready").value)
            await RisingEdge(self.dut.clk)
            await Timer(1, unit="ns")
            if took:
                i += 1
        self.sig("tvalid").value = 0
        self.sig("tlast").value = 0
        if self.user:
            self.sig("tuser").value = 0


class Sink:
    """Collects m_axis_* frames under random back-pressure; each frame is (bytes, info) with info holding tuser on
    the last beat and the sideband signals named in `side` (checked steady within the frame)."""

    def __init__(self, dut, rng: random.Random, ready: float = 1.0, prefix: str = "m_axis_", user: bool = False,
                 side: tuple = ()):
        self.dut, self.rng, self.ready, self.p, self.user, self.side = dut, rng, ready, prefix, user, side
        self.frames: list[tuple[bytes, dict]] = []
        self.task = cocotb.start_soon(self._run())

    def sig(self, n):
        return getattr(self.dut, self.p + n)

    async def _run(self):
        cur, info, held = bytearray(), {}, None
        self.sig("tready").value = 0
        while True:
            await RisingEdge(self.dut.clk)
            await ReadOnly()
            # values after this edge stand until the next one, where the beat moves if tready is high
            v = int(self.sig("tvalid").value)
            beat = None
            if v:
                beat = (int(self.sig("tdata").value), int(self.sig("tlast").value),
                        int(self.sig("tuser").value) if self.user else 0,
                        tuple(int(getattr(self.dut, s).value) for s in self.side))
            if held is not None:
                assert v, "AXI-Stream: tvalid fell before the beat was taken"
                assert beat == held, f"AXI-Stream: a beat changed before it was taken ({held} -> {beat})"
            await Timer(1, unit="ns")
            r = 1 if self.rng.random() < self.ready else 0
            self.sig("tready").value = r
            held = None
            if v and r:
                if not cur:
                    info = {"side": beat[3]}
                assert beat[3] == info["side"], f"sideband changed inside a frame: {info['side']} -> {beat[3]}"
                cur.append(beat[0])
                if beat[1]:
                    info["tuser"] = beat[2]
                    self.frames.append((bytes(cur), info))
                    cur, info = bytearray(), {}
            elif v:
                held = beat

    def stop(self):
        self.task.cancel()


async def clocks(dut, n: int):
    for _ in range(n):
        await RisingEdge(dut.clk)
