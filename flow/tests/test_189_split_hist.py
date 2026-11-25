"""Brief 189 item 9: latency histograms split by message type and by position in the packet (advisory helper)."""

from __future__ import annotations

import json
from pathlib import Path

from flow.latency import split_hist as H

ROOT = Path(__file__).resolve().parents[2]


def _synthetic() -> list[dict]:
    """A feed where the replace type costs one clock more and each later message in a packet waits two clocks per predecessor."""
    rows = []
    for t, base in (("add", 3), ("delete", 3), ("replace", 4)):
        for pos in range(6):
            for _ in range(5):
                rows.append({"latency": base + 2 * min(pos, 4), "type": t, "pos": H.packet_position(pos)})
    return rows


def test_packet_position_and_class_label() -> None:
    assert [H.packet_position(i) for i in (0, 1, 3, 4, 9)] == ["first", "second", "fourth", "fifth_or_later", "fifth_or_later"]
    assert H.class_label("replace", 1) == "replace/second"


def test_split_gives_one_narrow_peak_per_class() -> None:
    by_pos = H.split(_synthetic(), "latency", "pos")
    assert by_pos["first"]["histogram"] == {"3": 10, "4": 5} and by_pos["second"]["peaks"] == [5, 6]
    by_type = H.split(_synthetic(), "latency", "type")
    assert by_type["add"]["n"] == 30 and by_type["replace"]["min"] == 4


def test_variance_explained_ranks_the_cause() -> None:
    a = H.analyse(_synthetic(), "latency", ["type", "pos"])
    assert a["bimodal"] and a["best_split"] == "pos"
    assert a["splits"]["pos"]["variance_explained"] > 0.85 > a["splits"]["type"]["variance_explained"] > 0
    both = [{**r, "both": H.class_label(r["type"], 0 if r["pos"] == "first" else 5)} for r in _synthetic()]
    assert H.explained(both, "latency", "both") > a["splits"]["type"]["variance_explained"]


def test_constant_value_explains_nothing() -> None:
    assert H.explained([{"v": 3, "c": "a"}, {"v": 3, "c": "b"}], "v", "c") is None
    assert H.analyse([{"v": 3, "c": "a"}], "v", ["c"])["best_split"] is None


def test_recorded_b127_split_by_byte_lane(tmp_path: Path) -> None:
    out = tmp_path / "o.json"
    assert H.main([str(ROOT / "results/b127/latency_unit_sim.json"), "--rows", "latency_by_alignment.at_verdict", "--value", "sop_minus_X",
                   "--by", "end_byte_in_word", "--out", str(out)]) == 0
    rec = json.loads(out.read_text())
    cls = rec["splits"]["end_byte_in_word"]["classes"]
    assert rec["enforced"] is False and rec["all"]["peaks"] == [11, 12, 13]
    assert cls["0"]["peaks"] == [11] and cls["1"]["peaks"] == [11] and cls["2"]["peaks"] == [12]      # the lane the message ends in sets the peak
    assert 0.8 < rec["splits"]["end_byte_in_word"]["variance_explained"] < 0.95
