"""The board test's stages (host/b127_stages.py) run in the whole-core simulation: the dry run of the pre-registered test (brief 127). Skipped without xsim. Sizes are small (the simulation is slow);
the board runs the full ones."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from designs.b96_kr260_10g.rm_gp_itch.host import b127_stages as S
from designs.b96_kr260_10g.rm_gp_itch.tests import xsim_session as X

pytestmark = pytest.mark.skipif(not X.have_xsim(), reason="needs Vivado xsim 2026.1")

SIM_SIZES = {"smoke": {"n_msgs": 30}, "counters": {"n_msgs": 25}, "latency": {"passes": 2}, "rate": {"passes": 3}, "risk": {}}


@pytest.mark.parametrize("stage", ["smoke", "counters", "latency", "rate", "risk"])
def test_stage_dry_run(stage, tmp_path) -> None:
    run, owner = X.sim_runner(tmp_path / stage)
    r = S.STAGES[stage](run, **SIM_SIZES[stage])
    if os.environ.get("B127_RECORD"):                  # the dry run's record: every stage's verdict and numbers (results/b127/stages_dry_run.json)
        out = Path(os.environ["B127_RECORD"]) / "stages_dry_run"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{stage}.json").write_text(json.dumps({**r, "sizes": SIM_SIZES[stage], "simulation": "whole core, xsim 2026.1, real XPM macros, GT stand-in, phase 0 ps"}, indent=1, default=str))
    assert r["pass"], r
