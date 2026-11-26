import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
for _p in HERE.parents:
    if (_p / "flow" / "cocotb_run.py").exists():
        sys.path.insert(0, str(_p))
        break

from flow import cocotb_run  # noqa: E402

DESIGN = HERE.parent
TOPLEVEL = "p4_fir32_core"
SEEDS = (1, 2, 3)


def _sources():
    sources = sorted((DESIGN / "rtl").glob("*.sv"))
    assert sources, "no RTL sources in rtl/"
    return sources


def test_p4_fir_dsp_rtl():
    sources = _sources()
    errors = []
    # one run() per seed, so build/verif/sim/seed<N>/results.xml exists for each
    for seed in SEEDS:
        try:
            cocotb_run.run("p4_fir_dsp_rtl", TOPLEVEL, sources, "p4_fir_bench",
                           DESIGN / "tests", parameters={}, seed=seed)
        except BaseException as exc:  # keep running the other seeds
            errors.append(f"seed {seed}: {exc!r}")
    assert not errors, "; ".join(errors)
