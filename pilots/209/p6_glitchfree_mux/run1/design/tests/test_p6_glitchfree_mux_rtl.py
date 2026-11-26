import sys
from pathlib import Path

DESIGN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESIGN_DIR))
sys.path.insert(0, str(DESIGN_DIR / "tests"))
for _p in DESIGN_DIR.parents:
    if (_p / "flow").is_dir():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break

from flow import cocotb_run  # noqa: E402


def test_p6_glitchfree_mux_rtl():
    sources = sorted((DESIGN_DIR / "rtl").glob("*.sv"))
    assert sources, "no rtl/*.sv sources found"
    errors = []
    # one run per seed: each writes build/verif/sim/seed<N>/results.xml
    for seed in (1, 2, 3):
        try:
            cocotb_run.run(
                "p6_glitchfree_mux",
                "p6_clkmux_core",
                sources,
                "p6_bench",
                DESIGN_DIR / "tests",
                parameters={"GATE_LEN_DEFAULT": 200},
                seed=seed,
            )
        except Exception as e:  # keep going so every seed leaves its results
            errors.append(f"seed {seed}: {e}")
    assert not errors, "; ".join(errors)
