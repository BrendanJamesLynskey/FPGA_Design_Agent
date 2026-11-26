import re
from pathlib import Path

import flow.cocotb_run


def _toplevel(sources):
    text = "".join(Path(s).read_text() for s in sources)
    for name in ("p5_async_fifo_soak_core", "p5_async_fifo_core"):
        if re.search(r"\bmodule\s+" + name + r"\b", text):
            return name
    for m in re.finditer(r"\bmodule\s+(\w+)\b(.*?)endmodule", text, re.S):
        if "h_we" in m.group(2) and "BSCANE2" not in m.group(2):
            return m.group(1)
    return "p5_async_fifo_soak_core"


def test_p5_async_fifo_rtl():
    design_dir = Path(__file__).resolve().parents[1]
    sources = sorted((design_dir / "rtl").glob("*.sv"))
    top = _toplevel(sources)
    for seed in (1, 2, 3):
        flow.cocotb_run.run(
            "p5_async_fifo",
            top,
            sources,
            "p5_bench",
            design_dir / "tests",
            parameters={},
            seed=seed,
        )
