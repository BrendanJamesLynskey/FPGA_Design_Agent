"""Acceptance tests of c16_nexys_aes_uart against model.py (hidden from the agent)."""

from __future__ import annotations

import cocotb
from benchmark.lib.bench import Board
from cocotb.triggers import ClockCycles, ReadOnly
from model import bench_requests

REPLY_TIMEOUT = 60_000


async def ask(b: Board, req_hex: str, reply_hex: str, what: str) -> None:
    await b.uart.send(bytes.fromhex(req_hex))
    got = await b.uart.recv(16, REPLY_TIMEOUT)
    assert got.hex() == reply_hex, f"{what}: request {req_hex}: RTL {got.hex()}, model {reply_hex}"


async def busy_bit(b: Board) -> int:
    await ReadOnly()
    v = int(b.dut.LED.value) & 1
    await ClockCycles(b.clk, 1)
    return v


@cocotb.test()
async def test_fips_197_examples(dut):
    """The two example blocks printed in FIPS 197 (appendix B and C.1)."""
    b = Board(dut, {})
    await b.start()
    r = bench_requests()
    for i in (0, 1):
        await ask(b, *r[i], f"FIPS 197 example {i}")


@cocotb.test()
async def test_random_requests_a(dut):
    b = Board(dut, {})
    await b.start()
    r = bench_requests()
    for i in (2, 3, 4):
        await ask(b, *r[i], f"request {i}")


@cocotb.test()
async def test_random_requests_b(dut):
    b = Board(dut, {})
    await b.start()
    r = bench_requests()
    for i in (5, 6, 7):
        await ask(b, *r[i], f"request {i}")


@cocotb.test()
async def test_no_state_between_requests(dut):
    """Different keys on consecutive requests, then the first request again."""
    b = Board(dut, {})
    await b.start()
    r = bench_requests()
    for i in (1, 0, 5, 1):
        await ask(b, *r[i], f"request {i} in a mixed order")


@cocotb.test()
async def test_reset_and_busy_led(dut):
    b = Board(dut, {})
    await b.start()
    r = bench_requests()
    await b.uart.send(bytes(range(20)))               # a part-received request
    await b.reset()
    await ask(b, *r[0], "request after reset")
    await b.cycles(200)
    assert await busy_bit(b) == 0, "LED0 must be low when idle"
    await b.uart.send(bytes.fromhex(r[2][0]))
    seen = 0
    for _ in range(2000):
        seen |= await busy_bit(b)
        if seen:
            break
    assert seen, "LED0 was never high while the block was encrypted"
    await b.uart.recv(16, REPLY_TIMEOUT)
    await b.cycles(200)
    assert await busy_bit(b) == 0, "LED0 must be low after the reply"
