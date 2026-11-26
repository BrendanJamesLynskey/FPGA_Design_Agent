"""Brief 215: gather the per-run records of one batch into results/215_public_benchmarks/records/<batch>/<tag>/ and write results.csv.

usage: records.py --batch calibration|sample50 --data cvdp.jsonl --ids ids.txt --prefix cal|s --scores scores.csv [--out DIR]
  ids.txt: problem ids in order; tag = <prefix>_<id minus 'cvdp_copilot_'> (plus the driver's own name when a tag was re-run: use --tags to override)
  scores.csv: id,pass|fail lines from `cvdp_adapter.py score`
Copies: rtl/ (the delivered files), role_usage.jsonl, summary.json, the driver log. The problem text (spec.md) is never copied."""
import argparse, csv, json, shutil, re
from pathlib import Path

W = Path("/home/brendan/Claude_sandbox/_worktrees/215-public-benchmarks")
S = Path("/home/brendan/Claude_sandbox/_scratch_215")
KEEP = ("run_id", "design", "model", "harness", "claude_code_version", "plan_cost_estimate_usd", "harness_arm", "profile", "role_models",
        "model_table_hash", "per_role", "per_stage", "stages_visited", "loops", "tokens", "cost_usd", "unreported_cost_calls", "token_split",
        "budget_scale", "turns", "wall_s", "stop", "stop_detail", "clean_stop", "knowledge_bank")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True); ap.add_argument("--data", required=True); ap.add_argument("--ids", required=True)
    ap.add_argument("--prefix", required=True); ap.add_argument("--scores", required=True)
    ap.add_argument("--scores2", help="second scores.csv (post hoc extension-mapped variant)")
    ap.add_argument("--tags", help="id=tag,... overrides"); ap.add_argument("--out", default=str(W / "results/215_public_benchmarks"))
    a = ap.parse_args()
    cat = {}
    for l in open(a.data):
        r = json.loads(l); cat[r["id"]] = (r["categories"][0], r["categories"][1] if len(r["categories"]) > 1 else "")
    sc = dict(x.split(",") for x in Path(a.scores).read_text().split())
    sc2 = dict(x.split(",") for x in Path(a.scores2).read_text().split()) if a.scores2 else {}
    ov = dict(x.split("=") for x in a.tags.split(",")) if a.tags else {}
    rows = []
    for pid in Path(a.ids).read_text().split():
        tag = ov.get(pid, f"{a.prefix}_{pid[len('cvdp_copilot_'):]}")
        dst = Path(a.out) / "records" / a.batch / tag
        found = sorted(W.glob(f"runs/*/{tag}"))
        log = (S / "logs" / f"{tag}.log")
        row = {"id": pid, "category": cat[pid][0], "difficulty": cat[pid][1], "tag": tag, "result": sc.get(pid, "NOT RUN"), "result_ext_mapped": sc2.get(pid, "")}
        if found:
            d = found[0]; run = d.parent
            dst.mkdir(parents=True, exist_ok=True)
            if (d / "rtl").is_dir():
                shutil.copytree(d / "rtl", dst / "rtl", dirs_exist_ok=True)
            if (run / "role_usage.jsonl").exists():
                shutil.copy(run / "role_usage.jsonl", dst / "role_usage.jsonl")
            if (run / "summary.json").exists():          # a whitelist: the full summary carries the interview's private question text
                full = json.loads((run / "summary.json").read_text())
                (dst / "summary.json").write_text(json.dumps({k: full[k] for k in KEEP if k in full}, indent=1) + "\n")
            ru = [json.loads(x) for x in (run / "role_usage.jsonl").read_text().splitlines()]
            s = json.loads((run / "summary.json").read_text()) if (run / "summary.json").exists() else {}
            row.update(run_id=run.name, stop=(s.get("stop") or "no summary")[:90], wall_s=s.get("wall_s", ""),
                       plan_cost_usd=s.get("plan_cost_estimate_usd", ""), tokens=sum(r.get("tokens") or 0 for r in ru),
                       stage2_visits=len({(r["visit"]) for r in ru if r["stage"] == "rtl-design-creation"}))
        if log.exists():
            txt = log.read_text()
            m = re.search(r"weekly_before=(\d+)%", txt); m2 = re.search(r"weekly_after=(\d+)%", txt); m3 = re.search(r"exit (\d+) wall_s=(\d+)", txt)
            row.update(weekly_before=m.group(1) if m else "", weekly_after=m2.group(1) if m2 else "", driver_wall_s=m3.group(2) if m3 else "")
            dst.mkdir(parents=True, exist_ok=True)
            # the driver log carries the agent's closing JSON and its stdout; keep only its first lines and the exit lines
            lines = txt.splitlines()
            keep = [x for x in lines if re.match(r"^20\d\d-", x)]
            (dst / "driver.log").write_text("\n".join(keep) + "\n")
        rows.append(row)
    cols = ["id", "category", "difficulty", "tag", "result", "result_ext_mapped", "run_id", "stop", "stage2_visits", "wall_s", "driver_wall_s", "plan_cost_usd", "tokens",
            "weekly_before", "weekly_after"]
    out = Path(a.out) / f"results_{a.batch}.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    print(out)


if __name__ == "__main__":
    main()
