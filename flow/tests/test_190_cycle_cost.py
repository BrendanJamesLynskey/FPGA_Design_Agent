"""Brief 190, item 26: the cycle-cost line (flow/cycle_cost.py): values computed from records, zero rows explained, totals summed, docs current."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from flow import cycle_cost as CC

ROOT = Path(__file__).resolve().parents[2]


def test_the_trading_designs_have_current_lines() -> None:
    assert all(CC.coverage().values()), CC.coverage()
    assert CC.check() == []


def test_values_are_the_measured_ones() -> None:
    got = {}
    for d in CC.TRADING:
        rows, totals, probs = CC.evaluate(CC.load(ROOT / "designs" / d))
        assert probs == []
        got[d] = ([r["clocks"] for r in rows], [t["sum"] for t in totals])
    assert got["b110_itch_ouch"] == ([1, 1, 5, 1, 1], [8, 3])
    assert got["b58a_trigger"] == ([2, 1, 1, 2, 2, 12], [8, 18])
    assert got["b119_tcp_fast"] == ([1, 0, 0], [])


def test_zero_rows_say_why_and_the_stub_comparison_is_zero() -> None:
    rows, _, _ = CC.evaluate(CC.load(ROOT / "designs" / "b119_tcp_fast"))
    zero = [r for r in rows if r["clocks"] == 0]
    assert len(zero) == 2 and all(len(r["why"]) > 40 for r in zero)


def _tree(tmp_path: Path, rec: dict, spec: dict, doc: str = f"x\n{CC.BEGIN}\n{CC.END}\n") -> Path:
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "r.json").write_text(json.dumps(rec))
    d = tmp_path / "designs" / "d"
    (d / "docs").mkdir(parents=True)
    (d / "docs" / "d.md").write_text(doc)
    (d / "cycle_cost.yaml").write_text(yaml.safe_dump(spec))
    return tmp_path


SPEC = {"design": "d", "doc": "docs/d.md", "unit": "clocks", "rows": [
    {"id": "a", "block": "a", "from_event": "t0", "to_event": "t1", "record": "results/r.json", "to": ["a"]},
    {"id": "b", "block": "b", "from_event": "t1", "to_event": "t2", "record": "results/r.json", "from": ["a"], "to": ["b"], "why": "registered in place"}],
    "totals": [{"label": "all", "sum_of": ["a", "b"], "record": "results/r.json", "path": ["b"]}]}


def _sub(base: Path, name: str) -> Path:
    (base / name).mkdir()
    return base / name


def test_check_catches_each_failure_kind(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"a": 2, "b": 5}, SPEC)
    rows, totals, probs = CC.evaluate(CC.load(root / "designs" / "d"), root)
    assert [r["clocks"] for r in rows] == [2, 3] and totals[0]["sum"] == 5 and probs == []
    (root / "designs" / "d" / "docs" / "d.md").write_text(f"x\n{CC.BEGIN}\nold\n{CC.END}\n")
    assert any("not current" in p for p in CC.check(root, ("d",)))
    # zero with no why
    z = json.loads(json.dumps(SPEC))
    z["rows"][1].pop("why")
    root2 = _tree(_sub(tmp_path, "z"), {"a": 2, "b": 2}, z)
    assert any("adds 0 clocks and says no why" in p for p in CC.check(root2, ("d",)))
    # a total that is consistent (the second row is b - a), then one that is not the record's figure
    root3 = _tree(_sub(tmp_path, "t"), {"a": 2, "b": 9}, SPEC)
    rows, totals, probs = CC.evaluate(CC.load(root3 / "designs" / "d"), root3)
    assert totals[0]["sum"] == 9 and probs == []                      # a=2 and b-a=7 sum to 9, which is b
    bad = json.loads(json.dumps(SPEC))
    bad["totals"][0]["path"] = ["a"]
    root4 = _tree(_sub(tmp_path, "u"), {"a": 2, "b": 9}, bad)
    assert any("rows sum to 9 but the record says 2" in p for p in CC.check(root4, ("d",)))
    # a record that cannot be read
    broken = json.loads(json.dumps(SPEC))
    broken["rows"][0]["to"] = ["missing"]
    root5 = _tree(_sub(tmp_path, "v"), {"a": 2, "b": 9}, broken)
    assert any("KeyError" in p for p in CC.check(root5, ("d",)))


def test_write_then_check_round_trips(tmp_path: Path) -> None:
    root = _tree(tmp_path, {"a": 2, "b": 5}, SPEC)
    rows, totals, _ = CC.evaluate(SPEC, root)
    doc = root / "designs" / "d" / "docs" / "d.md"
    doc.write_text(f"head\n{CC.BEGIN}\n{CC.render(SPEC, rows, totals)}\n{CC.END}\ntail\n")
    assert CC.check(root, ("d",)) == []
    assert "| a | 2 |" in doc.read_text() and "registered in place" in doc.read_text()
