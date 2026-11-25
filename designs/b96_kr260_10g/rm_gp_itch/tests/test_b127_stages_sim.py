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


CONT_SIZES = {"smoke": {"n_msgs": 30}, "counters": {"n_msgs": 20}, "rate": {"passes": 2}}


def test_full_session_in_board_order(tmp_path) -> None:
    """Brief 172: the board's session, in the board's order (smoke, counters, latency with speculation off then on, rate; risk, the last stage, is left out: it reads no counter that no clear touches and costs the longest run) on ONE simulation from reset with no reset between the stages. Each stage on its
    own (above) could not show that `rp.frames` is cleared only by reset; the rate stage failed on the board for that reason (results/b127/hw/20261122_150408)."""
    from designs.b96_kr260_10g.rm_gp_itch.host import b127_board as BB
    run, owner = X.continuous_runner(tmp_path / "cont")
    out = BB.run_stages(run, ("smoke", "counters", "latency", "rate"), CONT_SIZES, latency_passes=1)
    if os.environ.get("B127_RECORD"):
        d = Path(os.environ["B127_RECORD"])
        d.mkdir(parents=True, exist_ok=True)
        (d / "stages_continuous_sim.json").write_text(json.dumps({"stages": out, "sizes": {**CONT_SIZES, "latency_passes": 1}, "simulation_runs": owner.runs,
                                                                   "simulation": "whole core, xsim 2026.1, real XPM macros, GT stand-in, phase 0 ps, one continuous session from reset"}, indent=1, default=str))
    assert out["all_pass"], out
    assert out["rate"]["numbers"]["rp_frames_before"] > 0, "the earlier stages must have played frames: the test is not testing the carry-over"
