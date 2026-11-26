import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import flow.cocotb_run  # noqa: E402

DESIGN = Path(__file__).resolve().parents[1]


def _toplevel(sources):
    """The register core: the module that has the h_we port and is not the jtag_bus or the top."""
    best = None
    for f in sources:
        txt = f.read_text()
        for m in re.finditer(r"\bmodule\s+(\w+)(.*?)\bendmodule", txt, re.S):
            name, body = m.group(1), m.group(2)
            if "h_we" in body and "BSCANE2" not in body and "jtag_bus" not in body:
                if best is None or "core" in name:
                    best = name
    return best or "top"


def _run_all():
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    top = _toplevel(sources)
    flow.cocotb_run.run("p5_async_fifo", top, sources, "p5_async_fifo_bench",
                        DESIGN / "tests", parameters={}, seed=1)
    flow.cocotb_run.run("p5_async_fifo", top, sources, "p5_async_fifo_bench",
                        DESIGN / "tests", parameters={}, seed=2)
    flow.cocotb_run.run("p5_async_fifo", top, sources, "p5_async_fifo_bench",
                        DESIGN / "tests", parameters={}, seed=3)


def test_rtl():
    _run_all()


if __name__ == "__main__":
    _run_all()
