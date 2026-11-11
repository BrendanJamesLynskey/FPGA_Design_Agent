"""cocotb tests of the brief 24 reference burst controller (ctl_sep / ctl_mono through tb_ctl).

Directed tests with cycle-exact expectations for OUT=0 (combinational Moore outputs): the burst, the nack retry, the timeout,
back-pressure on the response. TESTS_BASE are the tests a first bench has (no timeout test); test_timeout reaches ERR.
"""

from __future__ import annotations

import os

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge


STATES = {n: i for i, n in enumerate("IDLE LOAD REQ ADDR DATA TURN WACK RETRY RESP ERR COOL".split())}
TRANS = [("IDLE", "LOAD"), ("LOAD", "REQ"), ("REQ", "ADDR"), ("ADDR", "DATA"), ("DATA", "TURN"), ("TURN", "WACK"), ("WACK", "RESP"),
         ("WACK", "RETRY"), ("WACK", "ERR"), ("RETRY", "REQ"), ("RESP", "COOL"), ("ERR", "COOL"), ("COOL", "IDLE")]
SAMPLERS: list = []


async def start(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    if os.environ.get("FDA_FSM_SAMPLER"):                           # the in-bench route (flow/fsm_cov_cocotb.py); cocotb ends a test's tasks
        from flow.fsm_cov_cocotb import start_fsm_coverage          # with the test, so every test starts its own sampler
        SAMPLERS.append(start_fsm_coverage(dut.clk, dut.g.dut.st if hasattr(dut, "g") else dut.dut.st, "ctl", STATES, TRANS, "IDLE"))
    for n in ("cmd_valid", "gnt", "ack", "nack", "rsp_ready"):
        getattr(dut, n).value = 0
    dut.rst_n.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst_n.value = 1


async def cycle(dut) -> None:
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)


def v(sig) -> int:
    return int(sig.value)


async def request(dut) -> None:
    """cmd_valid until cmd_ready (the cmd handshake), then drop it."""
    dut.cmd_valid.value = 1
    while not v(dut.cmd_ready):
        await cycle(dut)
    await cycle(dut)
    dut.cmd_valid.value = 0


async def wait_for(dut, sig, limit: int = 40) -> int:
    n = 0
    while not v(sig):
        await cycle(dut)
        n += 1
        assert n < limit, f"{sig._name} never rose"
    return n


@cocotb.test()
async def test_burst_and_ack(dut) -> None:
    await start(dut)
    await request(dut)
    n = await wait_for(dut, dut.bus_req)
    dut.gnt.value = 1
    await cycle(dut)
    dut.gnt.value = 0
    assert v(dut.bus_addr_v) == 1, "address phase after the grant"
    await cycle(dut)
    beats, last = 0, 0
    while v(dut.bus_valid):
        beats += 1
        last = v(dut.bus_last)
        await cycle(dut)
    assert beats == 4 and last == 1, (beats, last)           # four beats, bus_last on the fourth
    assert v(dut.bus_req) == 0
    await cycle(dut)                                         # TURN
    dut.ack.value = 1
    await cycle(dut)
    dut.ack.value = 0
    await wait_for(dut, dut.rsp_valid)
    assert v(dut.rsp_err) == 0
    dut.rsp_ready.value = 1
    await cycle(dut)
    dut.rsp_ready.value = 0
    for _ in range(3):                                       # COOL: three cycles, no command accepted
        assert v(dut.cmd_ready) == 0
        await cycle(dut)
    assert v(dut.cmd_ready) == 1


@cocotb.test()
async def test_nack_retries_the_burst(dut) -> None:
    await start(dut)
    await request(dut)
    await wait_for(dut, dut.bus_req)
    dut.gnt.value = 1
    await cycle(dut)
    dut.gnt.value = 0
    await wait_for(dut, dut.bus_valid)
    while v(dut.bus_valid):
        await cycle(dut)
    await cycle(dut)                                         # TURN
    dut.nack.value = 1
    await cycle(dut)
    dut.nack.value = 0
    await cycle(dut)                                         # RETRY, then REQ again
    await wait_for(dut, dut.bus_req)
    assert v(dut.rsp_valid) == 0
    await cycle(dut)                                         # one more edge: a sampler on the clock sees the state it ended in


@cocotb.test()
async def test_response_backpressure(dut) -> None:
    await start(dut)
    await request(dut)
    await wait_for(dut, dut.bus_req)
    dut.gnt.value = 1
    await cycle(dut)
    dut.gnt.value = 0
    await wait_for(dut, dut.bus_valid)
    while v(dut.bus_valid):
        await cycle(dut)
    await cycle(dut)                                         # TURN
    dut.ack.value = 1
    await cycle(dut)
    dut.ack.value = 0
    await wait_for(dut, dut.rsp_valid)
    for _ in range(5):                                       # rsp_ready low: rsp_valid stays up
        assert v(dut.rsp_valid) == 1
        await cycle(dut)


@cocotb.test()
async def test_timeout_reports_an_error(dut) -> None:
    await start(dut)
    await request(dut)
    await wait_for(dut, dut.bus_req)
    dut.gnt.value = 1
    await cycle(dut)
    dut.gnt.value = 0
    await wait_for(dut, dut.bus_valid)
    while v(dut.bus_valid):
        await cycle(dut)
    await wait_for(dut, dut.rsp_valid, limit=20)             # no ack, no nack: eight WACK cycles, then ERR
    assert v(dut.rsp_err) == 1
    dut.rsp_ready.value = 1
    await cycle(dut)
    dut.rsp_ready.value = 0
    for _ in range(4):
        await cycle(dut)
    assert v(dut.cmd_ready) == 1
    if SAMPLERS:                                             # the last test writes the functional bins the V3 gate reads
        from cocotb_coverage.coverage import coverage_db
        coverage_db.export_to_yaml(os.environ["FDA_COV_OUT"])
