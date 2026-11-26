import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for _p in Path(__file__).resolve().parents:
    if (_p / "flow" / "cocotb_run.py").exists():
        sys.path.insert(0, str(_p))
        break

import flow.cocotb_run  # noqa: E402

DESIGN = Path(__file__).resolve().parents[1]
PARAMS = {"GATE_LEN_DEFAULT": 200}


def _run(seed):
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    return flow.cocotb_run.run(
        "p6_glitchfree_mux",
        "p6_clkmux_core",
        sources,
        "test_p6_glitchfree_mux_bench",
        DESIGN / "tests",
        parameters=PARAMS,
        seed=seed,
    )


def test_p6_glitchfree_mux_rtl():
    for seed in (1, 2, 3):
        _run(seed)
