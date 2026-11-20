"""Brief 96D2: the 2026-11-19 board run counted no samples at any of 1023 points x 10 scans. Cause (UG576 v1.7.1 Table 4-20, printed pp. 230-232): the GTHE4 masks are TEN 16-bit
words each and the driver wrote five, so ES_QUAL_MASK[159:80] stayed 0 and the sample counter never advanced. These tests pin the fix and the guards, against the
register-level synthetic board (flow/eyescan/fake.py, which now models that rule) and the committed failed-run captures."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from designs.b96_kr260_10g.model import eyescan as tw
from flow.eyescan import __main__ as cli
from flow.eyescan import api, capture as C, fake, scan
from flow.eyescan import hw as H

FAILED = Path(__file__).resolve().parents[2] / "results" / "b96d" / "hw" / "20261119_231836"
CFG = dict(target_ber=1e-6, hstep=8, vstep=40, vmax=80)


def _run(fb, **kw):
    return scan.run_scan(H.EyeHW(fb), scan.ScanConfig(**{**CFG, **kw}), synthetic=True, conditions=lambda: {"inside_roc": True}, link_ok=lambda: True, design={})


def test_masks_are_the_ug576_160_bit_values_in_ten_words():
    # {80'b1, 32'b0, 48'b1} written out as a string, independent of the implementation (UG576 Table 4-20, 32-bit width, UltraScale+)
    want = int("1" * 80 + "0" * 32 + "1" * 48, 2)
    assert H.sdata_mask_160(32) == want
    assert H.SDATA_MASK_32 == [0xFFFF, 0xFFFF, 0xFFFF, 0x0000, 0x0000] + [0xFFFF] * 5
    assert int("1" * 80 + "0" * 40 + "1" * 40, 2) == H.sdata_mask_160(40) and int("1" * 80 + "0" * 80, 2) == H.sdata_mask_160(80)
    assert len(H.QUAL_MASK) == len(H.QUALIFIER) == len(H.SDATA_MASK_32) == 10 and set(H.QUAL_MASK) == {0xFFFF}
    # Table C-2 (GTHE4_CHANNEL): words 0-4 at 0x03F/0x044/0x049, words 5-9 at 0x0E7/0x0EC/0x0F1
    assert tw.QUALIFIER_ADDRS == [0x3F, 0x40, 0x41, 0x42, 0x43, 0xE7, 0xE8, 0xE9, 0xEA, 0xEB]
    assert tw.QUAL_MASK_ADDRS == [0x44, 0x45, 0x46, 0x47, 0x48, 0xEC, 0xED, 0xEE, 0xEF, 0xF0]
    assert tw.SDATA_MASK_ADDRS == [0x49, 0x4A, 0x4B, 0x4C, 0x4D, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5]
    assert len(H.SAVE_ADDRS) == 33 and len(set(H.SAVE_ADDRS)) == 33
    with pytest.raises(ValueError):
        H.sdata_mask_160(24)


def test_the_96d_five_word_driver_reproduces_the_failed_run_and_the_guard_stops_it_at_the_self_test():
    """The old driver (five words of each mask) on the board model: every point times out. The scan must stop at its self-test, with no grid point taken."""
    fb = fake.FakeBoard()
    eh = H.EyeHW(fb)

    def old_setup():
        eh.require_eyescan_build()
        eh.clear_flags()
        eh.saved = {a: eh.drp_read(a) for a in H.SAVE_ADDRS}
        for i in range(5):
            eh.drp_write(tw.A_ES_QUALIFIER0 + i, 0)
            eh.drp_write(tw.A_ES_QUAL_MASK0 + i, 0xFFFF)
            eh.drp_write(tw.A_ES_SDATA_MASK0 + i, [0x00FF, 0x0000, 0xFF00, 0xFFFF, 0xFFFF][i])
        return dict(eh.saved)
    eh.setup = old_setup
    cap = scan.run_scan(eh, scan.ScanConfig(**CFG), synthetic=True, design={})
    assert "NO DATA" in cap["run"]["error"] and "self-test" in cap["run"]["error"] and "COUNT" in cap["run"]["error"]
    assert cap["points"] == [] and cap["selftest"]["ok"] is False and cap["restore"]["ok"] is True
    assert C.no_data_stats(cap)["no_data"] is True
    with pytest.raises(C.CaptureError, match="NO DATA"):
        C.require_data(cap)


def test_the_fixed_driver_passes_the_self_test_and_every_point_has_data():
    cap = _run(fake.FakeBoard())
    assert cap["selftest"]["ok"] is True and cap["selftest"]["samp"] > 0 and cap["run"]["error"] is None
    assert cap["run"]["no_data_points"] == 0 and len(cap["points"]) == cap["settings"]["expected_points"]
    C.require_data(cap)
    assert all(r["status"] == 0b0101 for p in cap["points"] for r in p["rungs"])        # END state recorded for every rung
    assert "NO DATA" not in C.summary_line("x", cap)


def test_k_consecutive_no_data_points_stop_the_scan_and_one_stray_timeout_does_not():
    fb = fake.FakeBoard()
    orig = fb.wr
    state = {"n": 0}

    def breaker(a, v):
        if a == H.R_CMD and v & 4:
            state["n"] += 1
            if state["n"] == 4:                   # the fault appears after the self-test (point 1) and two good grid points
                fb.drp[tw.QUAL_MASK_ADDRS[7]] = 0
        orig(a, v)
    fb.wr = breaker
    cap = _run(fb)
    assert "NO DATA" in cap["run"]["error"] and f"{scan.K_CONSECUTIVE_NO_DATA} consecutive" in cap["run"]["error"]
    assert len(cap["points"]) == 2 + scan.K_CONSECUTIVE_NO_DATA and cap["run"]["no_data_points"] == scan.K_CONSECUTIVE_NO_DATA
    assert cap["restore"]["ok"] is True                                     # attributes put back on the early stop
    assert C.no_data_stats(cap)["no_data"] is True                          # stopped on its own guard: not an acceptable capture, though 2 points have data
    assert f"NO DATA: {scan.K_CONSECUTIVE_NO_DATA}/{2 + scan.K_CONSECUTIVE_NO_DATA} points timed out" in C.summary_line("x", cap)
    # a single stray no-data point is recorded, not fatal
    fb2 = fake.FakeBoard()
    orig2 = fb2.wr
    n2 = {"n": 0}

    def stray(a, v):
        if a == H.R_CMD and v & 4:
            n2["n"] += 1
            fb2.drp[tw.QUAL_MASK_ADDRS[7]] = 0 if n2["n"] == 5 else 0xFFFF
        orig2(a, v)
    fb2.wr = stray
    cap2 = _run(fb2)
    assert cap2["run"]["error"] is None and cap2["run"]["no_data_points"] == 1
    assert "WARNING 1/" in C.summary_line("x", cap2)


def test_the_committed_2026_11_19_captures_are_no_data_and_say_so():
    caps = sorted(p for p in FAILED.glob("*.json") if p.name not in ("probe.json", "program.json"))
    assert len(caps) == 10, [p.name for p in caps]
    for f in caps:
        c = C.load(f)
        nd = C.no_data_stats(c)
        assert nd["no_data"] and nd["timed_out"] == nd["points"] == c["settings"]["expected_points"], f.name
        with pytest.raises(C.CaptureError, match="NO DATA"):          # the check a results directory must pass: fails on this run
            C.require_data(c)
        line = C.summary_line(f.stem, c)
        assert f"NO DATA: {nd['points']}/{nd['points']} points timed out" in line and "open 0" not in line
        m = api.margin(c, c["settings"]["target_ber"])
        assert m["pass"] is False and any(r.startswith("NO DATA") for r in m["reasons"])


def test_summary_command_writes_no_data_lines_and_exits_9(tmp_path):
    for f in list(FAILED.glob("lpm_1.json")) + list(FAILED.glob("dfe_1.json")):
        shutil.copy(f, tmp_path / f.name)
    rc = cli.main(["summary", str(tmp_path)])
    txt = (tmp_path / "summary.txt").read_text()
    assert rc == cli.EXIT_NO_DATA == 9 and txt.count("NO DATA: 1023/1023 points timed out") == 1 and txt.count("NO DATA: 2046/2046 points timed out") == 1
    ok = fake.FakeBoard()
    good = _run(ok)
    d2 = tmp_path / "good"
    d2.mkdir()
    C.save(good, d2 / "fake.json")
    assert cli.main(["summary", str(d2)]) == 0 and "NO DATA" not in (d2 / "summary.txt").read_text()


def test_run_exits_9_on_no_data_and_1_on_a_lost_write(tmp_path, monkeypatch):
    class Dead(fake.FakeBoard):                          # the point sequencer never reaches END, whatever is written
        def _qual_all_masked(self):
            return False
    monkeypatch.setattr(fake, "FakeBoard", Dead)
    args = ["run", "--fake", "--out", str(tmp_path), "--name", "s", "--hstep", "16", "--vstep", "80", "--vmax", "80", "--target-ber", "1e-6"]
    assert cli.main(args) == cli.EXIT_NO_DATA
    c = C.load(tmp_path / "s.json")
    assert c["points"] == [] and "NO DATA" in c["run"]["error"] and c["restore"]["ok"] is True
    assert api.margin(c, 1e-6)["pass"] is False

    class Stuck(fake.FakeBoard):                         # a DRP write to a mask word is lost: caught by the read-back in setup()
        def wr(self, a, v):
            if a == H.R_CMD and v & 2 and self.reg.get(H.R_DRP_ADDR) in tw.QUAL_MASK_ADDRS:
                return
            super().wr(a, v)
    monkeypatch.setattr(fake, "FakeBoard", Stuck)
    assert cli.main(args) == 1
    assert "did not read back" in json.loads((tmp_path / "s.json").read_text())["run"]["error"]
