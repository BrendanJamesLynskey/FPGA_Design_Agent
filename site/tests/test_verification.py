"""The Verification page (brief 81): no typed numbers in the prose, every value read from a record, every check named on the map
exists in the flow's code, every link resolves, and the matrices are the records' rows."""
import copy
import json
import sys
from pathlib import Path

import pytest
import yaml

SITE = Path(__file__).resolve().parent.parent
ROOT = SITE.parent
sys.path.insert(0, str(SITE))
sys.path.insert(0, str(ROOT))
import build  # noqa: E402
import verification  # noqa: E402
import verification_page  # noqa: E402

Y = yaml.safe_load((SITE / "verification" / "verification.yaml").read_text())


@pytest.fixture(scope="module")
def data():
    return verification.build()


def test_page_is_current_and_numbers_are_sourced():
    d = build.load_data(None)
    pages, bad = build.build(SITE / "public", d)
    assert not bad
    assert "verification.html" in pages
    assert pages["verification.html"] == (SITE / "public" / "verification.html").read_text()


@pytest.mark.parametrize("text", ["It found 12 faults.", "Floor of 90 % holds.", "Ran at 125 MHz", "Depth 20 proofs"])
def test_a_typed_number_in_prose_is_refused(text):
    with pytest.raises(verification.ContractError, match="typed number"):
        verification._fill("t", text, {})


def test_names_with_digits_are_allowed():
    assert verification._fill("t", "AXI4-Lite and AXI4-Stream on Vivado 2026.1, stage 2, V3, T1", {})


def test_a_missing_value_is_refused():
    with pytest.raises(verification.ContractError, match="no value named"):
        verification._fill("t", "Got {nothing}.", {})


def test_every_value_is_in_its_source_file(data):
    for k, spec in Y["values"].items():
        assert list(ROOT.glob(spec["source"])), f"{k}: {spec['source']}"
    assert set(Y["values"]) <= set(data["content"]["values"])


def test_no_authored_text_holds_a_number():
    """Everything the page says is a placeholder or a name (the build refuses otherwise; this reads the YAML directly)."""
    def walk(x, where):
        if isinstance(x, str):
            verification._fill(where, x, {k: 0 for k in Y["values"]} | {k: 0 for k in
                               ("s_seeds_txt", "px_n", "px_equal", "px_vendor", "pf_checks", "pf_inside", "ax_bugs", "ax_rules", "ax_data", "cex_flag_step", "cex_silent_step")})
        elif isinstance(x, dict):
            for k, v in x.items():
                if k not in ("values", "axi_rows", "pin_fault", "links"):
                    walk(v, f"{where}.{k}")
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, f"{where}[{i}]")
    walk({k: v for k, v in Y.items() if k in ("text", "techniques")}, "yaml")


def test_every_check_named_on_the_map_exists_in_the_code():
    code = "".join(p.read_text() for d in ("flow", "agent") for p in (ROOT / d).rglob("*.py") if "tests" not in p.parts)
    for m in Y["map"]:
        for names in m["cells"].values():
            for n in names:
                if n == "hidden tests":
                    continue
                assert n in code, f"{n} is not a check name in flow/ or agent/"


def test_only_the_adversarial_review_is_off_the_map():
    """It is a way of building checks, not a check that runs in a stage."""
    on_map = {m["technique"] for m in Y["map"]}
    assert {t["id"] for t in Y["techniques"]} - on_map == {"adversarial"}


def test_a_map_with_an_unknown_technique_or_stage_is_refused(monkeypatch):
    bad = copy.deepcopy(Y)
    bad["map"][0]["technique"] = "nothing"
    monkeypatch.setattr(verification.yaml, "safe_load", lambda _t: bad)
    with pytest.raises(verification.ContractError, match="no technique"):
        verification.build()
    bad = copy.deepcopy(Y)
    bad["map"][0]["cells"] = {"s_nowhere": ["x"]}
    monkeypatch.setattr(verification.yaml, "safe_load", lambda _t: bad)
    with pytest.raises(verification.ContractError, match="no stage"):
        verification.build()


def test_every_technique_has_the_three_parts_and_real_links(data):
    for t in data["content"]["techniques"]:
        for k in ("what", "catches", "cannot", "how", "evidence"):
            assert t[k].strip(), (t["id"], k)
        assert t["links"], t["id"]
        for l in t["links"]:
            assert (ROOT / l["path"].rstrip("/*")).exists(), l


def test_cdc_matrix_is_the_records_rows(data):
    t = json.loads((ROOT / "results/16_cdc_gate_2026_1/mutant_table.json").read_text())
    M = data["content"]["cdc"]
    assert len(M["rows"]) == sum(1 for r in t["rows"] if r["kind"] == "mutant")
    assert M["totals"][3] == sum(1 for r in t["rows"] if r["kind"] == "mutant" and r["gate_flags"])
    # the claim "report_cdc alone is weaker than the gate" is the record's; a flipped record would flip the page
    assert M["totals"][0] < M["totals"][3]


def test_axi_matrix_marks_the_stream_runs_as_unseen_by_amd(data):
    rows = {r["tag"]: r for r in data["content"]["axi"]["rows"]}
    assert rows["stream_packets_lose_last"]["flags"][2] is None and rows["stream_packets_keep_wire"]["flags"][2] is None
    assert rows["periph_regs_no_strb"]["flags"] == [False, True, False]      # a data bug: no protocol rule, the scoreboard
    assert all(rows[t]["flags"][0] for t in ("periph_regs_b_early", "periph_regs_exokay", "master_inject"))


def test_pin_fault_designs_share_their_sources_and_differ_in_constraints(data):
    assert [s["ok"] for s in data["content"]["pin"]["steps"]] == [True, True, False]


def test_the_pin_check_refuses_designs_with_different_sources(monkeypatch):
    spec = dict(Y["pin_fault"], faulty="designs/t1_dimmer_counter")
    with pytest.raises(verification.ContractError):
        verification.pin_fault(spec, {"pf_inside": 7, "pf_checks": 7})


def test_formal_table_marks_k_induction_only_for_prove_jobs(data):
    rows = data["content"]["formal"]["rows"]
    assert any(r["method"].startswith("k-induction") for r in rows)
    assert all(not r["method"].startswith("k-induction") for r in rows if "bounded" in r["method"])


def test_page_is_native_html_and_in_the_nav():
    page = (SITE / "public" / "verification.html").read_text()
    assert 'href="verification.html"' in page and "<details" in page
    assert "id=\"formal\"" in page and "{" not in verification_page.fm(1)
    for t in ("Vivado 2026.1",):
        assert t in page
    for banned in ("2025.2", "Vivado 2025"):
        assert banned not in page
