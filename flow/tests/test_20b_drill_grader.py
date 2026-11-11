"""Brief 20 part B: the I/O drill's grader (benchmark/drills/lib/grade_io.py) passes the reference build and fails each
constraint mutant, on the committed goldens of real builds (flow/run_vivado.sh, Vivado 2025.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark.drills.lib import grade_io

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "benchmark" / "drills" / "d20_adc_capture"
GOLD = ROOT / "results" / "20_timing_exceptions" / "drills" / "golden"

# mutant -> the grader check that must fail (and only that one)
EXPECT = {"ref": set(), "adc_margin_xdc": {"margin"}, "adc_invented": {"routed", "no_invented"},
          "adc_swapped": {"routed", "interface", "no_invented"}, "adc_nojitter": {"input_jitter"}}


@pytest.mark.parametrize("name", sorted(EXPECT))
def test_grader_on_reference_and_mutants(name: str) -> None:
    d = GOLD / ("adc_ref" if name == "ref" else name)
    r = grade_io.grade(TASK, d)
    failed = {k for k, c in r["checks"].items() if not c["pass"]}
    assert failed == EXPECT[name], json.dumps(r["checks"], indent=1)[:3000]
    assert r["pass"] == (name == "ref")


def test_reference_numbers() -> None:
    r = grade_io.grade(TASK, GOLD / "adc_ref")
    i = r["checks"]["interface"]["interfaces"][0]
    assert i["iob_packed"] and i["setup_slack_ns"] > 0 and i["hold_slack_ns"] > 0
    g = json.loads((GOLD / "adc_ref" / "build" / "base" / "gates.json").read_text())
    m = g["stages"]["post_route"]["timing_margin"]
    assert m["margin_ns"] == 0.3
    assert m["place_wns_without_margin_ns"] - m["place_wns_with_margin_ns"] == pytest.approx(0.3, abs=0.002)
