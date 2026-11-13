import sys
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model import Model


PARAMS = {
    "DEBOUNCE_CYCLES": 8,
    "PWM_PERIOD_CYCLES": 16,
    "DISPLAY_DIGIT_CYCLES": 5,
    "UART_BAUD_DIVIDER_CYCLES": 8,
}


@cocotb.test()
async def counter_reset_buttons_and_outputs_match_model(dut):
    m = Model(**PARAMS)
    dut.clk.value = 0
    dut.cpu_resetn.value = 0
    dut.btn_up.value = 0
    dut.btn_down.value = 0
    dut.btn_center.value = 0
    dut.switches.value = 0
    dut.uart_rxd.value = 1

    async def cycle(resetn=1, up=0, down=0, center=0, switches=0):
        values = {
            "cpu_resetn": resetn,
            "btn_up": up,
            "btn_down": down,
            "btn_center": center,
            "switches": switches,
            "uart_rxd": 1,
        }
        for name, value in values.items():
            getattr(dut, name).value = value
        dut.clk.value = 0
        await Timer(5, unit="ns")
        dut.clk.value = 1
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        expected = m.step(values)
        for name, value in expected.items():
            observed = int(getattr(dut, name).value)
            assert observed == value, (
                f"{name}: observed 0x{observed:x}, expected 0x{value:x}"
            )
        return expected

    # Assert reset across multiple edges, then release it synchronously.
    for _ in range(3):
        await cycle(resetn=0)
    for _ in range(3):
        await cycle(resetn=1)

    # Walk through each button with enough stable cycles for the small test
    # debounce setting. Include held-button cycles (one event only), release,
    # counter wrap in both directions, and centre clear.
    for _ in range(12):
        await cycle(up=1)
    for _ in range(12):
        await cycle(up=0)
    for _ in range(12):
        await cycle(down=1)
    for _ in range(12):
        await cycle(down=0)
    for _ in range(12):
        await cycle(center=1)
    for _ in range(12):
        await cycle(center=0)

    # Simultaneous button assertion and stable switch patterns exercise the
    # documented clear > up > down event priority and all output scan slots.
    for i in range(20):
        await cycle(up=1, down=1, center=1, switches=(i * 13) & 0xFF)
    for i in range(20):
        await cycle(up=0, down=0, center=0, switches=(255 - i * 7) & 0xFF)

    # Additional deterministic variety on switches while output PWM and display
    # scan continue to advance. UART is held at the idle level.
    for value in (0, 1, 127, 128, 254, 255, 0x55, 0xAA):
        for _ in range(7):
            await cycle(switches=value)
