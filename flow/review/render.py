"""The review report renderers (brief 84): a human version and an agent version of the same findings.

Human: Markdown for an engineer: understanding, a block diagram, findings by severity with place, evidence, rule and fix,
the verification gap, questions, and what was and was not checked. Agent: compact Markdown with one line per finding and
stable ids, sized so an agent can read the whole of it before it changes anything (the brief 68 split). Neither is
written by a model: both are rendered from ``review.json``, so a sentence in the report is a field of the record.
"""

from __future__ import annotations

from typing import Any

SEV_ORDER = ("critical", "major", "minor", "info")


def _loc(f: dict[str, Any]) -> str:
    l = f["location"]
    if not l.get("file"):
        return l.get("object") or "-"
    s = l["file"] + (f":{l['line']}" if l.get("line") else "")
    if l.get("end_line") and l["end_line"] != l.get("line"):
        s += f"-{l['end_line']}"
    return s + (f" ({l['object']})" if l.get("object") else "")


def _group(findings: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Check findings that differ only by line (the same rule, file and message) are shown once with all their lines."""
    out: dict[tuple, list[dict[str, Any]]] = {}
    for f in findings:
        key = (f["source"], f["rule"], f["location"]["file"], f["evidence"], f["severity"]) if f["source"].startswith("check:") else (f["id"],)
        out.setdefault(key, []).append(f)
    return list(out.values())


def human(rep: dict[str, Any]) -> str:
    u, d = rep["understanding"], rep["design"]
    L = [f"# Design review: {d['name']}", ""]
    L += [f"*Review {rep['review_id']}, schema {rep['schema_version']}. Reviewed directory `{d['path_label']}`, content hash `{d['sha256'][:12]}`; "
          f"the reviewed files were not changed (hash checked again at the end: {'unchanged' if d['unchanged'] else 'CHANGED'}).*", ""]
    if rep["intent"]["given"]:
        L += ["**Statement of intent (given):** " + rep["intent"]["text"].strip().splitlines()[0][:300], ""]
    else:
        L += ["**Statement of intent:** none given; the intent below is inferred.", ""]
    L += ["## 1. Understanding", ""]
    for k, h in (("summary", "What it does"), ("interfaces", "Interfaces"), ("clocks_resets", "Clocks and resets"), ("architecture", "Architecture as built")):
        if u.get(k):
            L += [f"**{h}.** {u[k]}", ""]
    if not rep["judge"]["ran"]:
        L += [f"*The reviewer's prose is absent: {rep['judge']['why']}. Only the facts made by code follow.*", ""]
    L += ["Facts made by code from the sources:", ""]
    L += ["| Module | File | Clocks | Async-reset edges | Instantiates |", "|---|---|---|---|---|"]
    for m in u["facts"]["modules"]:
        L.append(f"| `{m['name']}` | `{m['file']}:{m['line']}` | {', '.join(m['clocks']) or '-'} | {', '.join(m['async_reset_edges']) or '-'} | {', '.join(i['module'] for i in m['instances']) or '-'} |")
    L += ["", "```", u["facts"]["hierarchy"], "```", ""]
    if u["facts"].get("diagram"):
        L += [f"Block diagram of the top module: [block_diagram.svg]({u['facts']['diagram']}) (made from the source hierarchy).", ""]
    fs = rep["findings"]
    cnt = {s: sum(1 for f in fs if f["severity"] == s) for s in SEV_ORDER}
    L += ["## 2. Findings", "", "Counts: " + ", ".join(f"{cnt[s]} {s}" for s in SEV_ORDER) + ".", ""]
    for s in SEV_ORDER:
        grp = _group([f for f in fs if f["severity"] == s])
        if not grp:
            continue
        L += [f"### {s.capitalize()}", ""]
        for g in grp:
            f = g[0]
            n = f" (x{len(g)}: lines {', '.join(str(x['location']['line']) for x in g if x['location'].get('line'))})" if len(g) > 1 else ""
            L += [f"**{f['id']} {f['title']}**{n}", f"- Where: `{_loc(f)}`; category {f['category']}; confidence {f['confidence']}; found by {f['source']}",
                  f"- Evidence: {f['evidence'] or '(none given)'}", f"- Rule or reason: {f['rule'] or '-'}", f"- Suggested fix: {f['fix'] or '-'}", ""]
    if rep["dismissed"]:
        L += ["### Check findings the reviewer dismissed", ""] + [f"- {x['id']}: {x['reason']}" for x in rep["dismissed"]] + [""]
    if rep.get("sound"):
        L += ["### Looked at and found sound", ""] + [f"- {s}" for s in rep["sound"]] + [""]
    vg = rep["verification_gap"]
    L += ["## 3. Verification gap", ""]
    for k, h in (("covered", "What the existing tests cover"), ("missed", "What they miss"), ("faults_not_caught", "Seeded faults they would not catch")):
        if vg.get(k):
            L += [f"**{h}.**"] + [f"- {x}" for x in vg[k]] + [""]
    L += ["No coverage run or mutation run was made by the review: the lists above are the reviewer's reasoning from the test files.", ""]
    L += ["## 4. Questions for the author", ""] + ([f"- {q}" for q in rep["questions"]] if rep["questions"] else ["None: the code and the files answered what could be answered."]) + [""]
    L += ["## 5. What was checked, and what was not", "", "| Check | Result |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in rep["checks"]["ran"].items()]
    for k, v in rep["checks"]["not_run"].items():
        L.append(f"| {k} | not run: {v[:120]} |")
    L += ["", f"Scope: {rep['checks']['scope']}. No synthesis was run, so the post-synthesis checks (CDC report, methodology, DRC, timing) did not run; "
          "a clock-domain crossing is therefore found only by the reviewer's reading. Run the suite at scope synth after a build to add them.", ""]
    if rep.get("handover"):
        L += ["## 6. Handover", "", f"The design had no handover. One was written, marked produced by review: [{rep['handover']['yaml']}]({rep['handover']['yaml']}), "
              f"[README]({rep['handover']['readme']}), [AGENT.md]({rep['handover']['agent']}).", ""]
    if rep.get("improvements"):
        L += ["## 7. Requested improvements: plan", ""] + improvements_md(rep["improvements"])
    c = rep["judge"].get("call") or {}
    L += ["## Provenance", "", f"- Reviewer: {c.get('model_requested', 'none (check suite only)')}, effort {c.get('effort', '-')}, Claude Code {c.get('version', '-')}; "
          f"tokens as the provider reported them: {(c.get('usage') or {}).get('total_tokens', 0)}; wall {c.get('wall_s', 0)} s.",
          f"- Prompt version {rep['judge'].get('prompt_version', '-')}; check suite standard {rep['checks'].get('standard', '-')}.", ""]
    return "\n".join(L)


def improvements_md(imp: dict[str, Any]) -> list[str]:
    L = []
    o = imp["order"]
    if o["steps"]:
        L += ["Proposed order:", ""] + [f"{i + 1}. {s}" for i, s in enumerate(o["steps"])] + [""]
    for p in o["problems"]:
        L.append(f"- Plan problem: {p}")
    for it in imp["items"]:
        g, a = it.get("goal") or {}, it.get("assessment") or {}
        L += [f"**{it['id']}: {it.get('request', '')}**",
              f"- Measurable goal: {g.get('metric', '-')} {g.get('target', '')} ({g.get('conditions', '')}); acceptance test: {g.get('acceptance_test', '-')}"]
        if not it.get("measurable", True):
            L.append(f"- Question for the user: {it.get('question', '')}")
        L += [f"- Feasibility: {a.get('feasibility', '-')}: {a.get('why', '')}", f"- Approach: {a.get('approach', '')}",
              f"- Risks: {'; '.join(a.get('risks') or []) or '-'}; touches: {', '.join(a.get('touches') or []) or '-'}",
              f"- Depends on: {', '.join(a.get('depends_on') or []) or '-'}; conflicts with: {', '.join(a.get('conflicts_with') or []) or '-'}; "
              f"cost {(a.get('cost') or {}).get('size', '-')}",
              f"- Would enter the agent's flow at stage {it['entry']['stage']} ({it['entry']['kind']}), by the resume mechanism", ""]
    for n in imp.get("notes") or []:
        L.append(f"- Note: {n}")
    return L + [""]


def agent(rep: dict[str, Any]) -> str:
    """Compact: one line per finding. Read it whole before editing the design."""
    d = rep["design"]
    L = [f"# REVIEW (agent) {d['name']} id={rep['review_id']} schema={rep['schema_version']} design_sha={d['sha256'][:12]} mode=review (read-only)",
         "top: " + str(rep["understanding"]["facts"]["top"]) + "; clocks: " + ", ".join(rep["understanding"]["facts"]["clock_domains"]) + "; scope: " + rep["checks"]["scope"],
         "checks: " + ", ".join(f"{k}={v}" for k, v in rep["checks"]["ran"].items()) + " | not run: " + ", ".join(rep["checks"]["not_run"]) ,
         "summary: " + (rep["understanding"].get("summary") or "(none)")[:400], "", "FINDINGS id | sev | cat | where | conf | src | title | fix"]
    for g in _group(rep["findings"]):
        f = g[0]
        lines = ",".join(str(x["location"]["line"]) for x in g if x["location"].get("line"))
        loc = f["location"]["file"] + (f":{lines}" if lines else "")
        L.append(f"{f['id']} | {f['severity']} | {f['category']} | {loc or f['location'].get('object') or '-'} | {f['confidence']} | {f['source']} | {f['title'][:100]} | {f['fix'][:160]}")
    if rep["questions"]:
        L += ["", "QUESTIONS"] + [f"- {q}" for q in rep["questions"]]
    vg = rep["verification_gap"]
    L += ["", "TEST GAPS"] + [f"- {x}" for x in vg.get("missed", [])]
    if rep.get("improvements"):
        o = rep["improvements"]["order"]
        L += ["", "PLAN order: " + " > ".join(o["steps"])]
        for it in rep["improvements"]["items"]:
            L.append(f"{it['id']} | measurable={it.get('measurable', True)} | enter stage {it['entry']['stage']} | test: {(it.get('goal') or {}).get('acceptance_test', '')[:140]} | "
                     f"deps {','.join((it.get('assessment') or {}).get('depends_on') or []) or '-'}")
    L += ["", "RULES: this review did not edit the design; fixes are separate, opt-in work. Re-run the checks after any change."]
    return "\n".join(L)
