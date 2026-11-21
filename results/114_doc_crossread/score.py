"""Brief 114 scoring: the pre-registered rules in code (no model scores anything). Reads the run records under runs/ and writes results.json.

    python3 results/114_doc_crossread/score.py [--runs DIR] [--out results.json]

A record row is a document fact compared with the code. Every rule below is the one in PREREGISTRATION.md ("Scoring").
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
LO, HI = 0xE7, 0xF5


def _names(r: dict) -> str:
    return (r["subject"] + " " + (r.get("field") or "")).upper()


def _addrs(r: dict) -> list[int]:
    d = r["doc"]
    return list(d["values"] or []) or ([d["value"]] if isinstance(d["value"], int) else [])


def _dis(rows: list[dict], kind: tuple[str, ...], pred) -> list[dict]:
    return [r for r in rows if r["status"] == "disagree" and r["kind"] in kind and r["doc"]["quote_ok"] and pred(r)]


MASKS = ("QUALIFIER", "QUAL_MASK", "SDATA_MASK")


def targets(case: str, rows: list[dict]) -> dict[str, bool | list[str] | None]:
    """The pre-registered detections for one run of a case (None = no rule for this case)."""
    if case == "h1_96d_five_word":
        return {"word_count_flagged": bool(_dis(rows, ("word_count",), lambda r: any(m in _names(r) for m in MASKS) and r["doc"]["value"] == 10)),
                "addresses_flagged": bool(_dis(rows, ("address",), lambda r: any(m in _names(r) for m in MASKS) and any(LO <= a <= HI for a in _addrs(r))))}
    if case == "h2_96d2_ten_word":
        bad = [r for r in rows if r["status"] == "disagree" and any(m in _names(r) for m in MASKS)]
        return {"mask_rows_disagree": [r["id"] for r in bad]}                      # pass = empty
    if case == "h3_clock_phase":
        hit = [r for r in rows if "CLK_PHASE_SEL" in (_names(r) + " " + r["doc"].get("statement", "").upper())]
        return {"reader_mentions_clock_phase_attribute": bool(hit), "rows": [f"{r['id']}:{r['status']}:{r['kind']}" for r in hit]}
    if case == "p1_uartlite_stat_ctrl_swapped":
        return {"detected": bool(_dis(rows, ("address",), lambda r: "STAT" in _names(r) or "CTRL" in _names(r) or "CONTROL" in _names(r) or "STATUS" in _names(r)))}
    if case == "p2_timer_load_bit":
        return {"detected": bool(_dis(rows, ("bit_range",), lambda r: "LOAD" in _names(r)))}
    if case == "p3_zb_accel_id_reset":
        return {"detected": bool(_dis(rows, ("reset_value",), lambda r: _names(r).split()[0] == "ID"))}
    if case == "p4_zb_accel_version_width":
        return {"detected": bool(_dis(rows, ("bit_range", "width_bits"), lambda r: _names(r).split()[0] == "ID" and "VERSION" in _names(r)))}
    return {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, default=HERE / "runs")
    ap.add_argument("--out", type=Path, default=HERE / "results.json")
    a = ap.parse_args()
    cases = {c["id"]: c for c in json.loads((HERE / "cases.json").read_text())["cases"]}
    out: dict = {"schema": "fda-crossread-results/1", "arms": {}}
    for arm_dir in sorted(p for p in a.runs.iterdir() if p.is_dir()):
        arm: dict = {}
        for cid, c in cases.items():
            recs = [json.loads(p.read_text()) for p in sorted(arm_dir.glob(f"{cid}_r*.json"))]
            if not recs:
                continue
            per = []
            for rec in recs:
                rows = rec["rows"]
                u = rec.get("usage") or {}
                n_facts = len(rows)
                per.append({"run": rec["run"], "status_counts": rec["summary"], "disagree_rows": [f"{r['id']}:{r['subject']}:{r['kind']}" for r in rows if r["status"] == "disagree"],
                            "unverified_disagree": [r["id"] for r in rows if r["status"] == "disagree" and not r["doc"]["quote_ok"]],
                            "facts": n_facts, "quote_ok_share": round(sum(1 for r in rows if r["doc"]["quote_ok"]) / n_facts, 3) if n_facts else None,
                            "repairs": (rec.get("reader") or {}).get("repairs"), "reader_problems": len((rec.get("reader") or {}).get("problems") or []),
                            "targets": targets(cid, rows), "seconds": u.get("seconds"), "input_tokens": u.get("input_tokens"),
                            "cache_creation_input_tokens": u.get("cache_creation_input_tokens"), "cache_read_input_tokens": u.get("cache_read_input_tokens"),
                            "output_tokens": u.get("output_tokens"), "plan_cost_estimate_usd": u.get("plan_cost_estimate_usd"), "failed": rec.get("failed")})
            ok = [x for x in per if not x["failed"]]
            row: dict = {"role": c["role"], "runs": per, "n_runs": len(per), "n_failed": len(per) - len(ok)}
            keys = sorted({k for x in ok for k in x["targets"] if isinstance(x["targets"][k], bool)})
            row["detected_runs"] = {k: sum(1 for x in ok if x["targets"][k]) for k in keys}
            if c["role"] == "correct":
                row["runs_with_a_disagree"] = sum(1 for x in ok if x["disagree_rows"])
                row["disagree_rows_total"] = sum(len(x["disagree_rows"]) for x in ok)
            if cid == "h2_96d2_ten_word":
                row["runs_with_a_mask_disagree"] = sum(1 for x in ok if x["targets"]["mask_rows_disagree"])
                row["runs_with_a_disagree"] = sum(1 for x in ok if x["disagree_rows"])
            med = lambda k: statistics.median([x[k] for x in ok if isinstance(x[k], (int, float))]) if any(isinstance(x[k], (int, float)) for x in ok) else None  # noqa: E731
            row["median"] = {k: med(k) for k in ("seconds", "input_tokens", "cache_creation_input_tokens", "output_tokens", "plan_cost_estimate_usd", "facts", "quote_ok_share")}
            arm[cid] = row
        out["arms"][arm_dir.name] = arm
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print("wrote", a.out)


if __name__ == "__main__":
    main()
