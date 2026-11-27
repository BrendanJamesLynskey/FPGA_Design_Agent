import os
import re
import sys
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1]
for p in DESIGN.parents:
    if (p / "flow").is_dir():
        sys.path.insert(0, str(p))
        break
sys.path.insert(0, str(DESIGN))

from flow import cocotb_run  # noqa: E402


def _toplevel(sources):
    """The register core: the module with the h_we register port that does not instantiate jtag_bus."""
    for f in sources:
        text = f.read_text()
        for m in re.finditer(r"^\s*module\s+(\w+)(.*?)^\s*endmodule", text, re.S | re.M):
            body = m.group(2)
            if "h_we" in body and "jtag_bus" not in body:
                return m.group(1)
    return "p5_async_fifo_soak_core"


def _run(seed, width):
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    os.environ["P5_COUNTER_WIDTH"] = str(width)
    params = {} if width == 32 else {"COUNTER_WIDTH_BITS": width}
    cocotb_run.run(
        "p5_async_fifo",
        _toplevel(sources),
        sources,
        "p5_async_fifo_bench",
        Path(__file__).resolve().parent,
        parameters=params,
        seed=seed,
    )


def test_seed1():
    _run(1, 32)


def test_seed2_narrow_counters():
    _run(2, 8)


def test_seed3():
    _run(3, 32)
