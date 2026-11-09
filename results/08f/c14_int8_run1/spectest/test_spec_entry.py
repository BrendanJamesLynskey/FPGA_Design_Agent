"""Harness-written entry for the independent spec-test bench (spectest/spec_bench.py). No model wrote this file."""
import sys
from pathlib import Path

DESIGN_DIR = Path(__file__).resolve().parents[1]
for _p in [DESIGN_DIR, *DESIGN_DIR.parents]:
    if (_p / "flow" / "cocotb_run.py").exists():
        sys.path.insert(0, str(_p))
        break
sys.path.insert(0, str(Path(__file__).resolve().parent))        # spec_bench, spec_ref: this directory only, never the design's model.py

import yaml  # noqa: E402
from flow import cocotb_run, srcorder  # noqa: E402

import spec_bench  # noqa: E402


def test_spec_bench():
    top = yaml.safe_load((DESIGN_DIR / "build.yaml").read_text())["top"]
    own = sorted((DESIGN_DIR / "rtl").glob("*.sv"))
    sources = own if srcorder.no_shell(DESIGN_DIR) else cocotb_run.SHELL_RTL + own
    for seed in getattr(spec_bench, "SEEDS", (1,)):
        cocotb_run.run("spectest", top, sources, "spec_bench", DESIGN_DIR / "spectest",
                       parameters=dict(getattr(spec_bench, "PARAMS", {}) or {}), seed=seed,
                       build_root=DESIGN_DIR / "build" / "spectest" / "sim")
