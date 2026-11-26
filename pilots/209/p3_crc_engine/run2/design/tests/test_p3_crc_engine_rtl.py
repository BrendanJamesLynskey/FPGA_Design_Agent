"""pytest entry: runs the cocotb bench against rtl/*.sv for several seeds."""
import re
import sys
from pathlib import Path

import pytest

DESIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN))
sys.path.insert(0, str(DESIGN / "tests"))

from flow import cocotb_run  # noqa: E402


def _toplevel():
    """The register core: the module that has the h_rdata port and is not jtag_bus or the top."""
    cands = []
    for f in sorted((DESIGN / "rtl").glob("*.sv")):
        txt = f.read_text()
        for m in re.finditer(r"\bmodule\s+(\w+)(.*?);", txt, re.S):
            name = m.group(1)
            body = txt[m.end():m.end() + 4000]
            head = txt[m.start():m.end() + 3000]
            if "h_rdata" in head and "jtag_bus" not in name and name != "top":
                if "output" in head.split("endmodule")[0] and re.search(r"output[^;]*h_rdata", head):
                    cands.append(name)
    return cands[0] if cands else "top"


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_p3_crc_engine_rtl(seed):
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    cocotb_run.run(
        "p3_crc_engine",
        _toplevel(),
        sources,
        "crc_bench",
        DESIGN / "tests",
        parameters={},
        seed=seed,
    )
