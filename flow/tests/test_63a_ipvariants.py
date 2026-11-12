"""Brief 63A: the ip_lib variants schema, its validation and the read API (flow/ipvariants.py). No simulator, no Vivado:
the measured numbers come from the committed ip_lib/<block>/char/<part>.json files."""
from __future__ import annotations

import itertools
import json

import pytest

from flow import ipvariants as iv
from ip_lib.fir import model as fir_model


def test_every_entry_with_variants_validates():
    assert set(iv.entries_with_variants()) >= {"fir", "dds_awg", "adc_histogram"}
    errs = [e for b in iv.entries_with_variants() for e in iv.validate(b)]
    assert not errs, errs


@pytest.mark.parametrize("expr", ["__import__('os')", "TAPS.real", "open('x')", "[1, 2]", "lambda: 1", "TAPS if x else 1"])
def test_expressions_refuse_anything_but_arithmetic(expr):
    with pytest.raises(ValueError):
        iv.evaluate(expr, {"TAPS": 16})


def test_expression_functions():
    assert iv.evaluate("clog2(ceil(TAPS / FOLD))", {"TAPS": 33, "FOLD": 8}) == 3
    assert iv.evaluate("clog2(1)", {}) == 0
    assert iv.evaluate("0.5 * ceil(2**LUT_W * OUT_W / 18432)", {"LUT_W": 12, "OUT_W": 16}) == 2.0


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


def test_choose_throughput_puts_the_parallel_form_first():
    ranked = iv.choose("fir", {"TAPS": 16, "FOLD": 4}, objective="throughput")
    assert ranked[0]["variant"] == "lut_mult"


def test_choose_rejects_a_slow_rate():
    ranked = iv.choose("fir", {"TAPS": 64, "DATA_W": 12, "COEF_W": 12, "FOLD": 16}, need_ii=20)
    bad = {r["variant"] for r in ranked if not r["fits"]}
    assert "serial" in bad


def test_search_finds_entries_by_words():
    assert [e["block"] for e in iv.search("fir filter")] == ["fir"]
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
    """The hard resources each variant declares are the ones synthesis actually used (brief 62's plan check, applied to
    the library's own data): a planned DSP built in LUTs, or an adder tree pulled into DSP slices, fails here."""
    bad = []
    for b in iv.entries_with_variants():
        for r in iv.measured(b):
            pr = iv.predict(b, r["variant"], r["params"])["uses"]
            for k in ("dsp", "bram_tiles"):
                if k in pr and r.get(k) != pr[k]:
                    bad.append((b, r["variant"], r["params"], k, r.get(k), pr[k]))
    assert not bad, bad
