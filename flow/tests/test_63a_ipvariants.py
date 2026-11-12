"""The ip_lib variants schema, its validation and the read API (flow/ipvariants.py). No simulator, no Vivado:
the measured numbers come from the committed ip_lib/<block>/char/<part>.json files."""
from __future__ import annotations

import itertools
import json
import shutil

import pytest

from flow import ipvariants as iv
from ip_lib.fir import model as fir_model


def test_every_entry_with_variants_validates():
    assert set(iv.entries_with_variants()) >= {"fir", "dds_awg", "adc_histogram"}
    errs = [e for b in iv.entries_with_variants() for e in iv.validate(b)]
    assert not errs, errs


@pytest.mark.parametrize("expr", ["__import__('os')", "TAPS.real", "open('x')", "[1, 2]", "lambda: 1", "TAPS if x else 1", "TAPS +",
                                  "2 ** TAPS", "9 ** 9 ** 9", "pow2(65)", "pow2(TAPS * 10)"])
def test_expressions_refuse_anything_but_arithmetic(expr):
    with pytest.raises(ValueError):
        iv.evaluate(expr, {"TAPS": 16})


def test_expression_functions():
    assert iv.evaluate("clog2(ceil(TAPS / FOLD))", {"TAPS": 33, "FOLD": 8}) == 3
    assert iv.evaluate("clog2(1)", {}) == 0
    assert iv.evaluate("0.5 * ceil(pow2(LUT_W) * OUT_W / 18432)", {"LUT_W": 12, "OUT_W": 16}) == 2.0


def test_fir_declared_timing_matches_the_model():
    """ip.yaml's latency and II expressions agree with the model the simulations measure against."""
    for impl, taps, fold in itertools.product(fir_model.IMPLS, (2, 7, 16, 33, 64), (2, 3, 4, 8, 16)):
        if fold > taps:
            continue
        p = iv.predict("fir", impl, {"TAPS": taps, "FOLD": fold})
        t = fir_model.fir_timing(impl, taps, fold)
        assert (p["latency"], p["ii"]) == (t["latency"], t["ii"]), (impl, taps, fold)


def test_variant_costs_nearest_point_and_exactness():
    rows = {r["variant"]: r for r in iv.variant_costs("fir", {"TAPS": 16, "DATA_W": 16, "COEF_W": 16, "FOLD": 4})}
    assert set(rows) == set(fir_model.IMPLS)
    for r in rows.values():
        assert r["measured"] and r["measured"]["exact"], r["variant"]
    off = {r["variant"]: r for r in iv.variant_costs("fir", {"TAPS": 20, "FOLD": 4})}
    assert all(not r["measured"]["exact"] for r in off.values())
    assert off["serial"]["predicted"]["latency"] == 28


def test_choose_honours_a_dsp_budget():
    ranked = iv.choose("fir", {"TAPS": 16, "FOLD": 4}, budget={"dsp": 0})
    fits = [r["variant"] for r in ranked if r["fits"]]
    assert fits == ["lut_mult"], [(r["variant"], r["reasons"]) for r in ranked]
    assert any("dsp" in why for r in ranked if not r["fits"] for why in r["reasons"])


@pytest.mark.parametrize("params,budget,want_dsp", [
    ({"TAPS": 64, "DATA_W": 12, "COEF_W": 12, "FOLD": 4}, {"dsp": 4}, 16),   # nearest measured row (FOLD 16) has 4
    ({"TAPS": 16, "FOLD": 2}, {"dsp": 5}, 8),                                  # nearest measured row (FOLD 4) has 4
])
def test_choose_checks_the_budget_at_the_requested_point(params, budget, want_dsp):
    """A budget is checked against the cost at the requested point, never against a nearby measured point."""
    rows = {r["variant"]: r for r in iv.choose("fir", params, budget=budget)}
    for v in ("dsp_bram", "dist_ram"):
        assert rows[v]["cost"]["dsp"] == want_dsp
        assert not rows[v]["fits"] and any("dsp" in w for w in rows[v]["reasons"]), rows[v]["reasons"]
        assert rows[v]["measured"]["exact"] is False


def test_choose_needs_off_point_lut_and_fmax_to_be_measured_here():
    rows = {r["variant"]: r for r in iv.choose("fir", {"TAPS": 20, "FOLD": 4}, budget={"lut": 100000}, clock_ns=5)}
    for r in rows.values():
        assert not r["fits"]
        assert any("lut is not known" in w for w in r["reasons"]) and any("Fmax not measured" in w for w in r["reasons"])


@pytest.mark.parametrize("params,variant,needle", [
    ({"TAPZ": 3}, "dsp_bram", "unknown parameter TAPZ"),
    ({"TAPS": 8, "FOLD": 16}, "dsp_bram", "FOLD <= TAPS"),
    ({"TAPS": 128}, "lut_mult", "TAPS <= 64"),
    ({"TAPS": 300}, "serial", "outside 2..256"),
    ({"DATA_W": 24, "COEF_W": 18, "TAPS": 256, "FOLD": 8}, "dsp_bram", "<= 48"),
])
def test_points_outside_the_space_are_refused(params, variant, needle):
    assert any(needle in w for w in iv.check_point("fir", variant, params)), iv.check_point("fir", variant, params)
    with pytest.raises(ValueError, match=needle.split()[0]):
        iv.predict("fir", variant, params)
    row = {r["variant"]: r for r in iv.choose("fir", params, need_ii=1000)}[variant]
    assert not row["fits"] and not row["valid"] and any(needle in w for w in row["reasons"])


def test_lut_mult_at_128_taps_is_not_offered():
    ranked = iv.choose("fir", {"TAPS": 128}, need_ii=1)
    assert not [r["variant"] for r in ranked if r["fits"]], [(r["variant"], r["reasons"]) for r in ranked]


def test_fold_is_ignored_where_it_is_not_used():
    assert iv.check_point("fir", "serial", {"TAPS": 2, "FOLD": 4}) == []
    assert iv.check_point("fir", "lut_mult", {"TAPS": 2, "FOLD": 4}) == []
    assert iv.check_point("fir", "serial", {"FOLD": 1}) == []
    assert iv.check_point("fir", "lut_mult", {"FOLD": 1}) == []
    for v in ("dsp_bram", "dist_ram"):
        assert any("FOLD >= 2" in w for w in iv.check_point("fir", v, {"FOLD": 1}))


@pytest.mark.parametrize("params,needle", [
    ({"TAPS": "16"}, "TAPS='16' is a str, not an int"),
    ({"TAPS": 16.0}, "TAPS=16.0 is a float, not an int"),
    ({"TAPS": True}, "TAPS=True is a bool, not an int"),
])
def test_a_wrong_type_is_named_as_such(params, needle):
    why = iv.check_point("fir", "serial", params)
    assert any(needle in w for w in why) and not any("outside" in w for w in why), why


def test_choose_on_a_part_without_data_says_so_and_ranks_on_predictions():
    ranked = iv.choose("fir", {"TAPS": 16, "FOLD": 4}, part="xc7z020clg484-1", budget={"dsp": 4})
    assert all("no characterisation on xc7z020clg484-1" in r["note"] for r in ranked)
    fits = [r["variant"] for r in ranked if r["fits"]]
    assert fits[0] == "lut_mult" and set(fits) == {"lut_mult", "serial", "dsp_bram", "dist_ram"}


def test_search_finds_entries_by_words():
    assert [e["block"] for e in iv.search("fir filter")] == ["fir"]
    assert [e["block"] for e in iv.search("fir")] == ["fir"]          # whole words: "first" does not match
    assert "dds_awg" in [e["block"] for e in iv.search("sine")]


def test_char_files_have_the_schema_and_one_tool():
    for b in iv.entries_with_variants():
        d = json.loads(iv.char_file(b).read_text())
        assert d["schema"] == iv.SCHEMA and d["tool"].startswith("Vivado 2026.1"), b
        assert all(r["status"] == "ok" for r in d["results"]), b


def test_cli_validates(capsys):
    assert iv.main([]) == 0
    assert "0 problems" in capsys.readouterr().out


def test_measured_dsp_and_bram_match_the_declared_use():
    """The hard resources each variant declares are the ones synthesis actually used (the planner's plan check, applied to
    the library's own data): a planned DSP built in LUTs, or an adder tree pulled into DSP slices, fails here."""
    bad = []
    for b in iv.entries_with_variants():
        for r in iv.measured(b):
            pr = iv.predict(b, r["variant"], r["params"])["uses"]
            for k in ("dsp", "bram_tiles"):
                if k in pr and r.get(k) != pr[k]:
                    bad.append((b, r["variant"], r["params"], k, r.get(k), pr[k]))
    assert not bad, bad


@pytest.fixture
def lib(tmp_path, monkeypatch):
    """A scratch copy of the library and its tests, so validation can be shown a broken entry."""
    for d in ("ip_lib/fir", "ip_lib/dds_awg", "ip_lib/adc_histogram"):
        shutil.copytree(iv.ROOT / d, tmp_path / d, ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "hil/tests").mkdir(parents=True)
    shutil.copy(iv.ROOT / "hil/tests/test_30_ip_rtl.py", tmp_path / "hil/tests")
    monkeypatch.setattr(iv, "ROOT", tmp_path)
    monkeypatch.setattr(iv, "IP", tmp_path / "ip_lib")
    return tmp_path


def _edit(path, old, new):
    t = path.read_text()
    assert old in t
    path.write_text(t.replace(old, new, 1))


def test_validate_refuses_a_variant_without_rtl_or_tests(lib):
    y = lib / "ip_lib/fir/ip.yaml"
    _edit(y, "    - lut_mult\n    note: implementation variant", "    - lut_mult\n    - csd\n    note: implementation variant")
    _edit(y, "variants:\n", "variants:\n  csd:\n    summary: x\n    when: x\n    uses: {dsp: 0}\n    latency: 3\n    ii: 1\n")
    errs = iv.validate("fir")
    assert any("csd: no RTL branch" in e for e in errs), errs
    assert any("csd: no sweep_tested point" in e for e in errs), errs
    assert any("csd: not named in any test file" in e for e in errs), errs


@pytest.mark.parametrize("old,new,needle", [
    ("    latency: 2 + clog2(TAPS)\n", "    latency: 2 + clog2(TAPS\n", "does not parse"),
    ("  serial:\n    summary:", "  serial: 7\n  serialx:\n    summary:", "serial: not a mapping"),
])
def test_validate_reports_malformed_input_without_a_traceback(lib, old, new, needle):
    _edit(lib / "ip_lib/fir/ip.yaml", old, new)
    errs = iv.validate("fir")
    assert any(needle in e for e in errs), errs


def test_validate_checks_rows_against_declared_use_status_and_tool(lib):
    f = lib / "ip_lib/fir/char/xc7a100tcsg324-1.json"
    d = json.loads(f.read_text())
    d["tool"] = "Vivado 2025.2 (build 1)"
    d["results"][0]["dsp"] = 128
    d["results"][1]["status"] = "error: synthesis failed"
    f.write_text(json.dumps(d))
    errs = iv.validate("fir")
    assert any("is not Vivado 2026.1" in e for e in errs)
    assert any("measured dsp 128" in e for e in errs)
    assert any("status 'error: synthesis failed'" in e for e in errs)
