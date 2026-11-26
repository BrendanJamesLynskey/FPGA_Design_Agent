import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
DESIGN = HERE.parents[1]
for p in HERE.parents:
    if (p / "flow").is_dir():
        sys.path.insert(0, str(p))
        break
sys.path.insert(0, str(DESIGN))
sys.path.insert(0, str(HERE.parent))

from flow import cocotb_run  # noqa: E402


def _toplevel(sources):
    """The register core is the simulated toplevel: the module with the h_we port, not the top."""
    cands = []
    for s in sources:
        txt = s.read_text()
        for mm in re.finditer(r"module\s+(\w+)\s*(?:#\s*\(.*?\)\s*)?\((.*?)\);", txt, re.S):
            if "h_we" in mm.group(2) and "BSCANE2" not in mm.group(1):
                cands.append(mm.group(1))
    return cands[0] if cands else "fir32_core"


def test_p4_fir_dsp_rtl():
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    top = _toplevel([s for s in sources if "stub" not in s.name])
    for seed in (1, 2, 3):
        cocotb_run.run(
            "p4_fir_dsp",
            top,
            sources,
            ["p4_fir_dsp_bench"],
            HERE.parent,
            parameters={},
            seed=seed,
        )
