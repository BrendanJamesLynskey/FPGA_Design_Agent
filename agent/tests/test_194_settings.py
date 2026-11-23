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


def test_a_run_refuses_unconfirmed_settings_and_a_flag_that_disagrees(tmp_path):
    d = _pkg(tmp_path, "nexys_a7_100t")
    f = S.write(d, S.propose(d))
    with pytest.raises(S.SettingsError, match="not confirmed"):
        S.load_confirmed(f)
    done = S.confirm(f)
    assert "board" in done and "phys" not in done                                             # empty values cannot be confirmed by the call
    with pytest.raises(S.SettingsError, match="phys: ask"):
        S.load_confirmed(f)
    doc = yaml.safe_load(f.read_text())
    doc["settings"]["phys"].update(value=["none"], status="confirmed")
    f.write_text(yaml.safe_dump(doc))
    vals = S.load_confirmed(f)
    assert vals["board"] == "nexys_a7_100t"
    assert S.apply_to_args(vals, None, None) == ("nexys_a7_100t", "standard")
    with pytest.raises(S.SettingsError, match="disagrees"):
        S.apply_to_args(vals, "kr260", None)
    with pytest.raises(S.SettingsError, match="disagrees"):
        S.apply_to_args(vals, None, "prototype")


def test_a_conflict_cannot_be_confirmed_by_the_call(tmp_path):
    d = _pkg(tmp_path, "nexys_a7_100t", {"facts": {"part": "xc7a35tcpg236-1"}})
    f = S.write(d, S.propose(d))
    assert "part" not in S.confirm(f)


def test_the_cli_commands(tmp_path, capsys):
    from agent.__main__ import main
    d = _pkg(tmp_path, "kr260")
    assert main(["propose", str(d)]) == 0 and (d / "proposed_settings.yaml").is_file()
    assert main(["settings", "confirm", str(d / "proposed_settings.yaml")]) == 1          # io_standards, phys, interfaces still asked
    assert "ask" in capsys.readouterr().out


def test_agent_run_refuses_an_unconfirmed_settings_file(tmp_path, capsys):
    from agent.__main__ import main
    d = _pkg(tmp_path, "nexys_a7_100t")
    f = S.write(d, S.propose(d))
    with pytest.raises(SystemExit) as e:
        main(["run", str(ROOT / "designs/t1_dimmer_counter/spec.md"), "--settings", str(f)])
    assert e.value.code == 2 and "not confirmed" in capsys.readouterr().err
