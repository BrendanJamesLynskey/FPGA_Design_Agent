#!/usr/bin/env python3
"""The verification record (brief 144, owner decision 26): a generated, hash-pinned statement of what is verified, shipped with every product.

    python -m flow.verified DIR [DIR ...]     write DIR/VERIFIED.md and DIR/verified.json (DIR: designs/<d>, arith/<f> or ip_lib/<e>)
    python -m flow.verified --all             the same for every design, arithmetic function and IP-library entry
    python -m flow.verified --check [DIR ...] exit 1 if a committed record differs from what the generator writes now (CI runs this through
                                              flow/tests/test_144_verified.py); the git commit line is the one field not compared
    python -m flow.verified --label DIR       print the label only

The label ("verified", "verified except: ...", "not verified: ..." or "not assessed: ...") is COMPUTED here from the traceability collector
(``flow/trace_v1.py``) and is defined in docs/verified.md. Nothing is typed. A criterion whose evidence a later brief adds (143a agreement and
method mix, 143b mutation, 143c formal rigour, 143d fresh re-run) is read from the collector's output if the field is there, and is otherwise
shown as "not yet measured" and counts as not met: a label never claims what was not measured.

The record names every file it covers with its SHA-256 (the manifest), the git commit it was generated at (informational: a commit that adds
the record cannot be named inside it, so the check compares the manifest, not the commit) and the commands that reproduce the simulation and
formal evidence. It never carries a board, programming or deploy command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from flow import trace_v1 as T  # noqa: E402

SCHEMA = "fda-verified/1"
NOT_YET = "not yet measured"
# a command is a reproduce command only if it is simulation or formal; these never are (board, programming, bitstream builds, deploys)
DENY = re.compile(r"vivado|bringup|program|\bhw\b|hw_|deploy|xvc|jtag|\bila\b|openocd|ssh |scp |vercel|release\.py|push", re.I)
GENERATED = ("VERIFIED.md", "verified.json", "matrix.md", "matrix.html")
CRITERIA = (
    ("evidence", "Every requirement has passing evidence"),
    ("agreement", "Every requirement is agreed (human, or delegated and labelled so)"),
    ("method_mix", "Every requirement meets its required method mix"),
    ("mutation", "The bench passes the mutation floor"),
    ("formal_rigour", "The formal results pass the rigour checks"),
    ("fresh", "The evidence is fresh"),
)
LIMITS = [
    "Verified never means interoperability with a device the design talks to unless a board measurement against that device is listed in the record; a design that checks its own output against its own model accepts its own symmetric mistakes.",
    "Verified never means timing beyond the stated corner: a post-route timing result is for the part, speed grade, clock and tool version in its evidence file, not for other corners, temperatures or devices.",
    "Verified never means beyond the widths and depths checked: a simulation covers the vectors it ran, a bounded formal result covers the stated depth only, and a per-width proof covers the widths it names; only a Lean proof marked all widths covers every width, and only for its model.",
    "Verified never means the requirement is the right one: the text of a requirement is the human's check (or the planner's, where the record says delegated), and a record shows that checks exist and pass, not that nothing was left out.",
    "Verified never means a hardware or board result unless a board measurement item is listed; a simulation is not the board.",
    "Verified is about the files in the manifest at the hashes given. A change to any of them makes the record out of date (the CI check fails), and the evidence stale until it is re-recorded.",
    "An agreement or acceptance recorded as delegated is the planner's decision on the owner's delegation, not a human sign-off; the record counts it apart.",
]


# ---- helpers ---------------------------------------------------------------------------------------------
def rel(p: Path) -> str:
    return p.resolve().relative_to(ROOT).as_posix()


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git_head() -> str:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def entries() -> list[Path]:
    """Every directory that ships a record: designs/*, arith/* with a testplan, ip_lib/* with an ip.yaml."""
    out = [p for p in sorted((ROOT / "designs").iterdir()) if p.is_dir() and not p.name.startswith(("_", "."))]
    out += sorted(p.parent.parent for p in (ROOT / "arith").glob("*/verif/testplan.yaml"))
    out += sorted(p.parent for p in (ROOT / "ip_lib").glob("*/ip.yaml"))
    return out


def kind_of(d: Path) -> str:
    return d.parent.name          # designs | arith | ip_lib


def manifest(paths: list[str]) -> dict[str, str]:
    m = {}
    for p in sorted(set(paths)):
        f = ROOT / p
        m[p] = sha(f) if f.is_file() else "absent"
    return m


def reproduce(d: Path) -> list[dict]:
    """Simulation and formal commands only. From the testplan's optional `reproduce:` list, else the design's handover commands that are not heavy and
    not a board, programming or deploy step, else the test directory."""
    out: list[dict] = []
    plan = d / "verif" / "testplan.yaml"
    if plan.exists():
        try:
            raw = yaml.safe_load(plan.read_text()) or {}
        except yaml.YAMLError:
            raw = {}
        for c in raw.get("reproduce") or []:
            out.append({"what": c["what"], "cmd": c["cmd"]})
    if not out and (d / "handover.yaml").exists():
        h = yaml.safe_load((d / "handover.yaml").read_text()) or {}
        for c in h.get("commands") or []:
            if not c.get("heavy") and not DENY.search(c["cmd"]):
                out.append({"what": c["what"], "cmd": c["cmd"]})
    if not out:
        for t in ("tests", "tb"):
            if (d / t).is_dir():
                out.append({"what": "the simulation tests", "cmd": f"python -m pytest -q {rel(d)}/{t}"})
                break
    return [c for c in out if not DENY.search(c["cmd"])]       # a deny-listed command is never published, whatever named it


# ---- the requirement view --------------------------------------------------------------------------------
def agreement(r: dict) -> dict:
    """Brief 143a's `agreement` ({kind: human|agent_delegated, by, date}) when the collector supplies it; today the testplan's spec_status only.
    The testplan cannot claim agreement itself, so `agreed` there without a record is not counted."""
    a = r.get("agreement")
    if isinstance(a, dict) and a.get("kind") in ("human", "agent_delegated"):
        return {"status": "agreed_human" if a["kind"] == "human" else "agreed_delegated", "who": a.get("by") or a.get("who") or "not recorded",
                "when": a.get("date") or "not recorded", "text": "agreed (human)" if a["kind"] == "human" else "agreed (delegated, the planner's decision on the owner's delegation)"}
    if r.get("spec_status") == "agreed":
        return {"status": "unrecorded", "who": "not recorded", "when": "not recorded", "text": "marked agreed in the testplan with no agreement record: not counted"}
    return {"status": "draft", "who": "none", "when": "none", "text": "draft: no agreement recorded"}


FRESH = {"pass": "fresh", "bounded": "fresh", "unapproved": "fresh", "stale": "stale", "not_run": "no evidence", "fail": "failing"}


def item_view(i: dict) -> dict:
    ev = i.get("evidence") or {}
    w = i.get("written_by")                                         # brief 143a
    mut = i.get("mutation")                                         # brief 143b
    depth = (i.get("bounded") or {}).get("depth") if isinstance(i.get("bounded"), dict) else None
    v = {"id": i["id"], "method": i["method"], "status": i["status"], "title": i.get("title") or i["id"],
         "bench_author": {"implementing_agent": "implementing agent", "independent_bench": "independent bench", "human": "human"}.get(w, "not recorded"),
         "depth": depth, "mutation_score": mut.get("score") if isinstance(mut, dict) else None,
         "freshness": FRESH.get(i["status"], i["status"]), "record": ev.get("file") if ev.get("exists") else None,
         "record_sha256": sha(ROOT / ev["file"]) if ev.get("exists") and (ROOT / ev["file"]).is_file() else None,
         "instrument": i.get("instrument")}
    if i.get("stale_because"):
        v["stale_because"] = i["stale_because"]
    L = i.get("lean")
    if i["method"] == "formal_lean" and L:
        v["lean"] = {k: L.get(k) for k in ("approver_kind", "tier", "rtl_link", "build_source") if L.get(k)}
    return v


# ---- criteria --------------------------------------------------------------------------------------------
def crit(cid: str, state: str, detail: str, ids: list[str] | None = None) -> dict:
    return {"id": cid, "title": dict(CRITERIA)[cid], "state": state, "detail": detail, "ids": ids or []}


def criteria(c: dict, reqs: list[dict]) -> list[dict]:
    n = len(reqs)
    out = []
    not_ver = [r["id"] for r in reqs if r["state"] != "verified"]
    out.append(crit("evidence", "met" if not not_ver else "unmet",
                    f"all {n} requirements have passing evidence" if not not_ver else
                    f"{len(not_ver)} of {n} requirements are not in state verified: " + ", ".join(f"{r['id']} ({r['state']})" for r in reqs if r["state"] != "verified"), not_ver))
    unagreed = [r["id"] for r in reqs if r["agreement"]["status"] not in ("agreed_human", "agreed_delegated")]
    cnt = {k: sum(1 for r in reqs if r["agreement"]["status"] == k) for k in ("agreed_human", "agreed_delegated", "draft", "unrecorded")}
    out.append(crit("agreement", "met" if not unagreed else "unmet",
                    f"{cnt['agreed_human']} agreed by a human, {cnt['agreed_delegated']} agreed by delegation, {cnt['draft']} draft, {cnt['unrecorded']} marked agreed without a record", unagreed))
    mm = [r for r in reqs if "method_mix" in r]
    if len(mm) < n:
        out.append(crit("method_mix", "not_measured", f"{NOT_YET}: the required method mix per requirement kind is brief 143a; the collector does not supply it yet"))
    else:
        bad = [r["id"] for r in mm if not (r["method_mix"] or {}).get("met")]
        out.append(crit("method_mix", "met" if not bad else "unmet", f"{n - len(bad)} of {n} requirements meet their mix", bad))
    mu = c.get("mutation")
    if not isinstance(mu, dict) or "met" not in mu:
        out.append(crit("mutation", "not_measured", f"{NOT_YET}: the mutation score and floor are brief 143b; the collector does not supply them yet"))
    else:
        out.append(crit("mutation", "met" if mu["met"] else "unmet", f"mutation score {mu.get('score')} against a floor of {mu.get('floor')}"))
    has_formal = any(i["method"] == "formal" for i in c["items"])
    fr = c.get("formal_rigour")
    if not has_formal:
        out.append(crit("formal_rigour", "met", "no SymbiYosys item in the testplan, so there is no proof to check for vacuity or depth (a Lean item is checked by the kernel, see its tier)"))
    elif not isinstance(fr, dict) or "met" not in fr:
        out.append(crit("formal_rigour", "not_measured", f"{NOT_YET}: the vacuity, assumption and depth checks are brief 143c; the collector does not supply them yet"))
    else:
        out.append(crit("formal_rigour", "met" if fr["met"] else "unmet", str(fr.get("detail") or "")))
    stale = [i["id"] for i in c["items"] if i["status"] == "stale"]
    fresh_run = c.get("fresh_run")
    if stale:
        out.append(crit("fresh", "unmet", f"{len(stale)} items are stale (a file they are about changed after the evidence was recorded)", stale))
    elif not isinstance(fresh_run, dict) or "differs" not in fresh_run:
        out.append(crit("fresh", "not_measured", "no item is stale by its pins; the nightly fresh re-run comparison is brief 143d and " + NOT_YET))
    else:
        out.append(crit("fresh", "met" if not fresh_run["differs"] else "unmet", f"the fresh re-run differs from the committed record for {len(fresh_run['differs'])} items", fresh_run["differs"]))
    return out


def label_of(crits: list[dict], reqs: list[dict]) -> tuple[str, str]:
    """(kind, text). verified: every criterion met. not verified: a requirement fails or none verified. else verified except."""
    n = len(reqs)
    failing = [r["id"] for r in reqs if r["state"] == "fail"]
    if failing:
        return "not_verified", f"not verified: {len(failing)} of {n} requirements fail"
    if not any(r["state"] == "verified" for r in reqs):
        return "not_verified", f"not verified: no requirement of {n} has passing evidence"
    bits = []
    for k in crits:
        if k["state"] == "met":
            continue
        if k["state"] == "not_measured":
            bits.append({"method_mix": "required method mix not yet measured", "mutation": "mutation floor not yet measured",
                         "formal_rigour": "formal rigour not yet measured", "fresh": "fresh re-run not yet measured"}[k["id"]])
        else:
            m = len(k["ids"])
            bits.append({"evidence": f"{m} of {n} requirements without passing evidence", "agreement": f"{m} of {n} requirements not agreed",
                         "method_mix": f"{m} of {n} requirements short of their method mix", "mutation": "mutation floor not met",
                         "formal_rigour": "formal rigour checks not met", "fresh": f"{m} stale or differing evidence items"}[k["id"]])
    return ("verified", "verified") if not bits else ("verified_except", "verified except: " + "; ".join(bits))


def limits_for(c: dict, reqs: list[dict]) -> list[str]:
    out = list(LIMITS)
    ext = [r for r in reqs if r.get("hardware_closure") == "open"]
    if ext:
        out.append(f"{len(ext)} requirements depend on an element outside the design and have not been closed by hardware, so they hold in simulation only: " + ", ".join(r["id"] for r in ext) + ".")
    bounded = [i for i in c["items"] if i.get("bounded") is not None]
    if bounded:
        out.append(f"{len(bounded)} formal items are bounded model checks; each holds to its stated depth only: " + ", ".join(i["id"] for i in bounded[:8]) + (" and others." if len(bounded) > 8 else "."))
    sim = [r["id"] for r in reqs if r["kind"] == "performance" and r.get("basis") == "simulation"]
    if sim:
        out.append(f"{len(sim)} performance requirements are verified in simulation only, not measured on the board: " + ", ".join(sim) + ".")
    tim = [r["id"] for r in reqs if r["kind"] == "performance" and r.get("basis") == "timing"]
    if tim:
        out.append(f"{len(tim)} performance requirements are verified by post-route timing at one corner: " + ", ".join(tim) + ".")
    lt = [r["id"] for r in reqs if r.get("lean_transcription_only") and r["state"] == "verified"]
    if lt:
        out.append("Lean proofs here are of a transcription of the RTL, not of the RTL itself: " + ", ".join(lt) + ".")
    return out


# ---- the record ------------------------------------------------------------------------------------------
def record(d: Path) -> dict[str, Any]:
    d = d.resolve()
    rid = rel(d)
    rec: dict[str, Any] = {"schema": SCHEMA, "path": rid, "kind": kind_of(d), "name": d.name, "git_commit": git_head(),
                           "definition": "docs/verified.md", "criteria": [], "requirements": [], "declared": None}
    plan = d / "verif" / "testplan.yaml"
    files: list[str] = []
    if plan.exists() and all("kind" in r for r in (yaml.safe_load(plan.read_text()).get("requirements") or [])):      # a library entry whose testplan has no requirement kinds (brief 151's own format) is not rolled up by the collector yet
        c = T.collect(d)
        items = {i["id"]: i for i in c["items"]}
        reqs = []
        for r in c["requirements"]:
            row = dict(r)
            row["agreement"] = agreement(r)
            row["item_views"] = [item_view(items[x]) for x in r["items"]]
            reqs.append(row)
        crits = criteria(c, reqs)
        lk, lt = label_of(crits, reqs)
        files += [rel(plan)] + [rel(p) for p in sorted((d / "verif").glob("*.yaml"))]
        for i in c["items"]:
            ev = i.get("evidence") or {}
            if ev.get("exists"):
                files.append(ev["file"])
            files += i.get("checks") or []
            if i["method"] == "formal_lean":
                files.append("formal/lean/records/build_record.json")
        files = [f for f in files if Path(f).name not in GENERATED]
        rec.update(label_kind=lk, label=lt, criteria=crits, summary_line=c["summary"]["line"], notes=c.get("notes", ""),
                   counts={"requirements": len(reqs), "verified": sum(1 for r in reqs if r["state"] == "verified"),
                           "agreed_human": sum(1 for r in reqs if r["agreement"]["status"] == "agreed_human"),
                           "agreed_delegated": sum(1 for r in reqs if r["agreement"]["status"] == "agreed_delegated"),
                           "draft": sum(1 for r in reqs if r["agreement"]["status"] in ("draft", "unrecorded")),
                           "items": len(c["items"]), "stale_items": sum(1 for i in c["items"] if i["status"] == "stale")},
                   requirements=reqs, limits=limits_for(c, reqs))
    else:
        rec.update(label_kind="not_assessed", label="not assessed: no requirements recorded (no verif/testplan.yaml), so nothing here is traced to a requirement",
                   counts={"requirements": 0}, limits=list(LIMITS))
        rec["criteria"] = [crit(k, "not_measured", "no requirements recorded") for k, _ in CRITERIA]
        if kind_of(d) == "ip_lib":
            y = yaml.safe_load((d / "ip.yaml").read_text()) or {}
            rec["declared"] = {"source": "ip.yaml", "status": y.get("status"), "note": "the entry's own declared status; not traced to requirements and not checked by this record"}
            files += [rel(d / "ip.yaml")] + [rel(d / p) for p in (y.get("rtl") or [])]
            files += [rel(p) for sub in ("tb", "char") for p in sorted((d / sub).glob("*")) if p.is_file() and p.suffix in (".py", ".json", ".sv", ".yaml")]
            files += [rel(p) for p in (d / "model.py", d / "faults.yaml") if p.exists()]
        elif (d / "handover.yaml").exists():
            h = yaml.safe_load((d / "handover.yaml").read_text()) or {}
            rec["declared"] = {"source": "handover.yaml", "status": (h.get("state") or {}).get("stage"),
                               "evidence": [{"id": e.get("id"), "activity": e.get("activity"), "result": e.get("result"), "record": e.get("record")} for e in h.get("evidence") or []],
                               "note": "the design's own declared evidence; not traced to requirements and not checked by this record"}
            files += [rel(d / "handover.yaml")] + [e["record"] for e in h.get("evidence") or [] if e.get("record") and (ROOT / e["record"]).is_file()]
            files += [rel(p) for p in sorted((d / "rtl").glob("*")) if p.is_file()]
    rec["manifest"] = manifest(files)
    rec["reproduce"] = reproduce(d)
    return rec


# ---- rendering -------------------------------------------------------------------------------------------
HEAD = "<!-- Generated by `python -m flow.verified {p}` (brief 144) from the traceability collector and the files in the manifest. Do not edit. -->"
STATE_WORD = {"met": "met", "unmet": "NOT met", "not_measured": "not yet measured (counts as not met)"}


def render_md(rec: dict) -> str:
    p = rec["path"]
    L = [f"# {rec['name']}: verification record", "", HEAD.format(p=p), "",
         f"**{rec['label'][0].upper() + rec['label'][1:]}.**", "",
         f"What the label means, what \"verified\" never means and how it is earned: [docs/verified.md]({'../' * (p.count('/') + 1)}docs/verified.md). "
         f"The label is computed from the testplan and the evidence files named below; it is never typed. Generated at git commit `{rec['git_commit']}` "
         "(informational: the hashes in the manifest, not the commit, are what the CI check compares).", ""]
    if rec.get("summary_line"):
        L += [f"Traceability summary: {rec['summary_line']}", ""]
    L += ["## What was checked for the label", "", "| Criterion | Result | Detail |", "|---|---|---|"]
    for k in rec["criteria"]:
        L.append(f"| {k['title']} | {STATE_WORD[k['state']]} | {k['detail'].replace('|', '/')} |")
    L.append("")
    if rec.get("declared"):
        dc = rec["declared"]
        L += ["## Declared status (not part of the label)", "", f"From `{dc['source']}`: {dc.get('status') or 'no status stated'}. {dc['note'].capitalize()}.", ""]
        for e in dc.get("evidence") or []:
            L.append(f"- {e['id']}: {e['activity']}, {e['result']} (`{e['record']}`)")
        if dc.get("evidence"):
            L.append("")
    if rec["requirements"]:
        L += ["## Requirements", "",
              "Per requirement: its text, kind, agreement, state and every evidence item with its method, who wrote the bench, proof depth or mutation score where they apply, "
              "whether it is fresh, and the record it reads. A field a later brief adds shows as \"not yet measured\".", ""]
    for r in rec["requirements"]:
        a = r["agreement"]
        L += [f"### {r['id']}: {r['title']}", "", f"- Kind: {r['kind']}. State: {T._state_cell(r)}.",
              f"- Agreement: {a['text']}" + (f" (by {a['who']}, {a['when']})" if a["status"].startswith("agreed") else "") + ".",
              f"- Method mix required by its kind: {r['method_mix'] if 'method_mix' in r else NOT_YET + ' (brief 143a)'}. Mutation score of its bench: {NOT_YET} (brief 143b)."]
        if r.get("text"):
            L.append(f"- Text: {r['text']}")
        if r.get("source"):
            L.append(f"- Source: `{r['source']}`")
        for i in r["item_views"]:
            extra = []
            if i["depth"] is not None:
                extra.append(f"proof depth {i['depth']}")
            if i["mutation_score"] is not None:
                extra.append(f"mutation score {i['mutation_score']}")
            if i.get("lean"):
                extra.append("Lean: " + ", ".join(f"{k}={v}" for k, v in i["lean"].items()))
            if i.get("instrument"):
                extra.append(f"instrument {i['instrument']}")
            rec_s = f"record `{i['record']}`" + f" (sha256 {i['record_sha256'][:12]})" if i["record"] else "no record"
            L.append(f"  - `{i['id']}` {i['method']}: **{i['status']}**, bench author: {i['bench_author']}; {'; '.join(extra + [i['freshness']])}; {rec_s}"
                     + (f"; stale because {i['stale_because']}" if i.get("stale_because") else "") + ".")
        L.append("")
    L += ["## Limits", ""] + [f"- {x}" for x in rec["limits"]] + ["", "## Hash manifest", "",
          f"Every file this record covers, with its SHA-256 at generation ({len(rec['manifest'])} files). `absent` marks a named file that does not exist.", "",
          "| File | SHA-256 |", "|---|---|"]
    L += [f"| `{k}` | `{v}` |" for k, v in rec["manifest"].items()]
    L += ["", "## Reproduce", "", "Simulation and formal evidence only; this record never lists a board, programming or deploy command.", ""]
    L += [f"- {c['what']}: `{c['cmd']}`" for c in rec["reproduce"]] or ["- no simulation or formal command is recorded for this entry."]
    return "\n".join(L) + "\n"


def render_json(rec: dict) -> str:
    return json.dumps(rec, indent=1, sort_keys=True) + "\n"


def outputs(d: Path) -> dict[Path, str]:
    rec = record(d)
    return {d / "VERIFIED.md": render_md(rec), d / "verified.json": render_json(rec)}


COMMIT = re.compile(r"git commit `[^`]*`|\"git_commit\": \"[^\"]*\"")


def norm(text: str) -> str:
    """The commit is the one field not compared (a record cannot name the commit that adds it)."""
    return COMMIT.sub("git commit", text)


def check(dirs: list[Path]) -> list[str]:
    bad = []
    for d in dirs:
        for p, text in outputs(d).items():
            if not p.exists():
                bad.append(f"{rel(p)}: missing (run: python -m flow.verified {rel(d)})")
            elif norm(p.read_text()) != norm(text):
                bad.append(f"{rel(p)}: differs from the generator's output (run: python -m flow.verified {rel(d)})")
    return bad


def label_of_dir(d: Path) -> str | None:
    p = d / "verified.json"
    return json.loads(p.read_text())["label"] if p.exists() else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--label", action="store_true")
    a = ap.parse_args(argv)
    dirs = entries() if a.all or not a.dirs else [(ROOT / x).resolve() if not Path(x).is_absolute() else Path(x) for x in a.dirs]
    if a.check:
        bad = check(dirs)
        print("\n".join(bad) if bad else f"verification records current for {len(dirs)} entries")
        return 1 if bad else 0
    for d in dirs:
        if a.label:
            print(f"{rel(d)}: {record(d)['label']}")
            continue
        for p, text in outputs(d).items():
            p.write_text(text)
        print(f"{rel(d)}: {json.loads((d / 'verified.json').read_text())['label']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
