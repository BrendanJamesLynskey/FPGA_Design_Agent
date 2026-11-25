"""Brief 194: proposed settings from an input folder, confirmation gating, KR260 and Nexys A7 packages. No model, no tools."""

import shutil
from pathlib import Path

import pytest
import yaml

from agent.graph import settings as S

ROOT = Path(__file__).resolve().parents[2]


def _pkg(tmp_path, board, extra=None):
    d = tmp_path / f"{board}_package"
    d.mkdir()
    shutil.copy(ROOT / "boards" / board / "board.yaml", d / "board.yaml")
    if extra:
        (d / "board_facts.yaml").write_text(yaml.safe_dump(extra))
    return d


@pytest.mark.parametrize("board,part,clk", [("nexys_a7_100t", "xc7a100tcsg324-1", 100), ("kr260", "xck26-sfvc784-2LV-c", 25)])
def test_the_board_packages_give_sourced_proposals(tmp_path, board, part, clk):
    out = S.propose(_pkg(tmp_path, board))
    s = out["settings"]
    assert s["board"]["value"] == board and s["part"]["value"] == part
    assert s["reference_clocks"]["value"][0]["freq_mhz"] == clk
    assert s["speed_grade"]["value"] == ("-1" if board == "nexys_a7_100t" else "-2L")
    for k in ("board", "part", "reference_clocks"):
        assert s[k]["sources"] and s[k]["status"] == "proposed"
    assert all(e["status"] in ("proposed", "ask") for e in s.values())          # nothing is confirmed by the agent


def test_missing_values_are_asked_not_guessed(tmp_path):
    out = S.propose(_pkg(tmp_path, "kr260"))
    for k in ("io_standards", "phys"):
        assert out["settings"][k]["value"] is None and out["settings"][k]["status"] == "ask"
    assert S.propose(tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path)["settings"]["part"]["status"] == "ask"   # an empty folder asks for everything


def test_an_ingest_that_disagrees_is_a_conflict(tmp_path):
    d = _pkg(tmp_path, "nexys_a7_100t", {"facts": {"part": {"value": "xc7a35tcpg236-1", "source": "schematic p.3"}}})
    e = S.propose(d)["settings"]["part"]
    assert e["value"] == "xc7a35tcpg236-1" and "schematic p.3" in e["sources"][0]          # the ingest is read first
    assert e["conflicts"] == [{"value": "xc7a100tcsg324-1", "source": "boards/nexys_a7_100t/board.yaml"}]


def test_every_setting_is_an_interview_question_with_its_source_as_the_reason(tmp_path):
    out = S.propose(_pkg(tmp_path, "kr260"))
    qs = {k: (t, d, r) for k, t, d, r in S.questions(out)}
    assert set(qs) == set(S.KEYS)
    assert qs["part"][1] == '"xck26-sfvc784-2LV-c"' and "boards/kr260/board.yaml" in qs["part"][2]
    assert qs["phys"][1] == S.SENTINEL and "nothing is guessed" in qs["phys"][2]


def test_a_default_confirms_only_what_has_a_value_and_no_conflict(tmp_path):
    d = _pkg(tmp_path, "nexys_a7_100t", {"facts": {"part": "xc7a35tcpg236-1"}})
    doc = S.propose(d)
    values, bad = S.resolve(doc, {})                               # everything defaulted
    assert values["board"] == "nexys_a7_100t" and "part" not in values
    assert any(b.startswith("part: the sources disagree") for b in bad) and any(b.startswith("phys: nothing was proposed") for b in bad)
    values, bad = S.resolve(doc, {"part": ("xc7a100tcsg324-1", "answered"), "phys": ('["none"]', "answered")})
    assert values["part"] == "xc7a100tcsg324-1" and values["phys"] == ["none"] and not bad       # a person's answer settles a conflict and fills a gap


def test_an_answer_that_is_a_number_stays_text_where_the_proposal_is_text(tmp_path):
    doc = S.propose(_pkg(tmp_path, "nexys_a7_100t"))
    values, _ = S.resolve(doc, {"speed_grade": ("-2", "answered"), "reference_clocks": ('[{"port": "clk", "freq_mhz": 50}]', "answered")})
    assert values["speed_grade"] == "-2" and values["reference_clocks"][0]["freq_mhz"] == 50


def test_flags_become_the_proposed_value(tmp_path):
    doc = S.apply_flags(S.propose(_pkg(tmp_path, "nexys_a7_100t")), "kr260", "ip_release")
    assert doc["settings"]["board"]["value"] == "kr260" and doc["settings"]["board"]["sources"][-1] == "the command line"
    assert doc["settings"]["profile"]["value"] == "ip_release"


def test_the_cli_propose_command_writes_the_interviews_input(tmp_path):
    from agent.__main__ import main
    d = _pkg(tmp_path, "kr260")
    assert main(["propose", str(d)]) == 0
    assert S.load_proposals(d / "proposed_settings.yaml")["settings"]["board"]["value"] == "kr260"


def test_agent_run_refuses_a_file_that_is_not_a_settings_file(tmp_path, capsys):
    from agent.__main__ import main
    f = tmp_path / "x.yaml"
    f.write_text("a: 1\n")
    with pytest.raises(SystemExit) as e:
        main(["run", str(ROOT / "designs/t1_dimmer_counter/spec.md"), "--settings", str(f)])
    assert e.value.code == 2 and "not a settings file" in capsys.readouterr().err
