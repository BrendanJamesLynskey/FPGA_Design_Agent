"""Brief 189 item 6: the regression ratchet (advisory)."""

from __future__ import annotations

import json
from pathlib import Path

from flow import ratchet as R

ROOT = Path(__file__).resolve().parents[2]
OOC = ROOT / "results" / "b110" / "ooc" / "itch_ouch_top.json"
BASE = {"u_book": {"lut": 4397, "ff": 1703, "logic_depth": 5}, "u_mold": {"lut": 1394, "ff": 1683, "logic_depth": 4}, "u_tiny": {"lut": 6, "ff": 6}}


def _store(mods=BASE, clocks=None):
    s = R.snapshot("d", "b1", mods, clocks=clocks or {"decoded_event": 2, "first_order_word": 8})
    return {"history": [{**s, "accepted": True}]}


def _grow(m, mod, met, to):
    out = {k: dict(v) for k, v in m.items()}
    out[mod][met] = to
    return out


def test_no_baseline_passes() -> None:
    r = R.check({"history": []}, R.snapshot("d", "b0", BASE))
    assert r["pass"] and r["baseline"] is None


def test_same_numbers_pass() -> None:
    assert R.check(_store(), R.snapshot("d", "b2", BASE, clocks={"decoded_event": 2, "first_order_word": 8}))["findings"] == []


def test_growth_over_five_percent_is_flagged() -> None:
    r = R.check(_store(), R.snapshot("d", "b2", _grow(BASE, "u_book", "lut", 4700)))
    f = r["findings"]
    assert [(x["code"], x["module"], x["metric"], x["growth_pct"]) for x in f] == [("RATCHET-01", "u_book", "lut", 6.9)]
    assert not r["pass"] and r["enforced"] is False


def test_growth_under_the_limit_or_the_floor_is_not_flagged() -> None:
    assert R.check(_store(), R.snapshot("d", "b2", _grow(BASE, "u_book", "lut", 4500)))["findings"] == []   # 2.3 %
    assert R.check(_store(), R.snapshot("d", "b2", _grow(BASE, "u_tiny", "lut", 9)))["findings"] == []      # +50 % but 3 LUTs
    assert R.check(_store(), R.snapshot("d", "b2", _grow(BASE, "u_book", "logic_depth", 6)))["findings"][0]["growth_pct"] == 20.0


def test_a_clock_more_of_latency_is_flagged() -> None:
    r = R.check(_store(), R.snapshot("d", "b2", BASE, clocks={"decoded_event": 3, "first_order_word": 8}))
    assert [(f["module"], f["metric"]) for f in r["findings"]] == [("decoded_event", "clocks")]


def test_waiver_needs_a_reason_and_override_is_recorded() -> None:
    snap = R.snapshot("d", "b2", _grow(BASE, "u_book", "lut", 4700))
    assert not R.check(_store(), snap, waivers=[{"module": "u_book", "metric": "lut", "reason": ""}])["pass"]
    ok = R.check(_store(), snap, waivers=[{"module": "u_*", "metric": "lut", "reason": "wider order id, needed by the new risk check"}])
    assert ok["pass"] and ok["findings"][0]["waived"].startswith("waiver: wider")
    assert R.check(_store(), snap, override="ladder depth 8 to 16")["findings"][0]["waived"] == "override: ladder depth 8 to 16"
    assert not R.check(_store(), snap, override="  ")["pass"]


def test_creep_in_small_steps_is_caught_against_the_best() -> None:
    store = _store()
    for i, step in enumerate((4500, 4650, 4800, 4950)):            # each step under 5 % of the one before
        snap = R.snapshot("d", f"c{i}", _grow(BASE, "u_book", "lut", step))
        res = R.check(store, snap)
        if step < 4950:
            assert res["pass"], (step, res["findings"])
        R.record(store, snap, res)
    assert res["findings"] and res["findings"][0]["code"] == "RATCHET-02" and res["findings"][0]["was"] == 4397
    assert not store["history"][-1]["accepted"]


def test_new_and_vanished_figures_are_listed_not_flagged() -> None:
    m = {k: dict(v) for k, v in BASE.items() if k != "u_tiny"}
    m["u_new"] = {"lut": 100, "ff": 100}
    r = R.check(_store(), R.snapshot("d", "b2", m))
    assert "u_new.lut" in r["new"] and "u_tiny.lut" in r["gone"] and r["pass"]


def test_depth_from_a_timing_report() -> None:
    rpt = next((ROOT / "flow/tests/fixtures/io_timing/golden/io_v4").glob("timing_worst_setup.rpt")).read_text()
    d = R.depth_by_module(rpt)
    assert d and all(isinstance(v, int) and v >= 0 for v in d.values())


def test_snapshot_cli_on_recorded_b110_blocks_and_latencies(tmp_path: Path) -> None:
    snap = tmp_path / "s.json"
    assert R.main(["snapshot", "--blocks", str(OOC), "--build", "ooc6.2", "--out", str(snap),
                   "--clocks", str(ROOT / "results/b110/latency_sim.json"), "--clocks-key", "non_speculative"]) == 0
    s = json.loads(snap.read_text())
    assert s["modules"]["u_book"]["lut"] == 4397 and s["clocks"]["book_update_add"] == 7
    store = tmp_path / "store.json"
    assert R.main(["record", "--store", str(store), "--snap", str(snap)]) == 0
    assert json.loads(store.read_text())["history"][0]["accepted"] is True
    snap2 = tmp_path / "s2.json"
    R.main(["snapshot", "--blocks", str(OOC), "--run", "runs.2", "--build", "ooc4.4", "--out", str(snap2)])
    out = tmp_path / "o.json"
    assert R.main(["check", "--store", str(store), "--snap", str(snap2), "--json", str(out)]) == 0      # advisory: exit 0 even with findings
    assert R.main(["check", "--store", str(store), "--snap", str(snap2), "--enforce"]) == 1 if json.loads(out.read_text())["findings"] else True
