"""Brief 189 item 7: a second, independent latency method, and a planted racy-counter bench defect (advisory).

The fixture (fixtures/latency_race) measures a pipeline whose true latency is 3 clocks two ways: a cycle counter and the simulator's clock.
Variants 0 and 1 plant the testbench race (blocking counter increment read by another process on the same edge); variant 2 repairs it."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from flow.latency import crosscheck as X

FX = Path(__file__).parent / "fixtures" / "latency_race"
ROOT = Path(__file__).resolve().parents[2]
needs_iverilog = pytest.mark.skipif(shutil.which("iverilog") is None, reason="needs Icarus Verilog")
TRUE_LATENCY = 3


def _measure(tmp: Path, racy: int) -> dict:
    vvp = tmp / "lat.vvp"
    r = subprocess.run(["iverilog", "-g2012", "-s", "lat_tb", "-o", str(vvp), str(FX / "rtl" / "lat_pipe.sv"), str(FX / "lat_tb.sv")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = subprocess.run(["vvp", str(vvp), f"+RACY={racy}"], capture_output=True, text=True, timeout=60).stdout
    cnt, sim = (int(re.search(rf"{k}=(-?\d+)", out)[1]) for k in ("LAT_COUNTER", "LAT_SIMTIME"))
    return {"claim": f"lat_pipe latency, bench variant {racy}", "latency_clocks": cnt,
            "start_event": "in_valid sampled at a clock edge", "end_event": "out_valid first sampled high",
            "methods": [{"name": "stamp counter", "kind": "counter", "value": cnt},
                        {"name": "simulator time / period", "kind": "simulator_time", "value": sim}]}


@needs_iverilog
@pytest.mark.parametrize("racy", [0, 1])
def test_racy_counter_bench_misreads_and_the_second_method_flags_it(racy: int, tmp_path: Path) -> None:
    rec = _measure(tmp_path, racy)
    sim = rec["methods"][1]["value"]
    assert sim == TRUE_LATENCY                             # the simulator clock is not touched by the race
    assert rec["latency_clocks"] != TRUE_LATENCY           # the planted defect: the counter is read wrongly
    assert [f["code"] for f in X.check_record(rec)] == ["LAT-X-03"]


@needs_iverilog
def test_repaired_bench_agrees(tmp_path: Path) -> None:
    rec = _measure(tmp_path, 2)
    assert rec["latency_clocks"] == TRUE_LATENCY and X.check_record(rec) == []


def test_one_method_two_counters_and_missing_events() -> None:
    base = {"claim": "c", "latency_clocks": 3, "start_event": "a", "end_event": "b"}
    one = {**base, "methods": [{"name": "x", "kind": "counter", "value": 3}]}
    assert [f["code"] for f in X.check_record(one)] == ["LAT-X-01"]
    two_counters = {**base, "methods": [{"name": "x", "kind": "counter", "value": 3}, {"name": "y", "kind": "counter", "value": 3}]}
    assert [f["code"] for f in X.check_record(two_counters)] == ["LAT-X-02"]
    ok = {**base, "methods": [{"name": "x", "kind": "counter", "value": 3}, {"name": "y", "kind": "waveform_marker", "value": 3}]}
    assert X.check_record(ok) == []
    assert [f["code"] for f in X.check_record({**ok, "start_event": ""})] == ["LAT-X-04"]
    assert [f["code"] for f in X.check_record({**ok, "latency_clocks": 4})] == ["LAT-X-03"]
    tol = {**ok, "tolerance_clocks": 1, "methods": [{"name": "x", "kind": "counter", "value": 3}, {"name": "y", "kind": "analytic", "value": 4}]}
    assert X.check_record({**tol, "latency_clocks": 3}) == []


def test_scan_flags_recorded_latency_without_methods() -> None:
    f = X.scan_file(ROOT / "results" / "b110" / "latency_sim.json", ROOT)
    assert [x["code"] for x in f] == ["LAT-X-05"]


def test_cli_is_advisory(tmp_path: Path) -> None:
    import json
    (tmp_path / "x_latency.json").write_text(json.dumps({"claim": "c", "methods": [{"kind": "counter", "value": 1}]}))
    out = tmp_path / "o.json"
    assert X.main([str(tmp_path / "x_latency.json"), "--json", str(out)]) == 0
    rec = json.loads(out.read_text())
    assert rec["enforced"] is False and {f["code"] for f in rec["findings"]} == {"LAT-X-01", "LAT-X-04"}
