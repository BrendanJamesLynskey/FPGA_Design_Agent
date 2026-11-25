"""Brief 167b: stage 1 may plan build.yaml before the RTL exists (VHDL and SystemVerilog share the path).

Brief 167: 5 of 6 VHDL runs ended at stage 1 because `sources: [... rtl/*.vhd]` matched no file and `load_build_cfg` refused it 6 to 8 times."""

from __future__ import annotations

import pytest

from agent.core import dispatch
from agent.core.tools import SecurityError, load_build_cfg, rtl_pending


def _yaml(session, glob: str) -> None:
    f = session.design / "build.yaml"
    txt = f.read_text()
    own = f"{session.design.relative_to(session.root)}/rtl/*.sv"
    f.write_text(txt.replace(own, glob))


def _empty_rtl(session) -> None:
    for p in (session.design / "rtl").glob("*"):
        p.unlink()


@pytest.mark.parametrize("glob", ["rtl/*.vhd", "rtl/*.sv"])
def test_stage_1_accepts_an_rtl_glob_with_no_rtl_yet(session, glob) -> None:
    _empty_rtl(session)
    src = session.design.relative_to(session.root)
    _yaml(session, f"{src}/{glob}")
    session.stage = "board-and-device-planning"
    assert load_build_cfg(session)["top"]                      # no refusal


@pytest.mark.parametrize("glob", ["rtl/*.vhd", "rtl/*.sv"])
def test_stage_2_and_later_still_refuse_it(session, glob) -> None:
    _empty_rtl(session)
    src = session.design.relative_to(session.root)
    _yaml(session, f"{src}/{glob}")
    for stage in ("rtl-design-creation", "synthesis"):
        session.stage = stage
        with pytest.raises(SecurityError, match="matches no file"):
            load_build_cfg(session)


def test_the_before_picture_every_check_was_refused(session) -> None:
    """What brief 167 saw: with the stage-2 rule applied at stage 1 the tool refuses (rule build-yaml), every time."""
    _empty_rtl(session)
    src = session.design.relative_to(session.root)
    _yaml(session, f"{src}/rtl/*.vhd")
    session.stage = "rtl-design-creation"
    refusals = [dispatch(session, "check_constraints", {}) for _ in range(6)]
    assert all(r["refused"] and r["rule"] == "build-yaml" for r in refusals)
    session.stage = "board-and-device-planning"
    assert not any(dispatch(session, "check_constraints", {}).get("rule") == "build-yaml" for _ in range(6))


def test_only_the_designs_own_rtl_glob_is_pending(session) -> None:
    session.stage = "board-and-device-planning"
    src = session.design.relative_to(session.root)
    assert rtl_pending(session, f"{src}/rtl/*.vhd")
    assert not rtl_pending(session, f"{src}/other/*.vhd")      # another directory
    assert not rtl_pending(session, f"{src}/rtl/*.txt")        # not HDL
    assert not rtl_pending(session, "shell/rtl/*.sv")          # the shell is not the design's rtl
    session.stage = "rtl-design-creation"
    assert not rtl_pending(session, f"{src}/rtl/*.vhd")


def test_a_pending_glob_cannot_hide_an_escape(session) -> None:
    session.stage = "board-and-device-planning"
    _yaml(session, "../../../../etc/*.sv")
    with pytest.raises(SecurityError):
        load_build_cfg(session)
