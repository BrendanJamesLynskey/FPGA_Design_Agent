"""Brief 50A: the showcase page's data files are generated, never hand-edited: regenerating them from the committed run
files gives the committed bytes."""

from __future__ import annotations

from pathlib import Path

from debug_core import showcase_data

RES = Path(__file__).resolve().parents[2] / "results" / "50a_nl_debug"


def test_summary_and_hero_regenerate_byte_for_byte() -> None:
    for name, text in showcase_data.render(RES).items():
        assert (RES / name).read_text() == text, f"{name} differs from what python -m debug_core.showcase_data writes"


def test_the_answer_check_example_is_the_real_answer_line() -> None:
    import json
    t = json.loads((RES / "summary.json").read_text())["trust"]
    answer = (RES / "t1_count_write" / "answer.txt").read_text().splitlines()
    assert t["check_good"] in answer and t["check_good_refused"] == "none" and t["check_bad_refused"]
