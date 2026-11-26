import re
from pathlib import Path

from flow import cocotb_run

DESIGN = Path(__file__).resolve().parents[1]
NAME = "p5_async_fifo"
TOP_DEFAULT = "p5_async_fifo_soak"


def _toplevel(sources):
    """The register core is the simulated toplevel (jtag_bus is not simulated)."""
    mods = []
    for s in sources:
        mods += re.findall(r"^\s*module\s+(\w+)", Path(s).read_text(), re.M)
    for m in mods:
        if m.endswith("_core"):
            return m
    return TOP_DEFAULT


def _run(seed):
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    res = cocotb_run.run(
        NAME, _toplevel(sources), sources,
        test_module=["bench_p5_async_fifo"],
        test_dir=DESIGN / "tests",
        parameters={},
        seed=seed,
    )
    for attr in ("ok", "passed", "success"):
        if hasattr(res, attr):
            assert getattr(res, attr), res
    if isinstance(res, dict):
        for k in ("ok", "passed", "success"):
            if k in res:
                assert res[k], res
    return res


def test_seeds():
    for seed in (1, 2, 3):
        _run(seed)
