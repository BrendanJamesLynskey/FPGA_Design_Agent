"""Brief 68: the documentation checker (flow/handover.py, flow/doccheck.py), including the adversarial cases: a README
must not pass with an empty or placeholder gaps section, an invented number, or a number vouched for by itself."""
from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest

from flow import doccheck as D
from flow import handover as H

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "designs" / "b2_mic_pdm"          # the worked example


@pytest.fixture
def h():
    return H.load(EX)


def errs(h, readme=None):
    return H.problems(EX, h, readme)[0]


def has(es, pat):
    return any(re.search(pat, e) for e in es)


def test_example_is_clean(h):
    e, stale = H.problems(EX, h)
    assert e == [] and stale == []


def test_renderings_are_deterministic(h):
    prose = H.prose_blocks((EX / "README.md").read_text())
    assert H.render_all(h, EX, prose) == H.render_all(copy.deepcopy(h), EX, prose)


def test_empty_gaps_fail(h):
    h["gaps"] = []
    assert has(errs(h), r"schema: gaps")


@pytest.mark.parametrize("text", ["TBD", "n/a", "none", "...", "TODO: write the gaps", "-", "Nothing.",
                                  "n/a n/a n/a n/a n/a", "gap gap gap gap gap", "None known. None known. None."])
def test_placeholder_gap_fails(h, text):
    h["gaps"][0]["text"] = text
    assert has(errs(h), r"placeholder|gaps\[0\]: under|schema")


def test_short_gap_fails(h):
    h["gaps"][0]["text"] = "not measured yet"
    assert has(errs(h), r"gaps\[0\]: under")


# --- the review's defeats (brief 68 adversarial pass), kept as regressions
def test_missing_hash_is_an_error_not_stale(h):
    h["measurements"][0]["value"] = 1
    del h["measurements"][0]["sha256"]
    assert has(errs(h), r"M1: value or sha256 not filled")


def test_unfilled_value_does_not_crash(h):
    del h["measurements"][0]["value"]
    assert has(errs(h), r"M1: value or sha256 not filled")


@pytest.mark.parametrize("field,where", [("summary", "summary"), ("gap", "gaps[0].text"), ("cond", "evidence[2].conditions")])
def test_invented_number_in_free_text_fails(h, field, where):
    if field == "summary":
        h["summary"] += " It runs at 733 MHz."
    elif field == "gap":
        h["gaps"][0]["text"] += " Exactly 4271 clocks."
    else:
        h["evidence"][2]["conditions"] += " Worst case 9999 runs."
    assert has(errs(h), re.escape(where) + r": number (733|4271|9999)")


@pytest.mark.parametrize("hidden", ["&#52;&#57;&#57;&#57;", "49<b>99</b>", "49<!-- -->99", "0x1F4F", "1e9", "12_345",
                                    "a ]( b 4999 c ) d"])
def test_hidden_numbers_in_prose_fail(h, hidden):
    rd = (EX / "README.md").read_text().replace("<!-- prose:gaps -->\n", f"<!-- prose:gaps -->\nCost {hidden} LUT.\n")
    assert has(errs(h, rd), r"prose:gaps: number")


def test_prose_placeholder_fails(h):
    rd = (EX / "README.md").read_text().replace("<!-- prose:next -->\n", "<!-- prose:next -->\nTODO: say more.\n")
    assert has(errs(h, rd), r"prose:next: placeholder")


def test_clock_must_be_a_create_clock_on_that_port(h):
    h["clocks"][0]["mhz"] = 33                       # appears in LVCMOS33, not a clock
    assert has(errs(h), r"clock CLK100MHZ: 33 MHz")


def test_clock_from_own_handover_fails(h):
    h["clocks"][0]["source"] = "designs/b2_mic_pdm/handover.yaml"
    assert has(errs(h), r"clock CLK100MHZ")


def test_evidence_cannot_be_its_own_readme(h):
    h["evidence"][1]["record"] = "designs/b2_mic_pdm/README.md"
    assert has(errs(h), r"E2: record .* rendering of this handover")


def test_evidence_record_must_be_a_file(h):
    h["evidence"][1]["record"] = "results/board_v2"
    assert has(errs(h), r"E2: record results/board_v2 is not a file")


def test_short_board_conditions_fail(h):
    h["evidence"][2]["conditions"] = "a b c"
    assert has(errs(h), r"E3: hardware evidence must state")


def test_ci_claim_needs_a_test_file(h):
    h["evidence"][1]["how"] = "ci"
    h["evidence"][1]["record"] = "results/04f/mutation_t1.json"     # named in ci.yml as an argument, not a test
    assert has(errs(h), r"E2: how: ci")


def test_required_category_must_be_numeric(h):
    h["measurements"][0]["field"] = "builds.b2_mic_pdm.vivado"
    h["measurements"][0]["value"] = "2026.1"
    assert has(errs(h), r"M1: a resources measurement must be a number")


def test_stage_needs_its_evidence(h):
    h["evidence"][2]["activity"] = "build"
    h["evidence"][2]["conditions"] = ""
    assert has(errs(h), r"board-verified needs a passing board")


def test_agent_needs_agent_run(h):
    h["produced_by"] = "agent"
    assert has(errs(h), r"needs agent_run")


@pytest.mark.parametrize("spelling", ["vivado 2025.2", "Vivado v2025.2", "Vivado-2025.2"])
def test_vivado_spellings(h, spelling):
    h["summary"] += f" Once built with {spelling} here."
    assert has(errs(h), r"names a Vivado release other than 2026.1")


def test_freshness_reports_errors(h):
    f = H.freshness(EX)
    assert f["errors"] == [] and f["stale"] == [] and f["changed_files"] == []


def test_invented_measurement_value_fails(h):
    h["measurements"][2]["value"] = 4.5           # WNS typed by hand, not the record's
    assert has(errs(h), r"M3: value 4.5 is not the record's")


def test_measurement_cannot_cite_its_own_readme(h):
    h["measurements"][0]["record"] = "designs/b2_mic_pdm/README.md"
    h["measurements"][0]["match"] = r"(\d+) LUT"
    del h["measurements"][0]["field"]
    assert has(errs(h), r"M1: a measurement's record must be a results file")


def test_missing_field_fails(h):
    h["measurements"][0]["field"] = "builds.b2_mic_pdm.no_such_field"
    assert has(errs(h), r"M1: cannot read")


def test_changed_record_is_stale_not_wrong(h):
    h["measurements"][0]["sha256"] = "0" * 64
    h["measurements"][0]["value"] = 999
    e, stale = H.problems(EX, h, (EX / "README.md").read_text())
    assert any("M1:" in s for s in stale)
    assert not has(e, r"M1: value")


def test_category_without_measurement_or_gap_fails(h):
    h["gaps"] = [g for g in h["gaps"] if g["about"] != "latency"]
    assert has(errs(h), r"'latency': no measurement and no gap")


def test_failed_evidence_needs_a_gap(h):
    h["evidence"][0]["result"] = "fail"
    assert has(errs(h), r"E1: result fail needs a gap")


def test_failed_gate_needs_a_gap(h):
    h["state"]["gates"]["timing"] = "fail"
    assert has(errs(h), r"state.gates.timing: fail needs a gap")


def test_board_evidence_needs_conditions(h):
    h["evidence"][2]["conditions"] = ""
    assert has(errs(h), r"E3: hardware evidence must state")


def test_ci_claim_must_be_true(h):
    h["evidence"][1]["how"] = "ci"                # a results JSON is not something CI runs
    assert has(errs(h), r"E2: how: ci")


def test_clock_must_match_xdc(h):
    h["clocks"][0]["mhz"] = 125
    assert has(errs(h), r"clock CLK100MHZ: 125 MHz does not agree")


def test_other_vivado_release_fails(h):
    h["summary"] += " Built with Vivado 2025.2 originally."
    assert has(errs(h), r"names a Vivado release other than 2026.1")


def test_tool_must_be_2026_1(h):
    h["target"]["tool"] = "Vivado 2025.2"
    assert has(errs(h), r"target.tool")


def test_invented_number_in_prose_fails(h):
    rd = (EX / "README.md").read_text().replace("<!-- prose:measured -->\n",
                                                 "<!-- prose:measured -->\nThe microphone ran at 3.917 MHz.\n")
    assert has(errs(h, rd), r"prose:measured: number 3.917")


def test_number_from_record_in_prose_passes(h):
    rd = (EX / "README.md").read_text().replace("<!-- prose:measured -->\n",
                                                 "<!-- prose:measured -->\nThe first window had 541763 ones.\n")
    assert not has(errs(h, rd), r"prose:measured: number")


def test_number_hidden_in_code_span_still_checked(h):
    rd = (EX / "README.md").read_text().replace("<!-- prose:gaps -->\n", "<!-- prose:gaps -->\nFmax `287.3 MHz`.\n")
    assert has(errs(h, rd), r"number 287.3")


def test_hand_edit_outside_prose_fails(h):
    rd = (EX / "README.md").read_text().replace("| 3.436 ns |", "| 4.000 ns |")
    assert has(errs(h, rd), r"README.md is not current")


def test_id_must_match_directory(h):
    h["id"] = "other"
    assert has(errs(h), r"id 'other' is not the directory name")


def test_prose_blocks_survive_regeneration(h):
    rd = (EX / "README.md").read_text().replace("<!-- prose:what -->\n", "<!-- prose:what -->\nA note.\n")
    out = H.render_all(h, EX, H.prose_blocks(rd))["README.md"]
    assert "<!-- prose:what -->\nA note.\n<!-- /prose:what -->" in out


def test_agent_md_cites_records_with_hashes(h):
    a = H.render_agent(h, EX)
    for m in h["measurements"]:
        assert m["record"] in a and m["sha256"][:10] in a
    assert len(a) // 4 < 2000


# ------------------------------------------------------------------------------------------------ results READMEs
GOOD = """# results/x: a folder

This folder holds the records of a made-up brief, written for the checker's tests and nothing else at all.

## Records

- `a.json`: the one record, with the value 12.5 in it.

## Reproduce

Run `python3 make_a.py` (no Vivado, no board); it writes a.json in a second.

## Known gaps and limits

- One run only; the value was not repeated, so its spread is unknown.
"""


def _results(tmp_path, readme, data='{"v": 12.5}'):
    d = tmp_path / "x"
    d.mkdir()
    (d / "a.json").write_text(data)
    (d / "README.md").write_text(readme)
    return d


def test_results_good(tmp_path):
    assert D.check_results(_results(tmp_path, GOOD)) == []


@pytest.mark.parametrize("gaps", ["", "- none", "- n/a", "- TBD", "TODO", "None. None. None. None. None.", "x x x x x",
                                  "[a](b.c.d.e.f)"])
def test_results_empty_or_placeholder_gaps_fail(tmp_path, gaps):
    rd = GOOD.split("## Known gaps and limits")[0] + "## Known gaps and limits\n\n" + gaps + "\n"
    assert has(D.check_results(_results(tmp_path, rd)), r"Known gaps and limits'?: ")


def test_results_missing_section_fails(tmp_path):
    rd = GOOD.replace("## Reproduce", "## How")
    assert has(D.check_results(_results(tmp_path, rd)), r"no '## Reproduce'")


def test_results_measured_numbers_checked(tmp_path):
    rd = GOOD + "\n## Measured\n\nThe value was 12.5, and the other was 13.1.\n"
    es = D.check_results(_results(tmp_path, rd))
    assert has(es, r"number 13.1") and not has(es, r"number 12.5")


def test_results_measured_cannot_vouch_for_itself(tmp_path):
    rd = GOOD + "\n## Measured\n\n77.7\n"
    d = _results(tmp_path, rd)
    assert has(D.check_results(d), r"number 77.7")    # the README itself is not a record


def test_results_fenced_headings_do_not_count(tmp_path):
    rd = GOOD.split("## Records")[0] + "```\n## Records\nfiles here and there\n## Reproduce\nrun it now please ok\n" \
        "## Known gaps and limits\nsome gaps exist right here\n```\n"
    assert has(D.check_results(_results(tmp_path, rd)), r"no '## Records'")


def test_results_measured_variants_checked(tmp_path):
    rd = GOOD + "\n## Measured results\n\nLUTs 99999.\n"
    assert has(D.check_results(_results(tmp_path, rd)), r"number 99999")


def test_results_repeated_heading_fails(tmp_path):
    assert has(D.check_results(_results(tmp_path, GOOD + "\n## Records\n\nanother list of the files here.\n")), r"repeats")


def test_whole_tree_check_runs():
    e, w, cov = D.run()
    assert set(cov) == {"designs", "agent runs", "ip_lib", "results"}
