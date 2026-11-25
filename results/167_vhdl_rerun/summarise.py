"""Table of the brief 167 runs from records/<tag>/ (role_usage.jsonl, summary.json, score.txt). Prints markdown."""
import json, pathlib, re
R = pathlib.Path(__file__).parent / "records"
print("| run | arm | task | stop | stage-2 rtl visits >=2: repair / fresh | hidden bench |")
print("|---|---|---|---|---|---|")
for d in sorted(R.iterdir()):
    tag = d.name
    arm, task = tag.split("_")[2], {"G": "t1_gray_stepper", "F": "t1_sync_fifo_regs"}[tag.split("_")[1]]
    rows = [json.loads(l) for l in (d / "role_usage.jsonl").read_text().splitlines()]
    rt = [r for r in rows if r["role"] == "rtl" and r["stage"] == "rtl-design-creation" and r["visit"] >= 2]
    rep = sum(1 for r in rt if r["repair"]); fresh = len(rt) - rep
    s = d / "summary.json"
    stop = json.loads(s.read_text()).get("stop") if s.exists() else "cut at the 90 min wall cap (no summary.json)"
    sc = (d / "score.txt").read_text().strip().splitlines()[-1] if (d / "score.txt").exists() else "no RTL (not scored)"
    print(f"| {tag} | {arm} | {task} | {stop} | {rep} / {fresh} | {sc} |")
