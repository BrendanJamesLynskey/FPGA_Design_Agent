"""Brief 210: collect the compact record of the live runs from their run directories (runs/<id>/, which are not committed).

    python3 results/210_requirements/collect_live.py <exit-log-dir> <run name>=<exit log name> ...

For each named run: the interview questions with their class and how each was settled, the level and where it came from, the stop text, the
exit status (from the log's last line), tokens, wall time and the model, and REQUIREMENTS_NEEDED.md when the run wrote one."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "live_runs"


def main(logdir: Path, pairs: list[str]) -> None:
    OUT.mkdir(exist_ok=True)
    runs = {}
    for p in pairs:
        name, log = p.split("=")
        sums = [json.loads(f.read_text()) | {"_dir": f.parent} for f in (ROOT / "runs").glob("*/summary.json")]
        s = [x for x in sorted(sums, key=lambda x: x["run_id"]) if x.get("design") == name][-1]      # the latest run of that name
        q = s["questions"]
        code = int(re.findall(r"exit (\d+)", (logdir / log).read_text())[-1])
        d = s["_dir"] / name
        if (d / "REQUIREMENTS_NEEDED.md").is_file():
            (OUT / f"{name}_REQUIREMENTS_NEEDED.md").write_text((d / "REQUIREMENTS_NEEDED.md").read_text())
        runs[name] = {"run_id": s["run_id"], "exit_status": code, "level": q.get("level"), "level_source": q.get("level_source"),
                      "stop": s.get("stop"), "asked": q["asked"], "answered": q["answered"], "defaulted": q["defaulted"],
                      "waived": q.get("waived", 0), "unresolved": q.get("unresolved", 0), "model": s.get("model"), "harness": s.get("harness"),
                      "oracle_model": s.get("oracle_model"), "tokens": s.get("tokens"), "wall_s": s.get("wall_s"), "cost_usd": s.get("cost_usd"),
                      "questions": [{k: x.get(k) for k in ("id", "text", "risk", "risk_rule", "status", "by", "answer")} | {"waiver": x.get("waiver")}
                                    for x in q["questions"]]}
    (OUT / "live_runs.json").write_text(json.dumps(runs, indent=1) + "\n")
    print({k: (v["level"], v["exit_status"], v["unresolved"]) for k, v in runs.items()})


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2:])
