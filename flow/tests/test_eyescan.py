"""Brief 96D: the eye-scan host code, capture format, derived numbers and displays, against the SYNTHETIC board of flow/eyescan/fake.py (no hardware)."""

from __future__ import annotations

import json
import math

import pytest

from designs.b96_kr260_10g.model import eyescan as tw
from flow.eyescan import api, capture as C, fake, page, scan, svg
from flow.eyescan import hw as H


def _scan(seed=1, lpm=True, **kw):
    fb = fake.FakeBoard(seed=seed, lpm=lpm)
    cfg = scan.ScanConfig(**{"target_ber": 1e-9, "hstep": 4, "vstep": 16, "vmax": 112, **kw})
    cap = scan.run_scan(H.EyeHW(fb), cfg, synthetic=True, conditions=lambda: {"temp_c": 50.0, "inside_roc": True}, link_ok=lambda: True, design=fake.design_info())
    return fb, cap


def test_register_words_match_the_rtl_layout():
    # ES_POINT: [11:0] horizontal field, [18:12] code, [19] NEG_DIR, [20] UT_SIGN, [22:21] RANGE, [27:23] prescale (rtl/b96_core.sv, 0x034)
    w = H.point_word(-5, -17, 1, 2, 9)
    assert w & 0xFFF == (0x800 | (-5 & 0x7FF))
    assert (w >> 12) & 0x7F == 17 and (w >> 19) & 1 == 1 and (w >> 20) & 1 == 1 and (w >> 21) & 3 == 2 and (w >> 23) & 31 == 9
    assert H.point_word(0, 0, 0, 0, 0) == 0
    assert H.horz_field(0) == 0 and H.horz_field(32) == 32 and H.horz_field(-32) == 0x800 | (0x7E0)
    with pytest.raises(ValueError):
        H.point_word(0, 128, 0, 0, 0)


def test_ladder_reaches_the_target_and_repeats_the_last_rung_beyond_p_max():
    assert scan.ladder(0, 1e-9) == [0, 3, 6, 9, 10]
    assert scan.ladder(0, 1e-6) == [0]
    deep = scan.ladder(0, 1e-12)
    assert max(deep) == scan.P_MAX and deep.count(scan.P_MAX) > 1
    bits = sum(C.ES_COUNT_MAX * (1 << (1 + p)) * 32 for p in deep if p == scan.P_MAX)
    assert bits * 1e-12 >= 3.0                      # the repeats at the last prescale reach the 3/bits bound at the target
    # the longest single rung stays inside the 32-bit timeout register at 100 MHz
    assert H.rung_seconds(scan.P_MAX, 32, 10.3125) * 2 + 0.5 < (2 ** 32) / 100e6


def test_zero_errors_report_a_bound_not_zero_and_depth_needs_bits():
    p = {"h": 0, "v": 0, "ut": 0, "rungs": [{"pre": 10, "err": 0, "samp": 65535, "tmo": False}]}
    s = C.point_stats(p)
    bits = 65535 * 2048 * 32
    assert s["bits"] == bits and s["ber"] == 0.0 and s["ber_ub"] == pytest.approx(3.0 / bits)
    q = {"measured": True, "ber": 0.0, "bits": bits, "err": 0}
    assert C.classify(q, 1e-9) == "open"             # 4.3e9 bits x 1e-9 = 4.3 >= 3
    assert C.classify(q, 1e-10) == "shallow"         # 0.43 < 3: cannot vouch for 1e-10
    assert C.classify({"measured": True, "ber": 1e-5, "bits": bits, "err": 43000}, 1e-9) == "closed"
    assert C.classify({"measured": False}, 1e-9) == "unmeasured"


def test_final_rungs_at_one_prescale_are_pooled_earlier_ones_are_not():
    p = {"h": 0, "v": 0, "ut": 0, "rungs": [{"pre": 0, "err": 5, "samp": 65535, "tmo": False}, {"pre": 15, "err": 1, "samp": 65535, "tmo": False},
                                           {"pre": 15, "err": 0, "samp": 65535, "tmo": False}]}
    s = C.point_stats(p)
    assert s["err"] == 1 and s["bits"] == 2 * 65535 * (1 << 16) * 32
    p["rungs"].append({"pre": 15, "err": 0, "samp": 0, "tmo": True})
    assert C.point_stats(p)["measured"] is False      # a timed-out final rung gives no data


def test_dfe_merges_both_ut_signs():
    pts = [{"h": 0, "v": 8, "ut": 0, "rungs": [{"pre": 3, "err": 4, "samp": 1000, "tmo": False}]}, {"h": 0, "v": 8, "ut": 1, "rungs": [{"pre": 3, "err": 6, "samp": 1000, "tmo": False}]}]
    m = C.merge_ut(pts)
    assert len(m) == 1 and m[0]["err"] == 10 and m[0]["bits"] == 1000 * 16 * 32 and m[0]["ut"] == [0, 1]
    assert m[0]["ber_merged"] == pytest.approx((4 + 6) / 2 / (1000 * 16 * 32))
    # unequal depths: the merged BER is the equal-weight mean, not the pooled one (review finding B1)
    deep = [{"h": 0, "v": 8, "ut": 0, "rungs": [{"pre": 0, "err": 4000, "samp": 31250, "tmo": False}]},
            {"h": 0, "v": 8, "ut": 1, "rungs": [{"pre": 10, "err": 0, "samp": 65535, "tmo": False}]}]
    b0 = 4000 / (31250 * 2 * 32)
    assert C.merge_ut(deep)[0]["ber_merged"] == pytest.approx(b0 / 2) and C.merge_ut(deep)[0]["bits"] == 31250 * 2 * 32
    assert C.merge_ut(deep[:1], expected_ut=2)[0]["measured"] is False      # a half-measured DFE point is unmeasured
    # one UT measured, the other timed out: the merged point is unmeasured (never half a total BER)
    pts[1]["rungs"][-1]["tmo"] = True
    assert C.merge_ut(pts)[0]["measured"] is False


def test_end_to_end_on_the_synthetic_board_restores_every_drp_word():
    fb, cap = _scan()
    assert cap["synthetic"] and cap["instrument"]["mock"] and C.validate(cap) == []
    assert cap["restore"]["ok"] and cap["run"]["error"] is None and cap["link"]["ok_throughout"]
    for a, v in {tw.A_ES_CONTROL: 0x0360, tw.A_ES_HORZ: 0x0005, tw.A_VS: 0x1800}.items():
        assert fb.drp[a] == v, f"{a:#x} not restored"
    for a in tw.QUALIFIER_ADDRS + tw.QUAL_MASK_ADDRS + tw.SDATA_MASK_ADDRS:        # all thirty static words (GTHE4: ten of each, 96D2)
        assert fb.drp[a] == 0, f"{a:#x} not restored"
    assert (fb.reg[H.R_DRIVE] & 31) == 0b11000


def test_measured_ber_follows_the_model_it_was_drawn_from():
    fb, cap = _scan(seed=5, target_ber=1e-7)
    checked = 0
    for q in C.flat_points(cap):
        if q["measured"] and q["err"] >= 200:
            model = fb.ber(q["h"], q["v"], 0)
            assert q["ber"] == pytest.approx(model, rel=0.35), (q["h"], q["v"], q["ber"], model)
            checked += 1
    assert checked > 20


def test_width_and_height_come_from_open_points_only():
    fb, cap = _scan(seed=2, target_ber=1e-6)
    e = C.eye_at(cap, 1e-6)
    st = cap["settings"]
    # analytic reference: the points of the model open at 1e-6 along the row nearest 0 mV and the column nearest 0 UI
    row_open = [h for h in sorted({p["h"] for p in cap["points"]}) if fb.ber(h, 0, 0) <= 1e-6 * 0.5]
    assert e["width_counts"] >= (max(row_open) - min(row_open)) - 2 * st["hstep"]
    assert e["width_counts"] <= (max(row_open) - min(row_open)) + 2 * st["hstep"]
    assert e["width_ui"] == pytest.approx(e["width_counts"] * st["ui_per_count"])
    assert e["height_mv"] == pytest.approx(e["height_codes"] * 1.5)
    assert e["counts"]["shallow"] == 0


def test_eye_responds_to_equaliser_and_swing():
    _, lpm = _scan(seed=1, lpm=True, target_ber=1e-6)
    _, dfe = _scan(seed=1, lpm=False, target_ber=1e-6)
    assert dfe["settings"]["ut_signs"] == [0, 1] and len(dfe["points"]) == 2 * len(lpm["points"])
    assert C.eye_at(dfe, 1e-6)["counts"]["open"] >= C.eye_at(lpm, 1e-6)["counts"]["open"]
    fb = fake.FakeBoard(seed=1, drive_diff=0b01000)
    small = scan.run_scan(H.EyeHW(fb), scan.ScanConfig(target_ber=1e-6, hstep=4, vstep=16, vmax=112), synthetic=True, design={})
    assert C.eye_at(small, 1e-6)["counts"]["open"] < C.eye_at(lpm, 1e-6)["counts"]["open"]
    assert small["settings"]["tx"]["diff"] == 0b01000


def test_the_scan_refuses_a_build_without_the_eye_scan_circuit():
    fb = fake.FakeBoard()
    fb.drp[tw.A_ES_CONTROL] = 0x0060                       # ES_EYE_SCAN_EN and ES_ERRDET_EN clear
    with pytest.raises(H.EyeScanError, match="es.xdc"):
        H.EyeHW(fb).setup()
    fb2 = fake.FakeBoard()
    fb2.reg[H.R_FEATURES] = 0x01
    with pytest.raises(H.EyeScanError, match="no eye-scan registers"):
        H.EyeHW(fb2).setup()
    fb3 = fake.FakeBoard()
    fb3.drp[tw.A_ES_CONTROL] |= 1 << 10                    # somebody else's run bit
    with pytest.raises(H.EyeScanError, match="another user"):
        H.EyeHW(fb3).setup()


def test_restore_reports_a_word_that_did_not_come_back():
    fb = fake.FakeBoard()
    eh = H.EyeHW(fb)
    eh.setup()
    orig = fb.wr

    def lossy(a, v):
        orig(a, v)
        if a == H.R_CMD and v & 2 and fb.reg.get(H.R_DRP_ADDR) == tw.A_ES_HORZ:
            fb.drp[tw.A_ES_HORZ] ^= 0x10
    fb.wr = lossy
    r = eh.restore()
    assert r["ok"] is False and "0x04f" in r["mismatch"]


def test_validate_rejects_mock_mismatch_and_out_of_range_counts():
    _, cap = _scan()
    bad = json.loads(json.dumps(cap))
    bad["instrument"]["mock"] = False
    assert any("mock" in e for e in C.validate(bad))
    bad = json.loads(json.dumps(cap))
    bad["points"][0]["rungs"][0]["samp"] = 70000
    assert any("out of range" in e for e in C.validate(bad))


def test_margin_never_passes_a_synthetic_capture_and_states_the_post_equaliser_caveat():
    _, cap = _scan(target_ber=1e-6)
    m = api.margin(cap, 1e-6)
    assert m["pass"] is False and any("SYNTHETIC" in r for r in m["reasons"]) and m["post_equaliser"] is True and "AFTER the equaliser" in m["note"]


def test_page_data_carries_only_computed_numbers_and_the_page_builds_for_one_and_two_captures():
    _, a = _scan(seed=1, target_ber=1e-6)
    _, b = _scan(seed=2, lpm=False, target_ber=1e-6)
    d = api.page_data(a)
    assert len(d["depths"]) == 10 and d["depths"][0]["n"] == 3 and all(len(r) == len(d["h"]) for r in d["depths"][0]["rows"])
    assert d["summary"]["eye"]["depth"] == 1e-6
    h1 = page.build_page([a])
    h2 = page.build_page([a, b], ["LPM", "DFE"])
    assert "SYNTHETIC" in h1 and "<title>RX Eye Scan Viewer</title>" in h1 and h2.count("fda-eye-page-data/1") == 2
    assert "</script><script" not in h1.split('id="data">')[1].split("</script>")[0]
    with pytest.raises(ValueError):
        page.build_page([a, b, a])


def test_svgs_are_well_formed_and_mark_synthetic_and_bounds():
    import xml.dom.minidom as md
    _, cap = _scan(target_ber=1e-9)
    for s in (svg.heatmap_svg(cap, 1e-9), svg.bathtub_svg(cap, 1e-9)):
        md.parseString(s)
        assert "SYNTHETIC" in s
    assert "3/bits bound" in svg.bathtub_svg(cap, 1e-9)


def test_marching_squares_finds_a_level_between_two_values():
    z = [[0.0, 0.0], [2.0, 2.0]]
    segs = svg.contours(z, 1.0)
    assert len(segs) == 1 and segs[0][0][1] == pytest.approx(0.5) and segs[0][1][1] == pytest.approx(0.5)
    assert svg.contours([[0.0, None], [2.0, 2.0]], 1.0) == []


def test_cli_fake_run_plot_page_compare(tmp_path, capsys):
    from flow.eyescan.__main__ import main
    assert main(["run", "--fake", "--out", str(tmp_path), "--name", "a", "--target-ber", "1e-6", "--hstep", "4", "--vstep", "16", "--vmax", "112"]) == 0
    assert main(["run", "--fake", "--out", str(tmp_path), "--name", "b", "--target-ber", "1e-6", "--hstep", "4", "--vstep", "16", "--vmax", "112", "--eq", "dfe", "--seed", "3"]) == 0
    assert main(["plot", str(tmp_path / "a.json"), "-o", str(tmp_path), "--ber", "1e-6"]) == 0
    assert main(["page", str(tmp_path / "a.json"), str(tmp_path / "b.json"), "-o", str(tmp_path / "p.html")]) == 0
    assert main(["compare", str(tmp_path / "a.json"), str(tmp_path / "b.json"), "--ber", "1e-6"]) == 0
    out = capsys.readouterr().out
    assert "SYNTHETIC" in out
    assert (tmp_path / "a_eye.svg").exists() and (tmp_path / "p.html").stat().st_size > 10_000
    assert main(["api", str(tmp_path / "a.json"), "--what", "margin", "--ber", "1e-6"]) == 0
    assert main(["run", "--out", str(tmp_path), "--lock-text", "97: wrong prefix"]) == 2


def test_estimate_seconds_is_dominated_by_clean_points_at_depth():
    cfg = scan.ScanConfig(target_ber=1e-9)
    e = scan.estimate_seconds(cfg, 32)
    assert e["points"] == 33 * 31 and 0.3 < e["clean_point_s"] < 0.7
    assert scan.estimate_seconds(scan.ScanConfig(target_ber=1e-12), 32)["clean_point_s"] > 100 * e["clean_point_s"] / 10


def test_host_register_addresses_match_the_register_map():
    from designs.b96_kr260_10g import regmap
    by = {n: a for a, n, *_ in regmap.REGS}
    assert (by["DRP_ADDR"], by["DRP_DATA"], by["ES_CMD"], by["ES_STAT"], by["ES_POINT"], by["ES_TMO"], by["ES_RES"], by["GT_DRIVE"]) == (
        H.R_DRP_ADDR, H.R_DRP_DATA, H.R_CMD, H.R_STAT, H.R_POINT, H.R_TMO, H.R_RES, H.R_DRIVE)
    assert by["FEATURES"] == H.R_FEATURES and by["GT_CTRL"] == H.R_GT_CTRL
    assert "bit 4 EYESCAN" in [d for a, n, _, _, d in regmap.REGS if n == "FEATURES"][0] and H.FEATURE_EYESCAN == 0x10


def test_partial_feed_builds_a_capture_the_page_can_draw(tmp_path):
    from flow.eyescan.__main__ import _partial_capture, main
    part = tmp_path / "x.partial.jsonl"
    assert main(["run", "--fake", "--out", str(tmp_path), "--name", "full", "--target-ber", "1e-6", "--hstep", "4", "--vstep", "16", "--vmax", "112", "--partial", str(part)]) == 0
    full = C.load(tmp_path / "full.json")
    (tmp_path / "x.partial.header.json").write_text(json.dumps({k: v for k, v in full.items() if k != "points"}))
    cap = _partial_capture(part)
    assert len(cap["points"]) == len(full["points"]) and api.page_data(cap)["cells"]


def test_the_tx_sweep_never_exceeds_the_shipped_swing_or_3_db_cursors(tmp_path, capsys):
    from flow.eyescan.__main__ import main
    assert main(["run", "--out", str(tmp_path), "--lock-text", "96D: x", "--tx-diff", "25", "--serial", "x"]) == 2
    assert main(["run", "--out", str(tmp_path), "--lock-text", "96D: x", "--tx-post", "13", "--serial", "x"]) == 2
    assert "refused" in capsys.readouterr().err


def test_incomplete_or_failed_scan_never_passes():
    _, cap = _scan(target_ber=1e-6)
    assert C.is_complete(cap)
    cap["synthetic"] = False; cap["instrument"]["mock"] = False
    ok = api.margin(cap, 1e-6)
    assert not any("incomplete" in r for r in ok["reasons"])
    cap["points"] = cap["points"][: len(cap["points"]) // 2]
    assert not C.is_complete(cap) and any("incomplete" in r for r in api.margin(cap, 1e-6)["reasons"]) and not api.margin(cap, 1e-6)["pass"]


def test_scan_restores_equaliser_even_if_the_scan_fails_and_tx_drive_is_clamped():
    fb = fake.FakeBoard(lpm=True)
    eh = H.EyeHW(fb)
    orig = eh.point
    def boom(*a, **k):
        raise H.EyeScanError("injected")
    eh.point = boom
    cap = scan.run_scan(eh, scan.ScanConfig(equaliser="dfe", hstep=16, vstep=64), synthetic=True, design={})
    assert cap["run"]["error"] and "injected" in cap["run"]["error"] and cap["restore"]["ok"] and eh.equaliser() == "LPM" and not (fb.reg[H.R_DRIVE] & 0x10000)
    assert not C.is_complete(cap)
    with pytest.raises(ValueError):
        H.EyeHW(fb).set_tx_drive(25, 0, 0)
