"""cocotb bench for tb_rig: run the rig, record its UART byte stream, optionally inject one error and finish with a
temperature stop. The log goes to $CDC_LOG; tests/test_cdc_rig_rtl.py parses it with host/read_counters.py.

Environment: CDC_EPOCHS (readouts to collect), CDC_INJECT (copy index whose checker input gets one forced extra
event, or -1), CDC_TJ_STOP (1: raise temp past the stop code after the last epoch and wait for the S line).
"""

from __future__ import annotations

import os

import cocotb
from cocotb.triggers import ClockCycles, FallingEdge, ReadOnly, RisingEdge, Timer
from cocotb.handle import Force, Release


async def reader(dut, log, state):
    line = bytearray()
    while True:
        await RisingEdge(dut.tx_stb)
        await ReadOnly()
        b = int(dut.tx_byte.value)
        line.append(b)
        state["bytes"].append(b)
        if b == 0x0A:
            text = line.decode("ascii", "replace")
            log.write(text)
            log.flush()
            state["lines"].append(text.strip())
            line = bytearray()


async def uart_rx(dut, state, div):
    """Decode the serial line itself (8N1, div clk_a cycles a bit), so the UART is checked, not only the bytes."""
    bit_ns = 10 * div
    while True:
        await FallingEdge(dut.uart_txd)
        await Timer(bit_ns // 2, unit="ns")
        if int(dut.uart_txd.value) != 0:
            state["uart_glitch"] += 1
            continue
        b = 0
        for i in range(8):
            await Timer(bit_ns, unit="ns")
            b |= int(dut.uart_txd.value) << i
        await Timer(bit_ns, unit="ns")
        if int(dut.uart_txd.value) != 1:
            state["uart_framing"] += 1
        state["uart_bytes"].append(b)


@cocotb.test()
async def run_rig(dut):
    epochs = int(os.environ.get("CDC_EPOCHS", "3"))
    inject = int(os.environ.get("CDC_INJECT", "-1"))
    tj_stop = os.environ.get("CDC_TJ_STOP", "0") == "1"
    ntot = int(os.environ["CDC_NTOT"])
    dut.temp.value = 0x9A0          # about 30 degC
    state = {"lines": [], "bytes": [], "uart_bytes": [], "uart_glitch": 0, "uart_framing": 0}
    with open(os.environ["CDC_LOG"], "w") as log:
        cocotb.start_soon(reader(dut, log, state))
        cocotb.start_soon(uart_rx(dut, state, int(os.environ.get("CDC_UART_DIV", "2"))))

        def c_after_last_e():
            n, seen = 0, False
            for ln in state["lines"]:
                if ln.startswith("E,"):
                    n, seen = 0, True
                elif ln.startswith("C,") and seen:
                    n += 1
            return n

        def n_e():
            return sum(ln.startswith("E,") for ln in state["lines"])

        injected = False
        while not (n_e() >= epochs and c_after_last_e() >= ntot):
            await Timer(20, unit="us")
            if inject >= 0 and not injected and n_e() >= 1 and c_after_last_e() >= ntot:
                # one extra event at the checker input of copy `inject` (a C1 copy), once traffic has resumed after
                # the first readout: the next quiet point must count it as an error
                ev = dut.u_core.g_copy[inject].u_copy.g_v.ev
                await Timer(100, unit="us")
                await RisingEdge(dut.clk_a_o)
                ev.value = Force(1)
                await Timer(40, unit="ns")
                ev.value = Release()
                injected = True
                dut._log.info("forced one extra event into copy %d", inject)
        dut._log.info("collected %d epochs", n_e())
        if tj_stop:
            dut.temp.value = 0xC00          # about 104 degC, past the 80 degC stop code (0xB37)
            for _ in range(400):
                await Timer(20, unit="us")
                if any(ln.startswith("S,") for ln in state["lines"]):
                    break
            assert any(ln.startswith("S,") for ln in state["lines"]), "no S (temperature stop) line"
            assert int(dut.clkc_off.value) == 1, "clk_c was not stopped"
        await Timer(2, unit="us")
        n = len(state["uart_bytes"])
        assert n > 0 and state["uart_bytes"] == state["bytes"][:n], "the serial line does not carry the byte stream"
        assert state["uart_framing"] == 0 and state["uart_glitch"] == 0, state
        dut._log.info("UART line decoded: %d bytes match the byte stream", n)
        await ClockCycles(dut.clk_a_o, 10)
