"""Brief 177: the shadow-mode predict stage never changes a gate and scores itself against the routed outcome."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from flow import predict

ROOT = Path(__file__).resolve().parents[2]
GOOD = ROOT / "results/b96/build_a/gates.json"      # committed: post-synth WNS 0.652, post-place 0.499, routed 0.203


def test_predictions_cover_the_stages_that_ran_and_are_shadow():
    r = json.loads(GOOD.read_text())
    recs = predict.predict_stages(r)
    assert [x["stage"] for x in recs] == ["post_synth", "post_place"]
    assert all(x["mode"] == "shadow" and x["confidence"] == "low" and "not fitted" in x["basis"] for x in recs)
    assert recs[0]["p_pass"] == 0.9 and recs[1]["p_pass"] == 0.97


def test_low_prediction_carries_repair_context_and_a_gate_is_untouched(tmp_path):
    r = json.loads(GOOD.read_text())
    r["stages"]["post_place"]["timing"]["wns_ns"] = -0.4
    recs = predict.shadow(tmp_path, r)
    assert recs[1]["p_pass"] < predict.LOW and "retiming" in recs[1]["repair_context"]["families"]
    assert (tmp_path / "predictions.jsonl").exists()
    assert r["pass"] is True          # shadow() reads, never writes the result


def test_score_joins_with_the_routed_outcome(tmp_path):
    r = json.loads(GOOD.read_text())
    (tmp_path / "gates.json").write_text(json.dumps(r))
    predict.shadow(tmp_path, r)
    s = predict.score(tmp_path)
    assert s["routed_met"] == 1 and {x["outcome"] for x in s["rows"]} == {"go_pass"}
    r["timing"]["wns_ns"] = -0.1
    (tmp_path / "gates.json").write_text(json.dumps(r))
    assert {x["outcome"] for x in predict.score(tmp_path)["rows"]} == {"false_go"}


def test_shadow_can_be_turned_off_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("FDA_PREDICT_SHADOW", "0")
    assert predict.shadow(tmp_path, {}) == [] and not (tmp_path / "predictions.jsonl").exists()
    monkeypatch.delenv("FDA_PREDICT_SHADOW")
    assert predict.shadow(tmp_path / "missing_dir", json.loads(GOOD.read_text())) == []
