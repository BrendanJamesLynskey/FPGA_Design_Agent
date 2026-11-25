"""Brief 189 item 5: the tail-percentile claim gate (advisory). A tail percentile needs 100 observations beyond it."""

from __future__ import annotations

import json
from pathlib import Path

from flow import claims_tail as C

ROOT = Path(__file__).resolve().parents[2]


def test_required_samples() -> None:
    assert C.required_samples(99) == 10_000
    assert C.required_samples(99.9) == 100_000
    assert C.required_samples(99.99) == 1_000_000
    assert C.required_samples(95) == 2_000
    assert C.run_length(99.9, 50_000)["seconds"] == 2.0


def test_percentile_spellings() -> None:
    assert C.percentiles_in("p99 and p999 and p9999 and p995") == [99.0, 99.5, 99.9, 99.99]
    assert C.percentiles_in("the 99.9th percentile, a 99th-percentile figure, 95 %ile") == [95.0, 99.0, 99.9]
    assert C.percentiles_in("p50 and p90 (p95 is not p9)") == [90.0, 95.0]
    assert C.percentiles_in("the median and max") == []


def test_too_few_observations_is_flagged() -> None:
    f = C.scan_text("Latency p99.9 was 53 clocks over 3000 reads.", "x.md")
    assert [x["code"] for x in f] == ["TAIL-N-01"] and f[0]["samples"] == 3000 and f[0]["beyond"] == 3.0


def test_enough_observations_is_clean() -> None:
    assert C.scan_text("p99.9 = 53 clocks (n = 2,000,000 messages).", "x.md") == []
    assert C.scan_text("p99 over 25k frames", "x.md") == []
    assert C.scan_text("p99.99 over 1 million frames", "x.md") == []
    assert C.scan_text("p99.99 over 999,999 frames", "x.md")[0]["code"] == "TAIL-N-01"


def test_no_count_is_a_separate_finding() -> None:
    f = C.scan_text("The p99 read latency is 31 clocks.", "x.md")
    assert [x["code"] for x in f] == ["TAIL-N-02"]


def test_count_from_the_table_column_not_the_runs_column() -> None:
    tab = "| Run | Reads | Median / p99 | \n|---|---|---|\n| a | 3000 | 12 / 31 |\n| b | 2,000,000 | 12 / 31 |\n"
    f = C.scan_text(tab, "t.md")
    assert [x["where"] for x in f] == ["t.md:3"]
    runs = "| ID | What | Runs |\n|---|---|---|\n| M2 | p99.9 read latency | 1 |\n"
    assert C.scan_text(runs, "t.md")[0]["code"] == "TAIL-N-02"          # 1 run is not a sample count


def test_waiver_marker_skips_a_line() -> None:
    assert C.scan_text("p99.9 of |s| (tail-ok: a weight statistic over 64 values, not a latency)", "x.md") == []


def test_json_record_with_clock_and_ns_siblings() -> None:
    rec = {"runs": {"r": {"lat_clk": {"n": 3000, "p50": 12, "p99": 31, "p999": 53, "max": 59},
                          "lat_ns": {"p50": 37.0, "p99": 95.4}}}}
    f = C.scan_json(rec, "r.json")
    codes = {(x["where"].split(":")[1], x["samples"]) for x in f}
    assert ("runs.r.lat_clk.p99", 3000) in codes and ("runs.r.lat_ns.p99", 3000) in codes
    assert not any(x["where"].endswith("p50") for x in f)
    assert C.scan_json({"lat": {"n": 5_000_000, "p999": 4}}) == []


def test_flags_the_memory_scheduler_results_in_this_repo() -> None:
    """The recorded finding: results/b141 quotes p99 and p99.9 from 2,115 to 3,000 reads (about 21-30 and 2-3 beyond them)."""
    f = C.scan_file(ROOT / "designs" / "m141_ddr2_sched" / "docs" / "results.md", ROOT)
    assert any(x["code"] == "TAIL-N-01" and x["percentile"] == 99.0 and x["samples"] == 3000 for x in f)


def test_cli_writes_an_advisory_record(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("p99 over 100 samples\n")
    out = tmp_path / "o.json"
    assert C.main([str(tmp_path / "a.md"), "--json", str(out)]) == 0
    rec = json.loads(out.read_text())
    assert rec["enforced"] is False and rec["findings"][0]["code"] == "TAIL-N-01"
