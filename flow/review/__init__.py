"""Design review mode (brief 84): ``python -m agent review <design-dir>``.

Given an existing design the agent did not write, produce the review a senior FPGA engineer would: what the design does,
findings (severity, place, evidence, rule, fix, confidence), questions for the author, the verification gap, and a handover
when the design has none. Review mode never edits the reviewed design: it works on a copy (``prepare.py``) and writes only
to its output directory; the reviewed tree is hashed before and after.

Parts, each reused from earlier briefs where one exists:

- the check suite (brief 71, ``flow.checks``) at RTL scope, including the reset elaboration (71B) and the AXI rules
  (59A, 71, 73) -> ``collect.py``; this alone is the benchmark's baseline;
- the facts made by code from the sources (modules, ports, clocks, hierarchy, a block diagram) -> ``understand.py``;
- the judgement layer, one reviewer model call -> ``judge.py``;
- a handover for a design that has none (brief 68's three-file shape) -> ``handover_review.py``;
- requested improvements: restate, assess, order (brief 68D's entry stages) -> ``improve.py``; a plan only;
- the findings schema -> ``schema.py``; the human and agent renderings -> ``render.py``.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

from flow.review import collect, handover_review, improve, judge as J, prepare as P, render, understand
from flow.review.schema import SCHEMA_VERSION, Finding, assign_ids, from_dict, sort_findings

INTENT_FILES = ("spec.md", "INTENT.md", "intent.md", "SPEC.md")


def find_intent(design: Path, given: Path | None) -> tuple[str | None, str]:
    if given:
        return Path(given).read_text(errors="replace"), str(given)
    for n in INTENT_FILES:
        if (design / n).is_file():
            return (design / n).read_text(errors="replace"), n
    return None, ""


def merge(suite_findings: list[Finding], reply: dict[str, Any]) -> tuple[list[Finding], list[dict[str, str]], list[str]]:
    """The review's findings: the reviewer's own, plus every check finding it did not dismiss or fold into its own
    (a finding that cites a check id in ``refs`` replaces it and takes source ``both``). Returns (findings, dismissed, problems)."""
    ids = {f.id: f for f in suite_findings}
    problems: list[str] = []
    mine: list[Finding] = []
    for d in reply.get("findings") or []:
        if not isinstance(d, dict):
            problems.append("a finding that is not an object was dropped")
            continue
        f, pr = from_dict(d)
        if f is None:
            problems.append(f"finding {str(d.get('title', ''))[:60]!r} dropped: {'; '.join(pr)}")
            continue
        refs = [r for r in f.refs if r in ids]
        f.refs = refs
        if refs:
            f.source = "both"
        mine.append(f)
    dismissed = []
    for d in reply.get("dismissed") or []:
        if isinstance(d, dict) and d.get("id") in ids:
            dismissed.append({"id": d["id"], "reason": str(d.get("reason", "")).strip() or "(no reason given)"})
    gone = {d["id"] for d in dismissed} | {r for f in mine for r in f.refs}
    keep = [f for f in suite_findings if f.id not in gone]
    allf = keep + mine
    assign_ids(mine)
    # a reviewer finding's id must not collide with a check finding's
    used = {f.id for f in keep}
    for f in mine:
        while f.id in used:
            f.id += "x"
        used.add(f.id)
    return sort_findings(allf), dismissed, problems


def review(design: Path, out: Path, *, intent_file: Path | None = None, improvements: list[str] | None = None, use_judge: bool = True,
           model: str = J.DEFAULT_MODEL, effort: str | None = "medium", claude_bin: str = "claude", scope: str = "rtl",
           runner: Callable[..., dict[str, Any]] | None = None, name: str | None = None, write_files: bool = True,
           tag: str = "review", label: str | None = None) -> dict[str, Any]:
    t0 = time.time()
    design = Path(design).resolve()
    out = Path(out)
    sha_before = P.tree_sha(design)
    prep = P.prepare(design, name=name)
    intent, intent_src = find_intent(design, intent_file)
    suite = collect.run_suite(prep, scope=scope)
    under = understand.analyse(prep["src"], prep["rtl"], prep["top"], prep["tb"], prep["constraints"], prep["docs"])
    facts = {"top": under["top"], "modules": under["modules"], "clock_domains": under["clock_domains"], "rtl_files": under["rtl_files"],
             "test_files": under["test_files"], "constraint_files": under["constraint_files"], "doc_files": under["doc_files"],
             "hierarchy": understand.hierarchy_text(under), "diagram": "block_diagram.svg" if under["top"] else ""}
    reply: dict[str, Any] = {}
    jrec: dict[str, Any] = {"ran": False, "why": "run without the judgement layer (--no-judge): the check suite alone"}
    if use_judge:
        j = J.judge(prep, under, suite, intent, model=model, effort=effort, claude_bin=claude_bin, runner=runner,
                    out_dir=(out / "calls") if write_files else None, tag=tag)
        reply = j["reply"]
        jrec = {"ran": not j["error"], "why": j["error"], "call": j["call"], "prompt_chars": j["prompt_chars"], "prompt_version": j["prompt_version"]}
        if write_files:
            (out / "calls").mkdir(parents=True, exist_ok=True)
            (out / "calls" / f"{tag}.reply.txt").write_text(j["raw"])
    findings, dismissed, problems = merge(suite["findings"], reply)
    rep: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "review_id": tag if label is None else label,
        "design": {"name": name or design.name, "path_label": design.name, "sha256": sha_before, "unchanged": True,
                   "had_build_yaml": prep["had_build_yaml"], "inferred_top": prep["top"]},
        "intent": {"given": bool(intent), "source": intent_src, "text": intent or ""},
        "understanding": {k: reply.get(k, "") for k in ("summary", "interfaces", "clocks_resets", "architecture")} | {"facts": facts},
        "findings": [f.as_dict() for f in findings], "dismissed": dismissed, "sound": [str(x) for x in reply.get("sound") or []],
        "questions": [str(x) for x in reply.get("questions") or []],
        "verification_gap": {k: [str(x) for x in (reply.get("verification_gap") or {}).get(k) or []] for k in ("covered", "missed", "faults_not_caught")},
        "checks": {"scope": scope, "ran": suite["ran"], "not_run": suite["not_run"], "skipped": suite["skipped"], "digest": suite["digest"],
                   "standard": suite["report"].get("standard")},
        "judge": jrec, "judge_problems": problems, "improvements": None, "handover": None,
    }
    if improvements and use_judge:
        from flow.review import judge as JJ
        files_text = "\n\n".join(J.numbered(p, t) for p, t in J.gather(prep["src"]))
        run = runner or (lambda s, p: J.call_claude(s, p, model=model, effort=effort, claude_bin=claude_bin, out_dir=(out / "calls") if write_files else None, tag=tag + "_plan"))
        rep["improvements"] = improve.plan(improvements, rep, files_text, run)
    if not (design / "handover.yaml").is_file() and write_files:
        rep["handover"] = handover_review.write(out / "handover", rep)
    rep["design"]["unchanged"] = P.tree_sha(design) == sha_before
    rep["seconds"] = round(time.time() - t0, 1)
    if write_files:
        out.mkdir(parents=True, exist_ok=True)
        if under["top"]:
            (out / "block_diagram.svg").write_text(understand.svg_block_diagram(under))
        (out / "review.json").write_text(json.dumps(rep, indent=1, default=str) + "\n")
        (out / "REVIEW.md").write_text(render.human(rep))
        (out / "REVIEW_AGENT.md").write_text(render.agent(rep))
    return rep
