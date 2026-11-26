import sys
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN))
sys.path.insert(0, str(DESIGN / "tests"))
for _p in DESIGN.parents:
    if (_p / "flow" / "cocotb_run.py").exists():
        sys.path.insert(0, str(_p))
        break

import flow.cocotb_run as cocotb_run  # noqa: E402

TOPLEVEL = "fir32_core"  # register core: clk25, h_* port, led, sfp_tx_disable


def test_p4_fir_dsp_rtl():
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    for seed in (1, 2, 3):
        cocotb_run.run(
            "p4_fir_dsp",
            TOPLEVEL,
            sources,
            ["fir_bench"],
            DESIGN / "tests",
            parameters={},
            seed=seed,
        )
