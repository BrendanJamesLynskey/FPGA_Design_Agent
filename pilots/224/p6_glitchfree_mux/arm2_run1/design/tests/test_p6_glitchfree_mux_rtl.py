import re
import sys
from pathlib import Path

DESIGN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN_DIR))
sys.path.insert(0, str(DESIGN_DIR.parents[1]))

from flow import cocotb_run  # noqa: E402


def _toplevel(sources):
    """The register core: the module with the h_we port that is not the thin top."""
    for f in sources:
        text = f.read_text()
        for mm in re.finditer(r"\bmodule\s+(\w+)(.*?)\bendmodule", text, re.S):
            if "h_we" in mm.group(2) and "jtag_bus" not in mm.group(2) and "input" in mm.group(2):
                return mm.group(1)
    return "p6_clkmux_core"


def test_p6_glitchfree_mux_rtl():
    sources = sorted((DESIGN_DIR / "rtl").glob("*.sv"))
    top = _toplevel(sources)
    for seed in (1, 2, 3):
        cocotb_run.run(
            "p6_glitchfree_mux",
            top,
            sources,
            "p6_glitchfree_mux_bench",
            DESIGN_DIR / "tests",
            parameters={"GATE_LEN_DEFAULT": 200},
            seed=seed,
        )
