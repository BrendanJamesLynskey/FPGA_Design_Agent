#!/usr/bin/env python3
"""Summarise the stage-1 trial from agent run directories: for each run (name t150_<spec>_<arm>) the ip_lookup calls, the library
entries the design took, and whether the primary entry was reused. Copies the small records into stage1_trial/records/<name>/.

    python3 results/150_ip_lookup/stage1_trial/summarise.py runs/ > results/150_ip_lookup/stage1_trial/summary.json
"""
import json, re, shutil, sys
from pathlib import Path

#: files not copied: the model echoed private prompt text into them (agent/tests/test_99_prompts.py refuses it in tracked files)
NOT_COPIED = {("t150_ping_withfix", "trace.jsonl"), ("t150_ping_withfix", "spec.yaml"), ("t150_ping_withfix", "summary.json")}
PRIMARY = {"ping": ["icmp_echo"], "crc": ["crc32_step"], "fir": ["fir"], "uart": []}
SECONDARY = {"ping": ["eth_mac_rmii"]}
HERE = Path(__file__).resolve().parent
LIB = sorted(p.parent.name for p in (HERE.parents[2] / "ip_lib").glob("*/ip.yaml"))


def one(run: Path) -> dict | None:
    if not (run / "trace.jsonl").is_file():
        return None                                   # a run that stopped before it started (a prompt-pin error)
    cfg = json.loads((run / "config.json").read_text())
    name = cfg.get("name") or ""
    m = re.fullmatch(r"t150_(\w+?)_(with|without|withfix)", name)
    if not m:
        return None
    spec, arm = m.groups()
    d = run / name
    arch = (d / "ARCHITECTURE.md").read_text() if (d / "ARCHITECTURE.md").is_file() else ""
    yml = (d / "architecture.yaml").read_text() if (d / "architecture.yaml").is_file() else ""
    sec = re.search(r"## Library entries considered\n(.*?)(?:\n## |\Z)", arch, re.S)
    sec_text = sec.group(1) if sec else ""
    taken_sec = {e for e in LIB for line in sec_text.splitlines() if e in line and re.search(r"\btaken\b|\bused\b|\breuse", line, re.I)
                 and not re.search(r"not taken|not used|rejected|not reused", line, re.I)}
    named_yaml = {e for e in LIB if re.search(rf"\b{e}\b", yml)}
    calls = [json.loads(l) for l in (run / "trace.jsonl").read_text().splitlines() if '"ip_lookup"' in l]
    calls = [c for c in calls if c.get("kind") == "tool" and c.get("tool") == "ip_lookup"]
    ok = [c for c in calls if (c.get("result") or {}).get("ok")]
    used = taken_sec | named_yaml
    summ = json.loads((run / "summary.json").read_text()) if (run / "summary.json").is_file() else {}
    rec = HERE / "records" / name
    rec.mkdir(parents=True, exist_ok=True)
    for f in ("trace.jsonl", "role_usage.jsonl", "summary.json", "config.json"):
        if (run / f).is_file() and (name, f) not in NOT_COPIED:
            shutil.copy2(run / f, rec / f)
    for f in ("ARCHITECTURE.md", "architecture.yaml", "build/ip_lookup.jsonl", "spec.yaml"):
        if (d / f).is_file() and (name, Path(f).name) not in NOT_COPIED:
            shutil.copy2(d / f, rec / Path(f).name)
    return {"run": run.name, "spec": spec, "arm": arm, "ip_lookup_calls": len(calls), "ip_lookup_ok": len(ok),
            "queries": [c["arguments"].get("query") for c in ok if c["arguments"].get("action") == "search"],
            "entries_taken_in_section": sorted(taken_sec), "entries_named_in_architecture_yaml": sorted(named_yaml),
            "primary_expected": PRIMARY[spec], "primary_reused": sorted(set(PRIMARY[spec]) & used),
            "secondary_reused": sorted(set(SECONDARY.get(spec, [])) & used),
            "false_reuse": sorted(used) if not PRIMARY[spec] and not SECONDARY.get(spec) else [],
            "has_considered_section": bool(sec), "plan_cost_estimate_usd": summ.get("plan_cost_estimate_usd"),
            "stopped": summ.get("stop") or summ.get("stopped")}


if __name__ == "__main__":
    out = [r for r in (one(p) for p in sorted(Path(sys.argv[1]).glob("*"))) if r]
    print(json.dumps(sorted(out, key=lambda r: (r["spec"], r["arm"])), indent=1))
