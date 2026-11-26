import sys
from pathlib import Path

DESIGN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN_DIR))
for _p in [DESIGN_DIR, *DESIGN_DIR.parents]:
    if (_p / "flow" / "cocotb_run.py").exists():
        sys.path.insert(0, str(_p))
        break

from flow import cocotb_run  # noqa: E402

TOP = "p5_async_fifo_soak_core"
SOURCES = sorted((DESIGN_DIR / "rtl").glob("*.sv"))


def _run(seed):
    cocotb_run.run(
        "p5_async_fifo",
        TOP,
        SOURCES,
        "p5_async_fifo_bench",
        DESIGN_DIR / "tests",
        parameters={},
        seed=seed,
    )


def test_seed_1():
    _run(1)


def test_seed_2():
    _run(2)


def test_seed_3():
    _run(3)


if __name__ == "__main__":
    for s in (1, 2, 3):
        _run(s)
