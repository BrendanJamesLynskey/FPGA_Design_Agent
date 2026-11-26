import re
import sys
from pathlib import Path

DESIGN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN_DIR))
sys.path.insert(0, str(DESIGN_DIR / "tests"))

for _p in DESIGN_DIR.parents:
    if (_p / "flow" / "cocotb_run.py").exists():
        sys.path.insert(0, str(_p))
        break

from flow import cocotb_run  # noqa: E402


def _toplevel(sources):
    """The register core: the module with the h_we port that is not the top."""
    cands = []
    for s in sources:
        txt = s.read_text()
        for mm in re.finditer(r"^\s*module\s+(\w+)(.*?);", txt, re.S | re.M):
            body = txt[mm.end():mm.end() + 6000].split("endmodule")[0]
            head = mm.group(0)
            if "h_we" in head or "h_we" in body[:3000]:
                if "BSCANE2" in body or mm.group(1) in ("jtag_bus", "fir32_top"):
                    continue
                cands.append(mm.group(1))
    for pref in ("fir32_core", "fir_core", "core"):
        if pref in cands:
            return pref
    return cands[0] if cands else "fir32_core"


def test_p4_fir_dsp_rtl():
    sources = sorted((DESIGN_DIR / "rtl").glob("*.sv"))
    top = _toplevel(sources)
    for seed in (1, 2, 3):
        cocotb_run.run(
            "p4_fir_dsp",
            top,
            sources,
            ["fir_bench"],
            DESIGN_DIR / "tests",
            parameters={},
            seed=seed,
        )
