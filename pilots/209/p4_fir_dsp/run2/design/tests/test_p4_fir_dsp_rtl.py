"""Pytest entry: runs the cocotb bench on the register core for several seeds."""
import sys
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN))
sys.path.insert(0, str(DESIGN / "tests"))

for _p in DESIGN.parents:
    if (_p / "flow").is_dir():
        sys.path.insert(0, str(_p))
        break

for _p in [Path.cwd(), *Path.cwd().parents]:
    if (_p / "flow").is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from flow import cocotb_run  # noqa: E402

TOPLEVEL = "fir_core"


def test_p4_fir_dsp_rtl():
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    errors = []
    for seed in (1, 2, 3):
        try:
            cocotb_run.run(
                "p4_fir_dsp",
                TOPLEVEL,
                sources,
                ["fir_bench"],
                DESIGN / "tests",
                parameters={},
                seed=seed,
            )
        except Exception as e:  # keep running the other seeds so each leaves results.xml
            errors.append(f"seed {seed}: {e}")
    assert not errors, "; ".join(errors)
