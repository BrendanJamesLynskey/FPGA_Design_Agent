"""The board test's stages (host/b127_stages.py) run in the whole-core simulation: the dry run of the pre-registered test (brief 127). Skipped without xsim. Sizes are small (the simulation is slow);
the board runs the full ones."""
from __future__ import annotations

import pytest

from designs.b96_kr260_10g.rm_gp_itch.host import b127_stages as S
from designs.b96_kr260_10g.rm_gp_itch.tests import xsim_session as X

pytestmark = pytest.mark.skipif(not X.have_xsim(), reason="needs Vivado xsim 2026.1")

SIM_SIZES = {"smoke": {"n_msgs": 30}, "counters": {"n_msgs": 25}, "latency": {"passes": 2}, "rate": {"passes": 3}, "risk": {}}


@pytest.mark.parametrize("stage", ["smoke", "counters", "latency", "rate", "risk"])
def test_stage_dry_run(stage, tmp_path) -> None:
    run, owner = X.sim_runner(tmp_path / stage)
    r = S.STAGES[stage](run, **SIM_SIZES[stage])
    assert r["pass"], r
