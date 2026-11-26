import re
import sys
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _toplevel(sources):
    """The register core: the module with an h_we port that does not instantiate jtag_bus."""
    for s in sources:
        txt = Path(s).read_text()
        for m in re.finditer(r"\bmodule\s+(\w+)(.*?)\bendmodule", txt, re.S):
            name, body = m.group(1), m.group(2)
            if "h_we" in body and "jtag_bus" not in body and "BSCANE2" not in body:
                return name
    return "p5_async_fifo_soak_core"


def _run(seed):
    from flow import cocotb_run
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    return cocotb_run.run(
        "p5_async_fifo",
        _toplevel(sources),
        sources,
        "bench_p5_async_fifo",
        Path(__file__).resolve().parent,
        parameters={},
        seed=seed,
    )


def test_seed_1():
    _run(1)


def test_seed_2():
    _run(2)


def test_seed_3():
    _run(3)
