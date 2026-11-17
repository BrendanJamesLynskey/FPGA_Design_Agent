"""A handover for a design that has none, written by review (brief 84, using brief 68's three-file shape).

``handover.yaml`` (the facts), ``README.md`` (for an engineer) and ``AGENT.md`` (compact, for the agent), all marked
**produced by review**. They go to the review's output directory, never into the reviewed design. Everything stated is a
fact read from the sources (by code) or the reviewer's reading, with the file and line it rests on; nothing measured (no
resources, timing or power) is claimed, and the gaps say so. It is not in the schema of ``flow/handover.schema.json``
(that schema needs build records a review does not have), so ``flow/doccheck.py`` does not check it: the reviewer's
adoption of the design (a build, the agent's own run) is what turns it into a full handover.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def build(rep: dict[str, Any]) -> dict[str, Any]:
    u = rep["understanding"]
    f = u["facts"]
    mods = {m["name"]: m for m in f["modules"]}
    top = mods.get(f["top"]) or (f["modules"][0] if f["modules"] else {"ports": [], "params": {}})
    return {
        "schema": "fda-handover-review/1", "produced_by": "review", "review_id": rep["review_id"],
        "id": rep["design"]["name"], "design_sha256": rep["design"]["sha256"],
        "summary": u.get("summary") or "(the reviewer's summary is absent: the review ran without the judgement layer)",
        "scope_not": ["a measured design: no build, resources, timing or power were produced by the review",
                      "a verified design: findings are listed in review.json and not all are fixed"],
        "top": f["top"], "clock_domains": f["clock_domains"],
        "interfaces": [{"name": p["name"], "dir": p["dir"], "width": p["width"] or "1"} for p in top["ports"]],
        "parameters": [{"name": k, "default": v} for k, v in top.get("params", {}).items()],
        "files": {"rtl": f["rtl_files"], "tests": f["test_files"], "constraints": f["constraint_files"], "docs": f["doc_files"]},
        "interfaces_text": u.get("interfaces", ""), "clocks_resets_text": u.get("clocks_resets", ""), "architecture_text": u.get("architecture", ""),
        "findings_open": [{"id": x["id"], "severity": x["severity"], "where": x["location"]["file"] + (f":{x['location']['line']}" if x["location"].get("line") else ""),
                           "title": x["title"]} for x in rep["findings"] if x["severity"] in ("critical", "major")],
        "gaps": ["no synthesis, implementation or timing result exists in this handover",
                 "no simulation was run by the review; the tests' coverage is the reviewer's reading", *(rep["verification_gap"].get("missed") or [])[:6]],
        "next_steps": ["fix the critical and major findings, then re-run the review and the check suite at scope synth after a build",
                       "answer the open questions below"],
        "open_questions": rep["questions"],
    }


def write(out: Path, rep: dict[str, Any]) -> dict[str, str]:
    out.mkdir(parents=True, exist_ok=True)
    h = build(rep)
    (out / "handover.yaml").write_text("# Produced by review (flow/review/handover_review.py): facts read from the sources, nothing measured.\n"
                                       + yaml.safe_dump(h, sort_keys=False, width=120))
    L = [f"# {h['id']}: handover (produced by review)", "",
         f"> Produced by review `{h['review_id']}` on design content `{h['design_sha256'][:12]}`. Nothing here was measured. Read `review.json` for the findings.", "",
         "## What it does", "", h["summary"], "", "## Interfaces", "", h["interfaces_text"] or "(not written)", "",
         "| Port | Direction | Width |", "|---|---|---|"] + [f"| `{p['name']}` | {p['dir']} | {p['width']} |" for p in h["interfaces"]] + [
         "", "## Clocks and resets", "", h["clocks_resets_text"] or "(not written)", "", f"Clock domains found in the code: {', '.join(h['clock_domains']) or 'none'}.", "",
         "## Architecture", "", h["architecture_text"] or "(not written)", "", "## Files", ""]
    for k, v in h["files"].items():
        L.append(f"- {k}: {', '.join(f'`{x}`' for x in v) or 'none'}")
    L += ["", "## Open critical and major findings", ""] + ([f"- {x['id']} ({x['severity']}) `{x['where']}`: {x['title']}" for x in h["findings_open"]] or ["- none"])
    L += ["", "## Known gaps and limits", ""] + [f"- {g}" for g in h["gaps"]] + ["", "## Next steps", ""] + [f"- {s}" for s in h["next_steps"]]
    L += ["", "## Open questions", ""] + ([f"- {q}" for q in h["open_questions"]] or ["- none"]) + [""]
    (out / "README.md").write_text("\n".join(L))
    A = [f"# AGENT handover (produced by review) id={h['id']} review={h['review_id']} sha={h['design_sha256'][:12]}",
         f"top={h['top']} clocks={','.join(h['clock_domains'])} rtl={','.join(h['files']['rtl'])} tests={','.join(h['files']['tests'])} constraints={','.join(h['files']['constraints']) or 'none'}",
         "summary: " + h["summary"][:500], "facts: read from sources; no measurement; no build; no simulation by the review",
         "open: " + "; ".join(f"{x['id']}/{x['severity']}/{x['where']}" for x in h["findings_open"]), "gaps: " + " | ".join(h["gaps"][:6]),
         "next: " + " | ".join(h["next_steps"]), ""]
    (out / "AGENT.md").write_text("\n".join(A))
    return {"yaml": "handover/handover.yaml", "readme": "handover/README.md", "agent": "handover/AGENT.md"}
