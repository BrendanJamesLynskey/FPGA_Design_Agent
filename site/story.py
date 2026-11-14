"""Data for site/src/story.html (brief 76): how the agent was built, evaluated and improved.

    site/story/story.yaml        the authored story: timeline, experiment cards, method, findings, lessons
    site/story/merged_prs.json   a dated snapshot of the repository's merged pull requests (number, merge date, title)
    site/data/story.json         what the page reads (written by site/export.py)

Nothing measured is typed by hand. A number in the prose is a {name} placeholder (or {name|abs}, {name|plus}) whose value
is read from a committed file by one of site/expertise.py's expressions (see `expertise.EXPR`); the prose itself may hold
only names (models, tasks, rule ids, Vivado 2026.1). Plots are drawn from values, never from typed numbers. Every PR and
every linked path must exist. The page's number check sees the resolved values, never the story's own text.
"""
from __future__ import annotations

import glob
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

import expertise

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DIR = HERE / "story"

#: names that contain digits but are not measurements
PROSE_OK = re.compile(
    r"\bVivado 2026\.1\b|\bclaude-(?:sonnet|haiku|opus)-5-5\b|\bgpt-6-luna\b|\bglm-5\.3-flash\b|\bdeepseek-v4\.1-flash-1017\b|"
    r"\bqwen3(?:\.6)?(?:-35b-a3b|-coder-30b-a3b-instruct)?\b|\bbge-small-en-v1\.5\b|\b[ct]\d+_\w+|\bd\d+_\w+|\beval-[12]\b|"
    r"\b[HA][0-9]\b|\bG[1-5]\b|\bV[0-3]\b|\bFDA-CON-\d\b|\bUG949\b|\bpass@1\b|\bxc7a100t(?:csg324-1)?\b|\bNexys A7\b|\bAXI4-Lite\b|"
    r"\bT[12]\b|\bM(?:9|11)\b|\bLED0\b|\bc\d+\b|\bstages? \d\b|\b(?:one|two|three|four|five|six|seven)\b|\bKR260\b|\bXPM\b|\bF2\b|\bCDC\b|\b0 to 1\b", re.I)
NUM = re.compile(r"-?\d+(?:[.,]\d+)*")
VERDICTS = {"win": "Win", "mixed": "Mixed", "null": "Null", "negative": "Negative", "inconclusive": "Inconclusive",
            "stopped": "Stopped, no score"}
CAUSES = ["Spec and clarification", "Architecture", "RTL", "Verification", "Constraints and closure", "Tools",
          "Knowledge bank", "Prompts and context", "Cost or budget", "Harness or instrument"]


class ContractError(ValueError):
    pass


def _fill(where: str, text, vals: dict) -> str:
    text = str(text)
    bad = NUM.findall(PROSE_OK.sub(" ", re.sub(r"\{[\w|]+\}", " ", text)))
    bad = [b for b in bad if any(c.isdigit() for c in b)]
    if bad:
        raise ContractError(f"{where}: typed number(s) {bad}; use a {{name}} placeholder with a value expression")

    def one(m):
        k, _, flt = m.group(1).partition("|")
        if k not in vals:
            raise ContractError(f"{where}: no value named {k}")
        v = vals[k]
        if flt == "abs":
            v = abs(v)
        elif flt == "plus":
            v = f"+{expertise.fmt(v)}" if v > 0 else v
        elif flt:
            raise ContractError(f"{where}: unknown filter {flt}")
        return expertise.fmt(v) if not isinstance(v, str) else v
    out = re.sub(r"\{([\w|]+)\}", one, text)
    if re.search(r"[{}]", out):
        raise ContractError(f"{where}: malformed placeholder in {text!r}")
    return out


def _values(spec: dict) -> dict:
    out = {}
    for k, v in spec.items():
        if not glob.glob(str(ROOT / v["source"])):
            raise ContractError(f"value {k}: no file {v['source']}")
        out[k] = expertise.evaluate(v["expr"], {"source": v["source"]})
    return out


def _arm_values() -> dict:
    """The harness arms' paired changes (agent graph data), generated names h1_tok_est ... h9_wall_hi."""
    spec = {}
    for arm, idx in (("h1", 0), ("h2", 1), ("h9", 8)):
        for m, key in (("tok", "tokens"), ("cost", "cost_usd"), ("wall", "wall_s")):
            for k, f in (("est", "rel_pct"), ("lo", "lo_pct"), ("hi", "hi_pct")):
                spec[f"{arm}_{m}_{k}"] = {"source": "site/data/agent_graph.json", "expr": f"get:harness.arms.{idx}.result.paired.{m_key(key)}.{f}"}
        spec[f"{arm}_pass"] = {"source": "site/data/agent_graph.json", "expr": f"get:harness.arms.{idx}.result.hidden_passes"}
    spec["h_runs"] = {"source": "site/data/agent_graph.json", "expr": "get:harness.arms.0.result.runs"}
    return spec


def m_key(k):
    return k


def prs_snapshot() -> list[dict]:
    return json.loads((DIR / "merged_prs.json").read_text())


def _pr_links(prs, known, where):
    out = []
    for n in prs or []:
        if n not in known:
            raise ContractError(f"{where}: PR #{n} is not in merged_prs.json")
        out.append({"n": n, "title": known[n]})
    return out


def _links(paths, where):
    out = []
    for p in paths or []:
        try:
            out.append(expertise.link(p))
        except AssertionError as e:
            raise ContractError(f"{where}: {e}")
    return out


def _forest(spec: dict, vals: dict, where: str) -> dict:
    rows = []
    for r in spec["rows"]:
        rows.append({"label": r["label"], "est": vals[r["est"]], "lo": vals[r["lo"]], "hi": vals[r["hi"]], "group": r.get("group", "")})
    return {"title": spec["title"], "unit": spec["unit"], "rows": rows, "note": _fill(where, spec.get("note", ""), vals)}


def _runs_plot(spec: dict) -> dict:
    doc = json.loads((ROOT / spec["source"]).read_text())
    f, _, v = spec["where"].partition("=")
    rows = sorted((r for r in doc[spec["list"]] if str(r[f]) == v), key=lambda r: r["run"])
    fix = {int(k): v for k, v in spec["fix_after"].items()}
    return {"title": spec["title"], "rows": [{"run": r["run"], "got": r["tests_passed"], "of": r["tests_total"], "outcome": r["outcome"],
                                              "fix_pr": fix.get(r["run"], [None, ""])[0], "fix": fix.get(r["run"], [None, ""])[1]} for r in rows]}


def build() -> dict:
    y = yaml.safe_load((DIR / "story.yaml").read_text())
    prs = prs_snapshot()
    known = {p["number"]: p["title"] for p in prs}
    by_day = sorted(Counter(p["date"] for p in prs).items())
    spec = dict(y["values"])
    spec.update(_arm_values())
    vals = _values(spec)
    vals["merged_n"] = len(prs)
    d0, d1 = date.fromisoformat(by_day[0][0]), date.fromisoformat(by_day[-1][0])
    vals["span_days"] = (d1 - d0).days + 1
    F = lambda w, t: _fill(w, t, vals)

    timeline = []
    for t in y["timeline"]:
        w = f"timeline {t['id']}"
        timeline.append({"id": t["id"], "date": t["date"], "title": t["title"], "changed": F(w, t["changed"]), "why": F(w, t["why"]),
                         "showed": F(w, t["showed"]), "prs": _pr_links(t.get("prs"), known, w), "links": _links(t.get("links"), w),
                         "experiment": t.get("experiment", "")})
    exps = []
    for e in y["experiments"]:
        w = f"experiment {e['id']}"
        if e["verdict"] not in VERDICTS:
            raise ContractError(f"{w}: verdict {e['verdict']}")
        exps.append({"id": e["id"], "verdict": e["verdict"], "title": e["title"], "date": e["date"],
                     **{k: F(w + " " + k, e[k]) for k in ("question", "setup", "result", "interval", "decision", "lesson")},
                     "detail": [F(w + " detail", x) for x in e.get("detail", [])],
                     "prs": _pr_links(e.get("prs"), known, w), "links": _links(e.get("links"), w),
                     "plot": e.get("plot", ""), "order": e.get("order", 0)})
    ids = [e["id"] for e in exps]
    assert len(ids) == len(set(ids)), "duplicate experiment ids"
    plots = {k: _forest(v, vals, "plot " + k) for k, v in y["plots"].items()}
    plots["c14_runs"] = _runs_plot(y["runs_plot"])
    findings = []
    for f in y["findings"]:
        w = f"finding PR {f['pr']}"
        if f["cause"] not in CAUSES:
            raise ContractError(f"{w}: cause {f['cause']}")
        if f["pr"] not in known:
            raise ContractError(f"{w}: not in merged_prs.json")
        dt = next(p["date"] for p in prs if p["number"] == f["pr"])
        findings.append({"pr": f["pr"], "date": dt, "cause": f["cause"], "finding": F(w, f["finding"]), "fix": F(w, f["fix"]),
                         "kind": f.get("kind", "")})
    findings.sort(key=lambda f: (f["date"], f["pr"]))
    cause_n = {c: sum(1 for f in findings if f["cause"] == c) for c in CAUSES}
    vals["findings_n"] = len(findings)
    vals["causes_n"] = sum(1 for c in cause_n.values() if c)
    verdict_n = Counter(e["verdict"] for e in exps)
    vals["exp_n"] = len(exps)
    for k in VERDICTS:
        vals[f"v_{k}"] = verdict_n.get(k, 0)
    method = [{"title": m["title"], "text": F("method " + m["title"], m["text"])} for m in y["method"]]
    lessons = [{"claim": F("lesson", l["claim"]), "evidence": F("lesson", l["evidence"]), "links": _links(l.get("links"), "lesson")} for l in y["lessons"]]
    texts = {k: F("text " + k, v) for k, v in y["text"].items()}
    dates = sorted({t["date"] for t in timeline} | {e["date"] for e in exps} | {f["date"] for f in findings} | {d for d, _ in by_day})
    return {"content": {"text": texts, "timeline": timeline, "experiments": exps, "method": method, "lessons": lessons,
                        "findings": findings, "causes": CAUSES, "cause_n": cause_n, "verdicts": VERDICTS, "plots": plots,
                        "by_day": by_day, "values": vals},
            "check": {"values": vals, "plots": plots, "dates": dates, "by_day": by_day, "prs": sorted(known), "cause_n": cause_n}}
