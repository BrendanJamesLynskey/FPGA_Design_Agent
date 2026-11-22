"""The stage order of the board test (brief 172). Board run B of brief 127 failed stage `rate` with "frames played 4634 of 1900" because `rp.frames` is cleared only by reset, not by CLR_CNT, so it carried the frames of the
three earlier stages (2734) into the stage that compares it with its own 1900; each stage had been dry-run from reset, so the leak was invisible. Here, without a simulator, a stand-in for the register file keeps
`rp.frames` cumulative as the RTL does, and the stages that check it must judge the rise over their own replay."""
from __future__ import annotations

from designs.b96_kr260_10g.rm_gp_itch.host import b127_stages as S
from designs.b96_kr260_10g.rm_gp_itch.host import itch_bench as B


def _rate_runner(before: int, short: int = 0):
    """execute() answers the rate plan's reads as a board whose player has already sent `before` frames; `short` frames of the replay are missing."""
    state = {"rp": before}

    def execute(plan):
        loops = next(op[2] for op in plan.ops if op[0] == "W" and op[1] == B.ADDR["RP_CFG"])
        sent = loops * 19 - short                                    # stage_rate's session: the preamble packet and 18 single-message packets, `loops` passes
        res = {tag: 0 for tag in plan.reads}
        res["base.rp.frames"] = state["rp"]
        state["rp"] += sent
        res["rp.frames"] = state["rp"]
        res["us.fwd"] = sent
        res["itch.dup"] = sent - 19
        return res
    return S.Runner(execute=execute, sim=False, link_ready=True)


def test_rate_after_earlier_stages_judges_its_own_frames() -> None:
    r = S.stage_rate(_rate_runner(before=2734), passes=100)          # the board's numbers: 69 + 165 + 2 x 1250 frames before the stage
    assert r["pass"], r
    assert r["numbers"]["rp_frames_before"] == 2734 and r["numbers"]["rp_frames_after"] == 4634


def test_rate_alone_and_after_the_stages_agree() -> None:
    assert S.stage_rate(_rate_runner(before=0), passes=100)["pass"]


def test_rate_still_fails_when_the_player_is_short() -> None:
    r = S.stage_rate(_rate_runner(before=2734, short=1), passes=100)  # one frame fewer played AND forwarded: the criterion is unchanged
    assert not r["pass"] and any("frames played 1899 of 1900" in x for x in r["reasons"]), r
