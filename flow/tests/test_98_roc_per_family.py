"""Brief 98: the XADC/SYSMON operating-conditions verdict uses limits per family. The K26 (xck26-sfvc784-2LV-c) runs VCCINT at 0.72 V and
VCCBRAM at 0.85 V (AMD DS925 v1.30 table 2), which the 7-series limits (0.95 to 1.05 V) called outside on the first KR260 board run
(brief 96, 2026-11-17: now VCCINT 0.715, VCCBRAM 0.847). The readings below are that run's."""

from __future__ import annotations

from flow import program

KR260 = "xck26-sfvc784-2LV-c"
READ = ("FDA-COND NOW TEMPERATURE=25.0 VCCINT=0.715 VCCAUX=1.793 VCCBRAM=0.847\n"
        "FDA-COND MAX TEMPERATURE=25.7 VCCINT=0.718 VCCAUX=1.796 VCCBRAM=0.847\n"
        "FDA-COND MIN TEMPERATURE=25.0 VCCINT=0.714 VCCAUX=1.790 VCCBRAM=0.846\nFDA-COND FLAGS 0000\n")


def test_the_k26_run_readings_were_outside_the_old_7_series_limits_and_are_inside_its_own():
    old = program.parse_conditions(READ)                       # no part: the 7-series -1 table, as before
    assert not old["inside_roc"] and "now VCCINT 0.715" in old["outside"] and "now VCCBRAM 0.847" in old["outside"]
    new = program.parse_conditions(READ, KR260)
    assert new["inside_roc"] and new["outside"] == []
    assert new["limits"]["VCCINT"] == [0.698, 0.742] and new["limits"]["VCCBRAM"] == [0.825, 0.876]
    assert "DS925" in new["limits_source"] and "2lv" in new["limits_source"].lower()


def test_k26_limits_still_catch_a_wrong_supply():
    bad = READ.replace("VCCINT=0.715", "VCCINT=0.95", 1)        # a 0.85 V or 0.95 V rail on a 0.72 V part is a real fault
    r = program.parse_conditions(bad, KR260)
    assert not r["inside_roc"] and r["outside"] == ["now VCCINT 0.95"]
    low = READ.replace("VCCBRAM=0.847", "VCCBRAM=0.80", 1)
    assert program.parse_conditions(low, KR260)["outside"] == ["now VCCBRAM 0.8"]


def test_the_7_series_verdict_is_unchanged():
    text = ("FDA-COND NOW TEMPERATURE=41.2 VCCINT=0.998 VCCAUX=1.79 VCCBRAM=0.999\nFDA-COND FLAGS 0000\n")
    for part in (None, "xc7a100tcsg324-1", "xc7z020clg484-1"):
        c = program.parse_conditions(text, part)
        assert c["inside_roc"] and c["limits"]["VCCINT"] == [0.95, 1.05]
    assert program.roc_for("xc7a100tcsg324-1")[0] is program.ROC


def test_zynq_ultrascale_plus_speed_grades():
    vint = lambda part: program.roc_for(part)[0]["VCCINT"]      # noqa: E731
    assert vint("xczu3eg-sfvc784-2-e") == (0.825, 0.876)       # -2E: 0.85 V
    assert vint("xczu3eg-sfvc784-1-i") == (0.825, 0.876)
    assert vint("xczu7ev-ffvc1156-3-e") == (0.873, 0.927)      # -3E: 0.90 V
    assert vint("xczu3eg-sfvc784-2LV-e") == (0.698, 0.742)     # lowest power -2L, listed as -2LV
    assert vint("xczu3eg-sfvc784-1LI-i") == (0.698, 0.876)     # 0.72 V or 0.85 V: either window
    assert program.roc_for("xck26-sfvc784-2LV-c")[0]["VCCAUX"] == (1.746, 1.854)
    assert program.roc_for("xck26-sfvc784-2LV-c")[0]["TEMPERATURE"] == (None, 85.0)       # the house rule's junction limit


def test_program_uses_the_boards_catalogue_part():
    assert program._catalogue_part({"name": "kr260", "part": "xck26"}) == KR260             # discovery holds only the short part
    assert program._catalogue_part({"name": "not_a_board", "part": "xc7a100t"}) == "xc7a100t"
