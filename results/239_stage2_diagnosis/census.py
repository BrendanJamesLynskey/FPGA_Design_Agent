"""Brief 239 step 1: the failing-gate census, from records only (no new runs).

Reads the LangGraph checkpoints of every run folder (213 A/B runs, 227 arm A and C runs), takes each distinct failing
gate event (stage, visit number, failure list), and splits it into findings with an id, file:line and first error line.

    python results/239_stage2_diagnosis/census.py --out results/239_stage2_diagnosis

Inputs are read-only: the 213 run folders (``runs/`` of the 213 worktree) and the 227 run folders; the records
``summary.json`` under ``results/`` name each run id. Needs the project venv (langgraph).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

SANDBOX = Path.home() / "Claude_sandbox" / "_worktrees"
R213 = SANDBOX / "213-repair-feedback"
R227 = SANDBOX / "227-requirements-readiness"
SER = JsonPlusSerializer()

_VER = re.compile(r"%(Warning|Error)(?:-([A-Z0-9_]+))?: ([^\n]*)")
_FDA = re.compile(r"^\s*((?:FDA|HDL|STD)-[A-Z]+-\d+)\b(.*)$", re.M)


def runs_213() -> list[tuple[str, str, Path]]:
    out = []
    for d in sorted((R213 / "results/213_repair_feedback/runs").iterdir()):
        s = json.loads((d / "summary.json").read_text())
        out.append((f"213/{d.name}", d.name, R213 / "runs" / s["run_id"]))
    return out


def runs_227() -> list[tuple[str, str, Path]]:
    out = []
    for arm in "AC":
        for p in sorted((R227 / f"results/227_requirements_readiness/arms/{arm}").glob("*/run*")):
            s = json.loads((p / "summary.json").read_text())
            out.append((f"227/{arm}/{p.parent.name}/{p.name}", f"{arm}_{p.parent.name}_{p.name}", R227 / "runs" / s["run_id"]))
    return out


def events(run_dir: Path):
    c = sqlite3.connect(run_dir / "checkpoints.sqlite")
    seen = set()
    prev = None
    for cid, t, b in c.execute("select checkpoint_id,type,checkpoint from checkpoints order by checkpoint_id"):
        cv = SER.loads_typed((t, b)).get("channel_values", {})
        f = cv.get("fails")
        if not f:
            continue
        stage = cv.get("stage")
        visits = cv.get("visits") or {}
        key = (stage, visits.get(str(stage)), json.dumps(f))
        if key in seen:
            continue
        seen.add(key)
        carried = prev is not None and prev[1] == f and prev[0] != stage      # the routing step moved the stage, the failure text is the old one
        prev = (stage, f)
        if carried:
            continue
        yield {"stage": stage, "visit": visits.get(str(stage)), "fails": list(f), "detail": str(cv.get("detail") or "")}


def first_line(text: str) -> str:
    for ln in text.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith(("- V e r", "- Verilator:", "...")):
            return ln[:200]
    return ""


def lint_findings(detail: str) -> list[dict]:
    sec = detail.split("[verif_gates]")[0]
    out = []
    for m in _VER.finditer(sec):
        kind, rule, msg = m.groups()
        if msg.startswith("Exiting due to"):
            continue
        out.append({"id": f"verilator:{rule or 'ERROR'}", "where": re.sub(r".*/(?=[^/]+:\d+:\d+)", "", msg.split(": ")[0]) if ":" in msg else "", "text": msg[:160]})
    for m in _FDA.finditer(sec):
        out.append({"id": m.group(1), "where": "", "text": m.group(2).strip()[:160]})
    if "[icarus elaboration" in sec:
        out.append({"id": "icarus-elaboration", "where": "", "text": sec.split("[icarus elaboration")[1][:160]})
    return out


def findings(ev: dict) -> list[dict]:
    out = []
    detail = ev["detail"]
    for f in ev["fails"]:
        if f == "rtl: did not run (no gates record)" or f == "rtl: did not run":
            out.append({"gate": "stage_rtl", "id": "noise:rtl-did-not-run", "where": "", "text": f})
        elif f == "lint not passing":
            fs = lint_findings(detail) or [{"id": "lint:unparsed", "where": "", "text": first_line(detail)}]
            out += [{"gate": "lint", **x} for x in fs]
        elif f.startswith("standards STD-"):
            m = re.match(r"standards (STD-[A-Z]+-\d+): (?:([^:]+):(\d+): )?(.*)", f)
            if m:
                out.append({"gate": "standards", "id": m.group(1), "where": f"{m.group(2)}:{m.group(3)}" if m.group(2) else "", "text": m.group(4)[:160]})
            else:
                out.append({"gate": "standards", "id": "standards:other", "where": "", "text": f[:160]})
        elif f.startswith("standards STD-") or f.startswith("standards "):
            out.append({"gate": "standards", "id": "standards:other", "where": "", "text": f[:160]})
        elif f == "simulate not passing":
            sec = detail.split("[simulate]", 1)[1].split("\n[", 1)[0] if "[simulate]" in detail else ""
            m = re.search(r"first failing test ([^:]+): (.*)", sec, re.S)
            errs = re.findall(r"(?:AssertionError|\w+Error)[^|]{0,140}", m.group(2)) if m else []
            out.append({"gate": "simulate", "id": "simulate", "where": m.group(1) if m else "", "text": (errs[-1] if errs else first_line(sec)).replace("\n", " ")[:160]})
        elif f.startswith("model contract"):
            out.append({"gate": "model_contract", "id": "model-contract", "where": "", "text": f[:160]})
        elif f == "check_constraints failed":
            out.append({"gate": "inventory", "id": "check_constraints", "where": "", "text": first_line(detail.replace("[check_constraints]", ""))})
        elif f.startswith("V2") or f.startswith("V1") or f.startswith("V3") or f.startswith("V0"):
            out.append({"gate": "verif", "id": f.split()[0] + " " + f.split()[1].rstrip(":"), "where": "", "text": f[:160]})
        elif f.startswith("constants "):
            out.append({"gate": "constants", "id": f.split()[1], "where": "", "text": f[:160]})
        elif f.startswith("architecture not approved"):
            out.append({"gate": "arch_approved", "id": "arch-not-approved", "where": "", "text": f[:160]})
        elif "is compound (" in f:
            out.append({"gate": "spec_signed", "id": "spec:compound-requirement", "where": re.search(r"requirement (REQ-\d+)", f).group(1) if re.search(r"requirement (REQ-\d+)", f) else "", "text": f[:160]})
        elif ev["stage"] == 0:
            out.append({"gate": "spec_signed", "id": "spec:other", "where": "", "text": f[:160]})
        else:
            out.append({"gate": "other", "id": "other:" + f[:40], "where": "", "text": f[:160]})
    return out


#: category of each finding id: a real design error, b a rule the Designer is told of too late or never, c a rule that fires on correct
#: work, d a tool or harness fault, e a constraint the agent cannot know at stage 2 (hand-assigned from the records read for this census)
CATEGORY = {
    ("spec_signed", "spec:compound-requirement"): ("a", "stage 0, not stage 2: the Clarifier writes a requirement joining two statements; the clarify gate sends it back (auto, no cost to later stages)"),
    ("stage_rtl", "noise:rtl-did-not-run"): ("d", "added to every failing stage-2 visit because the flow gates record does not exist yet; alone it is a refused Vivado build (FDA_VIVADO_MAX, another job running)"),
    ("inventory", "check_constraints"): ("c", "'no design.xdc yet' on the first visits is the stage doing its work (expected); on a bounce from stage 2 it repeats the FDA-CON-8 text of the lint gate"),
    ("standards", "STD-CDC-01"): ("c", "architecture.yaml names the supplied data/jtag_bus.sv as inline_in; the checker knew only rtl/ and shell/ modules; routed to stage 1, where the Designer cannot make a data/ file a module"),
    ("lint", "FDA-CON-8"): ("c", "spec.yaml lists the internal register bus (direction: internal) as ports; the rule asked the top to have them"),
    ("lint", "verilator:UNUSEDSIGNAL"): ("c", "tdo and cmd_s[45] inside the supplied, read-only data/jtag_bus.sv; no Designer edit can clear them, and the waiver file was never mentioned to it"),
    ("simulate", "simulate"): ("a", "the agent's own bench against its own model: register read mismatches, early DONE, a measurement off by one, bench timeouts"),
    ("verif", "V2 failing_tests"): ("a", "the same failing tests, as the V2 gate reports them"),
    ("verif", "V2 assertions_bound_zero_failures"): ("a", "consequence of a failing test"),
    ("verif", "V2 constrained_random_test_ran"): ("a", "consequence of a failing test: no passing test with 'random' in its name"),
    ("verif", "V2 seeds_run"): ("d", "no seeded results were written (the run stopped earlier)"),
    ("model_contract", "model-contract"): ("a", "the Modeller's model.py raised on import or call"),
}


def summarise(rows: list[dict], out: Path) -> None:
    ev: dict = {}
    for r in rows:
        k = (r["gate"], r["id"])
        e = ev.setdefault(k, {"events": set(), "runs": set(), "r213": set(), "r227": set(), "repeat": 0, "first": r["first_line"], "stage2_events": set()})
        e["events"].add((r["run"], r["stage"], r["visit"]))
        e["runs"].add(r["run"])
        (e["r213"] if r["series"] == "213" else e["r227"]).add(r["run"])
        e["repeat"] += int(r["same_finding_as_previous_visit"])
        if str(r["stage"]) == "2":
            e["stage2_events"].add((r["run"], r["visit"]))
    lines = ["| gate | finding | cat | events | runs (213 / 227) | repeated next visit | stage-2 events | first line | what it is |", "|---|---|---|---|---|---|---|---|---|"]
    for k, e in sorted(ev.items(), key=lambda kv: (-len(kv[1]["runs"]), -len(kv[1]["events"]))):
        cat, note = CATEGORY.get(k, ("?", ""))
        fl = e["first"].replace("|", "/").replace("\n", " ")[:90]
        lines.append(f"| {k[0]} | {k[1]} | {cat} | {len(e['events'])} | {len(e['runs'])} ({len(e['r213'])} / {len(e['r227'])}) | {e['repeat']} | {len(e['stage2_events'])} | {fl} | {note} |")
    (out / "census_table.md").write_text("\n".join(lines) + "\n")


FIXED = {"FDA-CON-8", "STD-CDC-01", "verilator:UNUSEDSIGNAL"}      # the three rules that fired on correct work (brief 239 fixes 1 to 3)


def last_blocker(rows: list[dict], out: Path) -> None:
    """Per run: the baseline class (``baseline_runs.csv``) and, for a failing run, whether the findings of its last stage-1 or stage-2
    failing event were only the three rules fixed by this brief ('only-fixed'), included one ('partly') or none ('other')."""
    import csv as _csv
    order: dict[str, list[tuple]] = {}
    for r in rows:
        if str(r["stage"]) in ("1", "2") and r["id"] not in ("noise:rtl-did-not-run", "check_constraints"):
            k = (str(r["stage"]), str(r["visit"]))
            order.setdefault(r["run"], [])
            if k not in order[r["run"]]:
                order[r["run"]].append(k)
    base = {r["run"]: r for r in _csv.DictReader((out / "baseline_runs.csv").open())}
    res = []
    for run, b in base.items():
        if b["class"] != "fail":
            continue
        ids = set()
        if order.get(run):
            lk = order[run][-1]
            ids = {r["id"] for r in rows if r["run"] == run and (str(r["stage"]), str(r["visit"])) == lk and r["id"] not in ("noise:rtl-did-not-run", "check_constraints")}
        tag = "only-fixed" if ids and ids <= FIXED else ("partly" if ids & FIXED else "other")
        ever = {r["id"] for r in rows if r["run"] == run and str(r["stage"]) in ("1", "2")} & FIXED
        res.append({"run": run, "last_event_findings": "|".join(sorted(ids)), "last_event_vs_fixed_rules": tag, "fixed_rule_seen_in_run": int(bool(ever))})
    with (out / "last_blocker.csv").open("w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=list(res[0]))
        w.writeheader()
        w.writerows(res)


def baseline_table(out: Path) -> None:
    """``baseline_runs.csv``: per run the class (pass = stop done; own-pass = every stage-2 gate passed and only the independent bench is
    unresolved; fail), stage-2 and stage-1 entries, repeated stage-2 lint findings, plan-cost estimate and the stop reason."""
    import csv as _csv
    lint_rep: dict[str, int] = {}
    for r in _csv.DictReader((out / "census_events.csv").open()):
        if r["gate"] == "lint" and str(r["stage"]) == "2" and r["same_finding_as_previous_visit"] == "1":
            lint_rep[r["run"]] = lint_rep.get(r["run"], 0) + 1
    rows = []
    for label, short, rd in runs_213() + runs_227():
        base = R213 / "results/213_repair_feedback/runs" / short if label.startswith("213") else R227 / "results/227_requirements_readiness/arms" / label.split("/", 1)[1]
        s = json.loads((base / "summary.json").read_text())
        stop = s.get("stop") or ""
        v = s.get("stages_visited") or []
        cls = "pass" if stop == "done" else ("own-pass, bench unresolved" if stop.startswith("unresolved") else "fail")
        rows.append([label, cls, v.count(2), v.count(1), lint_rep.get(label, 0), round(s.get("plan_cost_estimate_usd") or 0, 2), stop[:80]])
    with (out / "baseline_runs.csv").open("w", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(["run", "class", "stage2_visits", "stage1_visits", "lint_repeats_stage2", "plan_cost_usd", "stop"])
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/239_stage2_diagnosis")
    a = ap.parse_args()
    out = Path(a.out)
    rows = []
    for label, short, rd in runs_213() + runs_227():
        last: dict = {}                      # stage -> {(id, where, text)} of that stage's previous failing event
        for ev in events(rd):
            fs = findings(ev)
            sig = tuple(sorted({(x["id"], x["where"]) for x in fs}))
            before = last.get(ev["stage"], set())
            for x in fs:
                same = (x["id"], x["where"], x["text"]) in before
                rows.append({"run": label, "series": label.split("/")[0], "stage": ev["stage"], "visit": ev["visit"], "gate": x["gate"], "id": x["id"], "where": x["where"],
                             "first_line": x["text"], "same_finding_as_previous_visit": int(same),
                             "event_sig": "|".join(f"{i}@{w}" for i, w in sig)[:300]})
            last[ev["stage"]] = {(x["id"], x["where"], x["text"]) for x in fs}
    out.mkdir(parents=True, exist_ok=True)
    with (out / "census_events.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    summarise(rows, out)
    baseline_table(out)
    last_blocker(rows, out)
    print(len(rows), "finding rows ->", out / "census_events.csv")


if __name__ == "__main__":
    main()
