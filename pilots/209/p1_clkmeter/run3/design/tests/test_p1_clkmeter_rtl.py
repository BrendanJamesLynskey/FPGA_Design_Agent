"""pytest entry: runs the cocotb bench on the register core for several seeds."""
import re
import sys
from pathlib import Path

import pytest

DESIGN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from flow import cocotb_run  # noqa: E402

PARAMS = {"LED_C3_HALF_PERIOD_CYCLES": 24, "LED_REF_HALF_PERIOD_CYCLES": 125}


def _toplevel(sources):
    """The register core: the module that has the h_we port and is not the top / jtag_bus."""
    best = None
    for s in sources:
        txt = s.read_text()
        for m in re.finditer(r"\bmodule\s+(\w+)", txt):
            name = m.group(1)
            body = txt[m.end():m.end() + 3000]
            if "h_we" in body and "BSCANE2" not in body and name != "freq_meter_top":
                if "core" in name or best is None:
                    best = name
    return best or "freq_meter_core"


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_p1_clkmeter(seed):
    sources = sorted((DESIGN_DIR / "rtl").glob("*.sv"))
    cocotb_run.run(
        "p1_clkmeter",
        _toplevel(sources),
        sources,
        "bench_p1_clkmeter",
        DESIGN_DIR / "tests",
        parameters=PARAMS,
        seed=seed,
    )
