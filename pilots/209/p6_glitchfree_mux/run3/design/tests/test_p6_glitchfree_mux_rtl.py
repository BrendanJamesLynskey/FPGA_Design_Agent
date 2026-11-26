import re
import sys
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN))
sys.path.insert(0, str(DESIGN / "tests"))
for _p in DESIGN.parents:
    if (_p / "flow").is_dir():
        sys.path.insert(0, str(_p))
        break

from flow import cocotb_run  # noqa: E402

PARAMS = {"GATE_LEN_DEFAULT": 200}


def _top(sources):
    top = "p6_clkmux_core"
    names = []
    for s in sources:
        txt = s.read_text()
        names += [mm.group(1) for mm in re.finditer(r"^\s*module\s+(\w+)\b", txt, re.M)]
    if top not in names:
        cores = [n for n in names if n.endswith("core")]
        if cores:
            top = cores[0]
    return top


def test_p6_glitchfree_mux_rtl():
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    top = _top(sources)
    for seed in (1, 2, 3):
        cocotb_run.run(
            "p6_glitchfree_mux",
            top,
            sources,
            "test_p6_glitchfree_mux_bench",
            DESIGN / "tests",
            parameters=PARAMS,
            seed=seed,
        )
