from pathlib import Path

import yaml

from flow import cocotb_run


DESIGN_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = DESIGN_DIR.parents[2]


def test_t1_dimmer_counter_rtl():
    spec = yaml.safe_load((DESIGN_DIR / "spec.yaml").read_text())
    # Short simulation-friendly intervals exercise the same cycle-based behavior
    # without waiting for the board-scale debounce and display intervals.
    parameters = dict(spec["parameters"])
    parameters.update(
        DEBOUNCE_CYCLES=8,
        PWM_PERIOD_CYCLES=16,
        DISPLAY_DIGIT_CYCLES=5,
        UART_BAUD_DIVIDER_CYCLES=8,
    )
    sources = cocotb_run.SHELL_RTL + sorted((DESIGN_DIR / "rtl").glob("*.sv"))
    cocotb_run.run(
        name=spec["name"],
        toplevel=spec["top"],
        sources=sources,
        test_module="t1_dimmer_counter_bench",
        test_dir=DESIGN_DIR / "tests",
        parameters=parameters,
        seed=1,
    )
