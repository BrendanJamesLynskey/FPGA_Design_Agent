import re
from pathlib import Path

import pytest

from flow import cocotb_run

DESIGN = Path(__file__).resolve().parents[1]


def _toplevel(sources):
    best = None
    for s in sources:
        txt = s.read_text()
        for mm in re.finditer(r"^\s*module\s+(\w+)", txt, re.M):
            name = mm.group(1)
            body = txt[mm.end():]
            end = body.find("endmodule")
            body = body[:end] if end >= 0 else body
            if "h_we" in body and not re.search(r"\bjtag_bus\s+(#|\w+\s*\()", body):
                if best is None or "core" in name:
                    best = name
    return best or "crc32_core"


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_p3_crc_engine_rtl(seed):
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    cocotb_run.run(
        "p3_crc_engine",
        _toplevel(sources),
        sources,
        ["crc_bench"],
        DESIGN / "tests",
        parameters={},
        seed=seed,
    )
