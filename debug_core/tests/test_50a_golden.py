"""Brief 50A golden captures: the raw ILA exports of the board demo (CSV, probe_map.txt, hw_probes.txt) are turned into a
capture again, and must give the same channels and the same answer as the committed run (results/50a_nl_debug)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from debug_core import capture as C
from debug_core.answer import answer
from debug_core.instruments import samples_from_files

GOLD = Path(__file__).parent / "fixtures" / "golden"
CASES = sorted(p.name for p in GOLD.iterdir() if (p / "capture.json").is_file()) if GOLD.is_dir() else []


@pytest.mark.parametrize("name", CASES)
def test_raw_ila_files_rebuild_the_committed_capture(name: str) -> None:
    d = GOLD / name
    cap = C.load(d / "capture.json")
    plan = json.loads((d / "plan.json").read_text())
    labels = json.loads((d / "labels.json").read_text()) if (d / "labels.json").is_file() else {}
    samples, t0, _ = samples_from_files(plan, d / "cap.csv", d / "probe_map.txt", d / "hw_probes.txt", labels)
    assert t0 == cap["timebase"]["trigger_sample"]
    assert {c["name"]: c["samples"] for c in cap["channels"]} == samples
    a = answer(cap, plan.get("question"))
    assert a["check"] == []
    assert a["text"].strip() == (d / "answer.txt").read_text().strip()


def test_there_are_golden_captures() -> None:
    assert len(CASES) >= 2
