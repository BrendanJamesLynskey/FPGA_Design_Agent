import re
import sys
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN))
sys.path.insert(0, str(DESIGN / "tests"))

from flow import cocotb_run  # noqa: E402


def _core_name(sources):
    """The register core: the module with the h_we port that is not the top."""
    for s in sources:
        txt = s.read_text()
        for m in re.finditer(r"\bmodule\s+(\w+)\b(.*?);", txt, re.S):
            if "h_we" in m.group(2) and "input" in m.group(2) and m.group(1) != "p2_top":
                return m.group(1)
    return "p2_core"


def test_p2_bram_rom_rtl():
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    top = _core_name(sources)
    for seed in (1, 2, 3):
        cocotb_run.run(
            "p2_bram_rom",
            top,
            sources,
            "bench_p2_bram_rom",
            DESIGN / "tests",
            parameters={},
            seed=seed,
        )
