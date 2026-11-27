"""pytest entry: runs the cocotb bench on the register core for three seeds."""
import re
import sys
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN))

from flow import cocotb_run  # noqa: E402


def _toplevel():
    """The register core: the module that has the h_we input."""
    for f in sorted((DESIGN / "rtl").glob("*.sv")):
        text = f.read_text()
        for m in re.finditer(r"\bmodule\s+(\w+)(.*?)\bendmodule", text, re.S):
            if re.search(r"\binput\b[^;,)]*\bh_we\b", m.group(2)):
                return m.group(1)
    return "p5_async_fifo_soak_core"


def test_rtl():
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    for seed in (1, 2, 3):
        cocotb_run.run(
            "p5_async_fifo",
            _toplevel(),
            sources,
            "p5_async_fifo_bench",
            DESIGN / "tests",
            parameters={},
            seed=seed,
        )
