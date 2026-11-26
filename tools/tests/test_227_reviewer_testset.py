"""Brief 227: the scoring of the reviewer test set (tools/reviewer_testset/score.py) and the naming rule of run.py. No model is called.

Covered: Wilson intervals (against known values), recall and specificity by stratum with group B and C kept apart, group G described and never scored, the two trivial
reviewers, run-to-run agreement, the count of blocking questions that changed nothing, the rule that the first run is the primary, the ids file (counts, no overlap,
the excluded id on neither side), and "named the fact" as a regex over blocking findings only."""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reviewer_testset"))
import run as RUN        # noqa: E402
import score as S        # noqa: E402

IDS = yaml.safe_load((Path(__file__).resolve().parents[1] / "reviewer_testset" / "ids.yaml").read_text())


def test_wilson_matches_known_values():
    lo, hi = S.wilson(12, 15)                       # report 226: 12 of 15 caught is 55% to 93%
    assert round(lo, 2) == 0.55 and round(hi, 2) == 0.93
    assert S.wilson(0, 0) == (0.0, 1.0)
    lo, hi = S.wilson(0, 20)
    assert lo == 0.0 and round(hi, 2) == 0.16


def test_the_ids_file_has_the_groups_of_report_226_and_no_overlap():
    g = IDS["groups"]
    assert {k: len(v["ids"]) for k, v in g.items()} == {"A": 7, "B": 2, "C": 6, "D": 3, "E": 2, "F": 21, "G": 25}
    allids = [i for v in g.values() for i in v["ids"]]
    assert len(allids) == len(set(allids)) and not set(IDS["excluded"]) & set(allids)
    assert all(g[k]["polarity"] == "positive" for k in "ABCD") and all(g[k]["polarity"] == "negative" for k in "EF") and g["G"]["polarity"] == "candidate"
    assert all(i.startswith("cvdp_agentic_") for k in "ABCDEF" for i in g[k]["ids"]) and all(i.startswith("cvdp_copilot_") for i in g["G"]["ids"])


def rows_for(flags: dict[str, tuple[bool, bool, int]], cond="kb", run=1):
    out = []
    for i, (flag, named, nb) in flags.items():
        grp = next(k for k, v in IDS["groups"].items() if i in v["ids"])
        out.append({"id": i, "group": grp, "condition": cond, "run": run, "flagged": flag, "named": named, "n_blocking": nb, "n_findings": nb + 1, "input_tokens": "1000", "output_tokens": "100"})
    return out


def test_scores_keep_the_strata_apart_and_report_g_without_scoring_it():
    g = IDS["groups"]
    flags = {}
    for n, i in enumerate(g["A"]["ids"]):
        flags[i] = (n < 6, n < 4, 2)                 # 6 flagged, 4 of them named
    for i in g["D"]["ids"]:
        flags[i] = (True, True, 1)
    for i in g["B"]["ids"] + g["C"]["ids"]:
        flags[i] = (False, False, 0)
    for n, i in enumerate(g["E"]["ids"] + g["F"]["ids"]):
        flags[i] = (n < 3, False, 2 if n < 3 else 0)
    for i in g["G"]["ids"][:5]:
        flags[i] = (True, False, 1)
    s = S.score(rows_for(flags), IDS, "kb")
    assert s["fact_missing"] == {"n": 10, "flagged": 9, "named": 7}
    assert s["borderline"]["n"] == 2 and s["implementation"]["n"] == 6 and s["implementation"]["flagged"] == 0
    assert s["negatives"]["n"] == 23 and s["negatives"]["flagged"] == 3 and s["negatives"]["hard_flagged"] == 2 and s["negatives"]["easy_flagged"] == 1
    assert round(s["precision_fact_missing"], 3) == round(9 / 12, 3)
    assert s["blocking_questions_on_negatives"] == 6
    assert s["g_flagged"]["flagged"] == 5 and s["g_flagged"]["n"] == 5
    md = S.render(s)
    assert "9/10 = 90% [60%, 98%]" in md and "(not scored)" in md and "Flag everything (reference)" in md


def test_the_first_run_is_primary_and_run_to_run_agreement_uses_the_rest():
    g = IDS["groups"]
    i1, i2 = g["A"]["ids"][:2]
    rows = rows_for({i1: (True, True, 1), i2: (True, True, 1)}) + rows_for({i1: (True, True, 1), i2: (False, False, 0)}, run=2)
    s = S.score(rows, IDS, "kb")
    assert s["fact_missing"]["flagged"] == 2 and s["run_to_run"] == {"problems": 2, "same_flag": 1}


def test_csv_round_trip(tmp_path):
    g = IDS["groups"]["A"]["ids"][0]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=RUN.FIELDS)
    w.writeheader()
    w.writerow({"id": g, "group": "A", "condition": "kb", "run": 1, "flagged": 1, "n_blocking": 2, "n_findings": 3, "named": 1, "input_tokens": 10, "output_tokens": 5, "model": "m", "checklist": "c"})
    p = tmp_path / "r.csv"
    p.write_text(buf.getvalue())
    rows = S.load_rows(p)
    assert rows[0]["flagged"] is True and rows[0]["named"] is True and rows[0]["n_blocking"] == 2


def test_named_is_a_regex_over_blocking_findings_only():
    rv = {"findings": [{"missing_fact": "default of SHORT", "question": "What is the default?", "blocking": False},
                       {"missing_fact": "the reset value", "question": "What does count hold in reset?", "blocking": True}]}
    assert RUN.named([r"(?i)default"], rv) is False                     # the matching finding is not blocking
    assert RUN.named([r"(?i)reset value"], rv) is True and RUN.named([], rv) is False
