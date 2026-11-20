"""Brief 114: run the pre-registered evaluation (run from the repository root).

    python3 results/114_doc_crossread/run_eval.py --arm A --priv-dir ../FPGA_Design_Agent_Knowledge/results_private/b114_doc_crossread [--only CASE] [--workers 3]

For every case x repeat of the arm: load the document excerpt, call the blind reader (purpose doc_crossread, the arm's model), compare with the case's code
files, and write the public record to runs/<arm>/<case>_r<k>.json. The public record keeps a quotation only for a `disagree` row (a short quotation, as the
brief allows); everything else of the reader's output (all facts, all quotations, the raw replies) goes to the private directory. A run that raised is
recorded as failed and re-run once; both attempts are kept. Nothing here scores: score.py does, by the pre-registered rules.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from flow import doc_crossread as D  # noqa: E402

HERE = Path(__file__).resolve().parent
SPEC = json.loads((HERE / "cases.json").read_text())
RUNS = HERE / "runs"


def public_record(rec: dict) -> dict:
    out = json.loads(json.dumps(rec, default=str))
    for r in out["rows"]:
        d = r["doc"]
        d["quote_sha256"] = hashlib.sha256((d.get("quote") or "").encode()).hexdigest()[:16]
        if r["status"] != "disagree":
            d.pop("quote", None)
            d.pop("statement", None)
    return out


def run_one(arm: str, case: dict, k: int, a: argparse.Namespace) -> dict:
    spec = SPEC["documents"][case["doc"]]
    path = Path(spec["path"]) if Path(spec["path"]).is_absolute() else ROOT / spec["path"]
    document = D.load_document(pdf=path, pages=case["pages"]) if spec["kind"] == "pdf" else D.load_document(doc=path)
    code_case = case.get("code_case", case["id"])
    code = [HERE / "cases" / code_case / "code" / n for n in case["code"]]
    arm_spec = SPEC["arms"][arm]
    attempts = []
    for attempt in (1, 2):
        meter = None
        try:
            res = D.make_resolver(model_config=json.dumps({"purposes": {D.PURPOSE: {"model": arm_spec["model"], "options": {"effort": arm_spec["effort"]}}}}))
            meter = D.UsageMeter(res)
            rec, read = D.crossread(document, code, case["topic"], case["target"], llm=meter, model_info=meter.model_info())
            rec["usage"] = meter.totals()
            rec["run"] = f"{arm}/{case['id']}_r{k}"
            rec["document"]["version"] = spec["version"]
            rec["document"]["file_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            rec["attempt"] = attempt
            if attempts:
                rec["earlier_attempts"] = attempts
            priv = a.priv_dir / arm
            priv.mkdir(parents=True, exist_ok=True)
            (priv / f"{case['id']}_r{k}_raw.json").write_text(json.dumps({"run": rec["run"], "raw_replies": read["raw_replies"], "reader_facts": read["facts"], "reader_problems": read["problems"],
                                                                         "usage_calls": meter.calls}, indent=1, default=str))
            pub = RUNS / arm
            pub.mkdir(parents=True, exist_ok=True)
            (pub / f"{case['id']}_r{k}.json").write_text(json.dumps(public_record(rec), indent=1) + "\n")
            return {"run": rec["run"], "ok": True, "summary": rec["summary"], "usage": rec["usage"]}
        except Exception as e:                      # an infrastructure error: keep it, try once more
            attempts.append({"attempt": attempt, "error": f"{type(e).__name__}: {str(e)[:160]}", "usage": meter.totals() if meter else None})
    pub = RUNS / arm
    pub.mkdir(parents=True, exist_ok=True)
    (pub / f"{case['id']}_r{k}.json").write_text(json.dumps({"run": f"{arm}/{case['id']}_r{k}", "failed": attempts[-1]["error"], "earlier_attempts": attempts, "rows": [], "summary": {},
                                                             "reader": {}, "usage": None}, indent=1) + "\n")
    return {"run": f"{arm}/{case['id']}_r{k}", "ok": False, "error": attempts[-1]["error"]}


def main() -> None:
    global SPEC, RUNS
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=list(SPEC["arms"]))
    ap.add_argument("--priv-dir", type=Path, required=True)
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--repeats", type=int, default=SPEC["repeats"])
    ap.add_argument("--only-repeat", type=int, help="run only this repeat number (a re-run after a code fix is recorded as such in PREREGISTRATION.md)")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--spec", type=Path, help="a cases file other than cases.json (plumbing smoke tests only)")
    ap.add_argument("--runs-dir", type=Path, help="write the public records here instead of runs/ (smoke tests only)")
    a = ap.parse_args()
    if a.spec:
        SPEC = json.loads(a.spec.read_text())
    if a.runs_dir:
        RUNS = a.runs_dir
    from agent.access import require_or_exit
    require_or_exit("results/114_doc_crossread/run_eval.py")
    jobs = [(c, k) for c in SPEC["cases"] if not a.only or c["id"] in a.only for k in (range(1, a.repeats + 1) if not a.only_repeat else [a.only_repeat])]
    t0 = time.time()
    meta = {"arm": a.arm, "arm_spec": SPEC["arms"][a.arm], "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "jobs": len(jobs),
            "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
            "claude_cli": subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip()}
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        results = list(ex.map(lambda j: run_one(a.arm, j[0], j[1], a), jobs))
    meta.update({"seconds": round(time.time() - t0), "failed": [r["run"] for r in results if not r["ok"]]})
    d = RUNS / a.arm
    d.mkdir(parents=True, exist_ok=True)
    (d / ("_meta.json" if not a.only_repeat else f"_meta_rerun_{a.only_repeat}_{'_'.join(a.only) or 'all'}.json")).write_text(json.dumps(meta, indent=1) + "\n")
    for r in results:
        print(r["run"], "ok" if r["ok"] else "FAILED " + r["error"], r.get("summary", ""))


if __name__ == "__main__":
    main()
