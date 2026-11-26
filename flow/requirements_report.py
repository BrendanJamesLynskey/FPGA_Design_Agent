#!/usr/bin/env python3
"""The requirements verification report of a design (brief 210): ``REQUIREMENTS_REPORT.md`` at the design root.

One row per requirement of ``spec.yaml``: its id and text, **where it came from** (a line of the user's request, an answered question,
a default with its risk class, a waiver, or "unrecorded": the request or the Clarifier's reading of it, which spec.yaml does not tell apart), the method(s) that verify it, the evidence as links
(test, formal job, gate or bring-up step) and the result: ``pass``, ``fail`` or ``pending`` (the evidence is not produced yet, for example a
board check before the visit). The headline line counts them: "N of M requirements verified and passed; K pending; F failed".

A requirement that rests on a default the user did not confirm is marked, so a pass is never read as confirming a guess. A requirement
that a gate's fix broke at ``loose`` (``build/requirements/state.json`` ``conflicts``) is marked ``fail`` with the reason.

The matrix underneath is brief 53's (``flow/traceability.py``); this report is its readable form plus the origin and the conflicts.

    python -m flow.requirements_report <design> [--hw <bring-up JSON>] [--json out.json] [--md out.md]

With no flag it rebuilds the matrix from the evidence the design's ``build/`` holds (the same files the agent's trace step reads), so after a
board run, ``python -m flow.requirements_report <design>`` turns the ``pending`` hardware rows into ``pass`` or ``fail`` from the bring-up
JSON (``build/bringup/<design>_bringup.json``, or ``--hw``) with no other edit.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    from flow import traceability as tr
except ImportError:                                  # run as a script: flow/ itself is on sys.path
    import traceability as tr                        # type: ignore[no-redef]

ROOT = tr.ROOT
SCHEMA = "fpga-force/requirements-report/v1"
REPORT = "REQUIREMENTS_REPORT.md"
JSON_REL = ("build", "requirements", "report.json")
STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "is", "are", "be", "it", "its", "for", "with", "at", "by", "as", "that", "this",
        "must", "shall", "should", "never", "no", "not", "one", "each", "every", "any", "when", "then", "than", "from", "into", "over"}
_TOK = re.compile(r"[a-z0-9_]+(?:\.[0-9]+)?")


def _tokens(s: str) -> set[str]:
    """Content words, cut to five letters so that "debounced" and "debounce", or "press" and "presses", meet."""
    return {t if t.isdigit() else t[:5] for t in _TOK.findall(str(s).lower()) if t not in STOP and (len(t) > 2 or t.isdigit())}


def _coverage(req: set[str], other: set[str]) -> float:
    return len(req & other) / len(req) if req else 0.0


# ---- where a requirement came from ---------------------------------------------------------------------------------------------------
def origin_of(req: dict[str, Any], spec: dict[str, Any], request: str) -> dict[str, Any]:
    """``{kind, detail, risk, unconfirmed}``. ``kind`` is spec | answered | default | waiver | unrecorded | agent.

    1. An explicit ``origin`` on the requirement (``{kind, detail}`` or a string) is used as written; ``agent`` and ``default`` count as
       unconfirmed.
    2. A resolved question (spec.yaml ``resolved_questions``) whose question and answer hold at least half of the requirement's words:
       ``answered`` (by a person, the oracle or a package fact), ``default`` (nobody answered; with the question's risk class) or ``waiver``.
    3. A line, or two lines together, of the request (spec.md) that holds at least 40 % of its words: ``spec``, with the line number. The
       match is by words, and the Clarifier rewrites each requirement as one checkable statement, so it is a pointer to the likely line, not proof.
    4. Otherwise ``unrecorded``: the requirement comes from the request or from the Clarifier's reading of it, and spec.yaml does not say which.
       It is not marked unconfirmed: nothing says it is a guess either."""
    given = req.get("origin")
    if isinstance(given, dict) and given.get("kind"):
        return {"kind": str(given["kind"]), "detail": str(given.get("detail", "")), "risk": given.get("risk"),
                "unconfirmed": str(given["kind"]) in ("default", "agent", "waiver")}
    if isinstance(given, str) and given.strip():
        return {"kind": "spec", "detail": given.strip(), "risk": None, "unconfirmed": False}
    want = _tokens(req.get("text", ""))
    from agent.graph import requirements as RQ
    top: tuple[float, dict] = (0.0, {})
    for q in spec.get("resolved_questions") or []:
        if isinstance(q, dict) and q.get("status") != "unresolved":
            c = _coverage(want, _tokens(f"{q.get('question', '')} {q.get('answer', '')}"))
            if c > top[0]:
                top = (c, q)
    if top[0] >= 0.5:
        q = top[1]
        risk = q.get("risk") if q.get("risk") in RQ.RANK else RQ.classify(str(q.get("question", ""))).cls
        what = str(q.get("question", ""))[:90]
        if q.get("status") == "waived":
            w = q.get("waiver") or {}
            return {"kind": "waiver", "detail": f"waived by {w.get('who', '?')} on {w.get('when', '?')}: {what}", "risk": risk, "unconfirmed": True}
        if q.get("status") == "defaulted":
            return {"kind": "default", "detail": f"a default (nobody answered): {what}", "risk": risk, "unconfirmed": True}
        return {"kind": "answered", "detail": f"answered by {q.get('by', '?')}: {what}", "risk": risk, "unconfirmed": False}
    lines = request.splitlines()
    best, at = 0.0, 0
    for pair in (False, True):                                   # a single line first: two lines together win only by holding more of the words
        for i, line in enumerate(lines):
            c = _coverage(want, _tokens(line + " " + lines[i + 1] if pair and i + 1 < len(lines) else line))
            if c > best:
                best, at = c, i + 1
    if best >= 0.4:
        return {"kind": "spec", "detail": f"your request, near line {at}", "risk": None, "unconfirmed": False}
    return {"kind": "unrecorded", "detail": "the request or the Clarifier's reading of it (spec.yaml does not record which)", "risk": None, "unconfirmed": False}


# ---- the evidence as links ------------------------------------------------------------------------------------------------------------
def _link(design: Path, file: str | None, line: int | None = None) -> str:
    """A path as a Markdown-relative target from the design root (the report lives there)."""
    import os
    if not file:
        return ""
    p = Path(file)
    p = p if p.is_absolute() else ROOT / p
    try:
        rel = os.path.relpath(p, design)
    except ValueError:
        rel = str(p)
    return rel + (f"#L{line}" if line else "")


def _evidence(design: Path, t: dict[str, Any], m: dict[str, Any]) -> list[dict[str, str]]:
    arts = {(a["kind"], a["name"]): a for a in t.get("artefacts") or []}
    src = t.get("evidence_sources") or {}
    out = []
    for v in m["verifications"]:
        a = arts.get(("test", v["artefact"])) or arts.get(("formal", v["artefact"]))
        if a:
            tgt = _link(design, a.get("file"), a.get("line") if a["kind"] == "test" else None)
        elif m["method"] == "hardware":
            tgt = _link(design, src.get("hw"))
        elif m["method"] == "analysis":
            tgt = _link(design, src.get("gates"))
        else:
            tgt = ""
        out.append({"name": v["artefact"], "link": tgt, "result": v["result"], "how": v.get("via", ""), "detail": v.get("detail", "")})
    return out


def _result(row: dict[str, Any], conflict: dict[str, Any] | None) -> tuple[str, str]:
    """(result, reason). pass | fail | pending. A requirement whose methods have no verification is ``fail`` (nothing verifies it)."""
    if conflict:
        return "fail", (f"the fix for {conflict.get('code')} ({conflict.get('fix_kind')}) was taken although it conflicts with this requirement"
                        + (f" (waived by {conflict['waiver'].get('who')}: {conflict['waiver'].get('why')})" if conflict.get("waiver") else
                           f" (level {conflict.get('level')}: the run went ahead)"))
    st = row.get("status")
    if st == "pass":
        return "pass", ""
    if st == "pending":
        why = [f"{m['method']} evidence not produced yet" for m in row["methods"] if m["status"] == "pending"]
        return "pending", "; ".join(why)
    if st == "stale":
        return "fail", "the requirement text changed since its evidence was made"
    why = [f"{m['method']}: " + ("nothing cites it" if not m["verifications"] else "a verification failed") for m in row["methods"] if m["status"] in ("fail", "missing")]
    if not row["methods"]:
        why = ["no proof method"]
    return "fail", "; ".join(why)


# ---- the lab (brief 221) --------------------------------------------------------------------------------------------------------------
def lab_rows(design: Path) -> dict[str, dict[str, Any]]:
    """``{requirement id: {...}}`` from ``build/lab/plan.json`` (the method chosen by stage 9) and ``build/lab/results.json`` (a run of the instrument
    steps). ``status`` is ``none`` (on-chip only), ``pending`` (an instrument check is planned and has not run), ``pass``, ``fail``, or ``dry_run`` (the
    agent's own run against mock instruments: it shows the plumbing works and is never evidence). Empty when the design has no lab plan."""
    pj, rj = Path(design).joinpath("build", "lab", "plan.json"), Path(design).joinpath("build", "lab", "results.json")
    if not pj.is_file():
        return {}
    plan = json.loads(pj.read_text())
    res = json.loads(rj.read_text()) if rj.is_file() else {}
    out: dict[str, dict[str, Any]] = {}
    for r in plan.get("requirements") or []:
        m = r["chosen"]
        row = {"method": m["method"], "instrument": m.get("instrument"), "channel": m.get("channel"), "probes": m.get("probes"),
               "left_out": r.get("left_out") or [], "status": "none" if m["method"] == "on_chip" else "pending", "value": None, "unit": None, "expected": r.get("expected")}
        got = [x for x in res.get("rows") or [] if x.get("requirement") == r["requirement"] and x.get("kind") == "measure"]
        if got and row["status"] != "none":
            g = got[-1]
            row.update(status=g["result"] if g["result"] in ("pass", "fail", "dry_run") else "fail", value=g.get("value"), unit=g.get("unit"), error_ppm=g.get("error_ppm"),
                       typed=g.get("typed"), detail=g.get("detail"))
            if res.get("mode") == "dry_run":
                row["status"] = "dry_run"
        out[r["requirement"]] = row
    return out


def lab_text(lab: dict[str, Any]) -> str:
    """The Method-column line of a requirement's instrument check."""
    if lab["status"] == "none":
        why = "; ".join(f"{x['instrument']}: {x['reason']}" for x in lab["left_out"])
        return "instrument: none, on-chip only" + (f" ({why})" if why else "")
    val = f" read {lab['value']:g} {lab['unit']}" if lab.get("value") is not None else ""
    return f"instrument ({lab['instrument']} {lab['channel']} on {lab['probes']}, {lab['method']}): {lab['status'].replace('_', ' ')}{val}"


# ---- the report -----------------------------------------------------------------------------------------------------------------------
def build_report(design: Path, t: dict[str, Any], spec: dict[str, Any], request: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """The report as data (``report.json``). ``t`` is ``flow.traceability.build``'s record."""
    state = state or {}
    conflicts = {c["requirement"]: c for c in state.get("conflicts") or []}
    by_id = {str(r.get("id")): r for r in spec.get("requirements") or [] if isinstance(r, dict)}
    rows = []
    labs = lab_rows(design)
    for r in t.get("requirements") or []:
        src = by_id.get(r["id"], {"id": r["id"], "text": r["text"]})
        og = origin_of(src, spec, request)
        res, why = _result(r, conflicts.get(r["id"]))
        lab = labs.get(r["id"])
        if lab and lab["status"] == "fail" and res != "fail":                  # an independent instrument check that fails fails the requirement
            res, why = "fail", f"the independent instrument check failed ({lab['instrument']} read {lab.get('value')} {lab.get('unit')}, "\
                               f"{lab.get('error_ppm', 0):+.0f} ppm from the expected value)" if lab.get("error_ppm") is not None else "the independent instrument check failed"
        rows.append({"id": r["id"], "text": r["text"], "origin": og, "result": res, "reason": why,
                     "methods": [{"method": m["method"], "status": m["status"], "evidence": _evidence(design, t, m)} for m in r["methods"]],
                     **({"lab": lab} if lab else {}),
                     "rests_on_unconfirmed": res == "pass" and og["unconfirmed"],
                     "high_risk_default": og["kind"] in ("default", "waiver") and og.get("risk") == "high"})
    n = {k: sum(r["result"] == k for r in rows) for k in ("pass", "pending", "fail")}
    from agent.graph import requirements as RQ
    return {"schema": SCHEMA, "design": design.name, "generated": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": state.get("level"), "level_source": state.get("source"),
            "total": len(rows), "passed": n["pass"], "pending": n["pending"], "failed": n["fail"],
            "unconfirmed_passes": sum(r["rests_on_unconfirmed"] for r in rows),
            "headline": headline(len(rows), n["pass"], n["pending"], n["fail"]),
            "unverified": [r["id"] for r in rows if not any(m["evidence"] for m in r["methods"])],
            "requirements": rows, "conflicts": list(conflicts.values()),
            "assumptions": RQ.assumptions_of(spec),
            "evidence_sources": t.get("evidence_sources"), "trace_pass": t.get("pass")}


def headline(m: int, ok: int, pending: int, failed: int) -> str:
    return f"{ok} of {m} requirements verified and passed; {pending} pending; {failed} failed"


def _c(x: Any) -> str:
    return str(x if x is not None else "").replace("|", "\\|").replace("\n", " ")


def to_markdown(rep: dict[str, Any]) -> str:
    out = [f"# Requirements report: {rep['design']}", "",
           f"Generated {rep['generated']} by `python -m flow.requirements_report`. Requirements level: "
           f"**{rep.get('level') or 'not recorded'}**" + (f" ({rep['level_source']})" if rep.get("level_source") else "") + ". "
           "The matrix underneath is `build/trace/trace.md`.", "",
           f"**{rep['headline']}.**"
           + (f" {rep['unconfirmed_passes']} of the passes rest on a default or an assumption you did not confirm (marked below): "
              "the test passing shows the design matches that guess, not that the guess is what you want." if rep["unconfirmed_passes"] else ""), ""]
    if rep["unverified"]:
        out += [f"No test or check cites: {', '.join(rep['unverified'])}.", ""]
    out += ["| Id | Requirement | Where it came from | Method | Evidence | Result |", "|---|---|---|---|---|---|"]
    for r in rep["requirements"]:
        og = r["origin"]
        came = f"{og['kind']}: {og['detail']}" + (f" ({og['risk']} risk)" if og.get("risk") and og["kind"] in ("default", "waiver", "answered") else "")
        if og["unconfirmed"]:
            came += " **[not confirmed" + (", high risk" if r["high_risk_default"] else "") + "]**"
        meth = "<br>".join([f"{m['method']}: {m['status']}" for m in r["methods"]] + ([lab_text(r["lab"])] if r.get("lab") else [])) or "none"
        ev = "<br>".join((", ".join(f"[{_c(e['name'])}]({e['link']}) {e['result']}" if e["link"] else f"{_c(e['name'])} {e['result']}" for e in m["evidence"]) or "none")
                         for m in r["methods"]) or "none"
        res = r["result"] + (f" ({_c(r['reason'])})" if r["reason"] else "") + (" **[on an unconfirmed default]**" if r["rests_on_unconfirmed"] else "")
        out.append(f"| {r['id']} | {_c(r['text'])} | {_c(came)} | {_c(meth)} | {ev} | {res} |")
    if rep["conflicts"]:
        out += ["", "## A fix that conflicts with a requirement", ""]
        out += [f"- {c['requirement']} ({_c(c.get('requirement_text'))}): the fix for {c['code']} ({c['fix_kind']}) {c['why']}. "
                f"Level {c.get('level')}, action: {c.get('action')}." for c in rep["conflicts"]]
    if rep["assumptions"]:
        out += ["", "## Assumptions you did not confirm", "", "| Risk | Question | The design used | How it was settled |", "|---|---|---|---|"]
        out += [f"| {a['risk']} | {_c(a['question'])} | {_c(a['used'])} | {_c(a['how'])} |" for a in rep["assumptions"]]
    return "\n".join(out) + "\n"


# ---- from the design directory --------------------------------------------------------------------------------------------------------
def _real(p: str | None) -> Path | None:
    """An ``evidence_sources`` path (repo-relative) as a path; None for none or '<outside repo>'."""
    if not p or str(p).startswith("<"):
        return None
    q = Path(p)
    return q if q.is_absolute() else ROOT / q


def refresh(design: Path, *, hw: Path | None = None, runs: Path | None = None, formal: Path | None = None, gates: Path | None = None,
            root: Path | None = None) -> dict[str, Any]:
    """Rebuild the matrix from the design's ``build/`` evidence (the files the agent's trace step reads), write ``build/trace/trace.{json,md}``,
    ``build/requirements/report.json`` and ``REQUIREMENTS_REPORT.md``. Evidence a later stage makes (analysis, hardware, coverage) is
    ``pending`` while its file is absent. Returns the report data."""
    design = Path(design).resolve()
    root = Path(root).resolve() if root else design
    b = design / "build"
    gates = gates or b / "base" / "gates.json"
    hw = hw or b / "bringup" / f"{design.name}_bringup.json"
    runs = runs or b / "verif" / "sim"
    formal = formal or root / "build" / "verif" / "formal"
    defer = tuple(m for m, f in (("analysis", gates), ("hardware", hw)) if not Path(f).is_file())
    if not list(Path(runs).glob("seed*/coverage*")):
        defer += ("coverage",)
    base = b / "trace" / "baseline.json"
    t = tr.build(design, runs, coverage=runs, formal=formal, gates=gates if Path(gates).is_file() else None,
                 hw=hw if Path(hw).is_file() else None, baseline=base if base.is_file() else None, defer=defer)
    return write(design, t)


def write(design: Path, t: dict[str, Any]) -> dict[str, Any]:
    """Write the trace and the report for a built matrix; the data is returned."""
    from agent.graph import requirements as RQ
    design = Path(design)
    b = design / "build"
    (b / "trace").mkdir(parents=True, exist_ok=True)
    (b / "trace" / "trace.json").write_text(json.dumps(t, indent=1, default=str) + "\n")
    (b / "trace" / "trace.md").write_text(tr.to_markdown(t))
    spec = yaml.safe_load((design / "spec.yaml").read_text()) if (design / "spec.yaml").is_file() else {}
    request = (design / "spec.md").read_text(errors="replace") if (design / "spec.md").is_file() else ""
    rep = build_report(design, t, spec or {}, request, RQ.read_state(design))
    jp = design.joinpath(*JSON_REL)
    jp.parent.mkdir(parents=True, exist_ok=True)
    jp.write_text(json.dumps(rep, indent=1, default=str) + "\n")
    (design / REPORT).write_text(to_markdown(rep))
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("design")
    ap.add_argument("--hw", help="the bring-up JSON (default build/bringup/<design>_bringup.json): pending hardware rows become pass or fail from it")
    ap.add_argument("--runs", help="directory of seed*/results.xml (default build/verif/sim)")
    ap.add_argument("--formal", help="SymbiYosys output directory (default build/verif/formal)")
    ap.add_argument("--gates", help="the build's gates.json (default build/base/gates.json)")
    a = ap.parse_args(argv)
    p = lambda x: None if not x else Path(x)
    rep = refresh(Path(a.design), hw=p(a.hw), runs=p(a.runs), formal=p(a.formal), gates=p(a.gates))
    print(rep["headline"])
    for r in rep["requirements"]:
        print(f"  {r['id']:8} {r['result']:8} {r['origin']['kind']}")
    print(f"wrote {Path(a.design) / REPORT}")
    return 0 if rep["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
