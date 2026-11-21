#!/usr/bin/env python3
"""Lean 4 as a "proved for all widths" evidence tier of the traceability matrix (brief 125).

The `formal_lean` method of ``flow/trace_v1.py`` is judged here. An item names a theorem of the Lean project (``formal/lean``), and this
module decides, from evidence and never from typed text:

* **Build status.** Computed by running ``lake build`` (in a scratch copy, with ``#print axioms`` appended) when the toolchain is present and
  the caller asks for it (``live``). Where the toolchain is absent (CI, most machines) the status is read from the committed, hash-pinned build
  record ``formal/lean/records/build_record.json`` and is shown as a *recorded build*, never as a re-run.
* **Axiom-audit tier**, from ``#print axioms``: ``kernel_only`` (only propext, Classical.choice, Quot.sound), ``compiled_decision_procedure``
  (also axioms that name a compiled SAT-certificate check, as ``bv_decide`` adds), ``unsound`` (``sorryAx`` or any other axiom).
* **Staleness.** The record pins the SHA-256 of every Lean file of the project, of each theorem's statement and of the definitions it rests on,
  and of the transcribed RTL lines. A change to any of them since the record makes the item stale.
* **The frozen statement.** A theorem statement is the specification. When a human approves a statement (``verif/lean_approvals.yaml``; no code
  and no agent writes that file), the approval pins the statement's hash and the hash of the file's definitions. A statement or definition that
  no longer matches is a gate failure of ``python -m flow.trace_v1 check``, not a warning. A statement with no approval is shown as
  "statement not approved" and is not counted as verified.
* **The RTL link, stated honestly.** ``rtl_generated`` (a tool made the Lean model from the RTL; none exists yet), ``transcription_tested`` (a
  person wrote the Lean model from named RTL lines, and a cross-check test compares it with an independent reference), ``transcription_untested``,
  ``model_only`` (pure mathematics, no RTL named). The matrix prints these as different things.

  python -m flow.trace_v1 lean-record [DESIGN ...]     rebuild with `lake build` and write the record (needs the toolchain)
  python -m flow.trace_v1 lean-statement DESIGN ITEM   print the statement and the hashes a human would approve (writes nothing)
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = "formal/lean"
RECORD_SCHEMA = "fpga-design-agent/lean-build-record/v1"
APPROVAL_SCHEMA = "fpga-design-agent/lean-approvals/v1"
ALLOWED_AXIOMS = frozenset({"propext", "Classical.choice", "Quot.sound"})
COMPILED = re.compile(r"(\._native\.bv_decide\.ax_\d+_\d+$)|^Lean\.ofReduceBool$|^Lean\.trustCompiler$")
TIERS = ("kernel_only", "compiled_decision_procedure", "unsound")
TIER_TEXT = {"kernel_only": "kernel only", "compiled_decision_procedure": "kernel plus a compiled decision procedure", "unsound": "unsound"}
RTL_LINKS = ("rtl_generated", "transcription_tested", "transcription_untested", "model_only")
RTL_LINK_TEXT = {"rtl_generated": "proof about the RTL (Lean model generated from it)",
                 "transcription_tested": "proof of the transcription, transcription tested",
                 "transcription_untested": "proof of the transcription, transcription not tested",
                 "model_only": "proof of a model, no RTL link"}
RTL_LINK_SHORT = {"rtl_generated": "RTL-generated model", "transcription_tested": "transcription tested", "transcription_untested": "transcription untested",
                  "model_only": "no RTL link"}


class LeanError(Exception):
    """A formal_lean item or the record is malformed (reported by the gate, never a traceback)."""


# ---- the toolchain ---------------------------------------------------------------------------------------
def lake_path() -> str | None:
    p = shutil.which("lake")
    if p:
        return p
    q = Path.home() / ".elan" / "bin" / "lake"
    return str(q) if q.exists() else None


def toolchain_available() -> bool:
    return lake_path() is not None


def _env() -> dict[str, str]:
    env = dict(os.environ)
    lp = lake_path()
    if lp:
        env["PATH"] = str(Path(lp).parent) + os.pathsep + env.get("PATH", "")
    return env


# ---- statements: what a human approves -------------------------------------------------------------------
def _statements_mod() -> Any:
    p = ROOT / DEFAULT_PROJECT / "tools" / "statements.py"
    spec = importlib.util.spec_from_file_location("lean_statements", p)
    m = importlib.util.module_from_spec(spec)          # type: ignore[arg-type]
    spec.loader.exec_module(m)                         # type: ignore[union-attr]
    return m


def sha_text(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def module_path(project: str, module: str) -> Path:
    return ROOT / project / Path(*module.split(".")).with_suffix(".lean")


def namespace_of(src: str) -> str:
    m = re.search(r"^namespace\s+(\S+)", src, flags=re.M)
    return m.group(1) if m else ""


def frozen(project: str, module: str, theorem: str) -> dict[str, Any] | None:
    """The statement of ``theorem`` (a qualified name, as ``#print axioms`` spells it) and the definitions of its module, comments ignored and
    whitespace normalised, with their hashes. ``None`` if the module or the theorem is missing. The definitions are part of what is approved:
    a statement means nothing if a definition it uses is edited."""
    mp = module_path(project, module)
    if not mp.exists():
        return None
    src = mp.read_text()
    ns = namespace_of(src)
    short = theorem[len(ns) + 1:] if ns and theorem.startswith(ns + ".") else theorem
    blocks = _statements_mod().blocks(src)
    stmt = [t for k, n, t in blocks if k in ("theorem", "lemma") and n == short]
    if not stmt:
        return None
    defs = [t for k, n, t in blocks if k in ("def", "abbrev")]
    return {"statement": stmt[0], "statement_sha256": sha_text(stmt[0]), "definitions": defs, "definitions_sha256": sha_text("\n".join(defs))}


# ---- the project's files and the transcribed RTL ---------------------------------------------------------
def project_files(project: str) -> dict[str, str]:
    """SHA-256 of every file the build reads: the .lean files (not .lake, tools, records), the lakefile, the manifest, the toolchain file."""
    base = ROOT / project
    out: dict[str, str] = {}
    for p in sorted(base.rglob("*.lean")):
        r = p.relative_to(base)
        if r.parts[0] in (".lake", "tools", "records"):
            continue
        out[r.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    for n in ("lakefile.toml", "lake-manifest.json", "lean-toolchain"):
        if (base / n).exists():
            out[n] = hashlib.sha256((base / n).read_bytes()).hexdigest()
    return out


def _git_show(commit: str, path: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{path}"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def source_key(s: dict) -> str:
    return f"{s['file']}:{s['lines']}" + (f"@{s['commit']}" if s.get("commit") else "")


def source_hash(s: dict) -> str | None:
    """SHA-256 of the transcribed RTL lines (``lines: "77-82"``, 1-based and inclusive). With ``commit`` the lines come from that commit (so they
    cannot go stale; used where the file is not in this tree, and then only when git has the object); otherwise from the working tree."""
    m = re.fullmatch(r"(\d+)-(\d+)", str(s.get("lines", "")))
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    if s.get("commit"):
        text = _git_show(s["commit"], s["file"])
    else:
        p = ROOT / s["file"]
        text = p.read_text() if p.exists() else None
    if text is None:
        return None
    lines = text.splitlines()
    if a < 1 or b < a or b > len(lines):
        return None
    return sha_text("\n".join(lines[a - 1:b]))


# ---- the build -------------------------------------------------------------------------------------------
def parse_axioms(log: str, qualified: str) -> list[str] | None:
    m = re.search(r"'%s' depends on axioms: \[(.*?)\]" % re.escape(qualified), log, flags=re.S)
    if m:
        return sorted(x.strip() for x in m.group(1).split(",") if x.strip())
    return [] if re.search(r"'%s' does not depend on any axioms" % re.escape(qualified), log) else None


def tier_of(axioms: list[str]) -> str:
    if "sorryAx" in axioms or any(a not in ALLOWED_AXIOMS and not COMPILED.search(a) for a in axioms):
        return "unsound"
    return "compiled_decision_procedure" if any(COMPILED.search(a) for a in axioms) else "kernel_only"


def build_live(project: str, theorems: list[tuple[str, str]]) -> dict[str, Any]:
    """``lake build`` in a scratch copy of the project (the tree is never touched), with ``#print axioms`` appended for each
    ``(module, qualified theorem)``. Returns the build outcome and, per theorem, its axioms and tier."""
    lp = lake_path()
    if lp is None:
        raise LeanError("the Lean toolchain (lake) is not installed")
    with tempfile.TemporaryDirectory(prefix="lean_tier_") as td:
        work = Path(td) / "p"
        shutil.copytree(ROOT / project, work, ignore=shutil.ignore_patterns(".lake", "tools", "records"))
        by_mod: dict[str, list[str]] = {}
        for mod, th in theorems:
            by_mod.setdefault(mod, []).append(th)
        for mod, ths in by_mod.items():
            f = work / Path(*mod.split(".")).with_suffix(".lean")
            src = f.read_text()
            ns = namespace_of(src)
            probe = "\n".join(f"#print axioms {t}" for t in ths)
            f.write_text(re.sub(r"\nend " + re.escape(ns) + r"\s*$", "\n" + probe + "\nend " + ns + "\n", src) if ns else src + "\n" + probe + "\n")
        p = subprocess.run([lp, "build"], cwd=work, capture_output=True, text=True, timeout=1800, env=_env())
    log = p.stdout + p.stderr
    ok = p.returncode == 0
    res: dict[str, Any] = {}
    for mod, th in theorems:
        ax = parse_axioms(log, th)
        if not ok or ax is None:
            res[th] = {"module": mod, "build_ok": False, "axioms": ax, "tier": None, "first_error": next((ln.strip()[:200] for ln in log.splitlines() if "error" in ln), "")}
        else:
            res[th] = {"module": mod, "build_ok": True, "axioms": ax, "tier": tier_of(ax)}
    ver = subprocess.run([str(Path(lp).parent / "lean"), "--version"], capture_output=True, text=True, env=_env())
    return {"build_ok": ok, "lean_version": ver.stdout.strip(), "log_sha256": sha_text(log), "theorems": res}


# ---- the record ------------------------------------------------------------------------------------------
def record_path(project: str = DEFAULT_PROJECT) -> Path:
    return ROOT / project / "records" / "build_record.json"


def load_record(project: str = DEFAULT_PROJECT) -> dict | None:
    p = record_path(project)
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except (OSError, json.JSONDecodeError):
        return None


def lean_items(plans: list[dict]) -> list[dict]:
    return [it for pl in plans for it in pl["verification"] if it.get("method") == "formal_lean"]


def write_record(items: list[dict], project: str = DEFAULT_PROJECT) -> Path:
    """Build (needs the toolchain) and write the record for every formal_lean item of ``items`` that lives in ``project``."""
    mine = [i for i in items if (i.get("lean") or {}).get("project", DEFAULT_PROJECT) == project]
    pairs = sorted({(i["lean"]["module"], i["lean"]["theorem"]) for i in mine})
    b = build_live(project, pairs)
    th: dict[str, Any] = {}
    for mod, name in pairs:
        f = frozen(project, mod, name) or {}
        e = b["theorems"][name]
        th[name] = {"module": mod, "build_ok": e["build_ok"], "axioms": e["axioms"], "tier": e["tier"], "statement_sha256": f.get("statement_sha256"),
                    "definitions_sha256": f.get("definitions_sha256")}
        if e.get("first_error"):
            th[name]["first_error"] = e["first_error"]
    srcs: dict[str, Any] = {}
    for i in mine:
        for s in (i.get("rtl_link") or {}).get("source") or []:
            srcs[source_key(s)] = source_hash(s)
    rec = {"schema": RECORD_SCHEMA, "toolchain": (ROOT / project / "lean-toolchain").read_text().strip(), "lean_version": b["lean_version"],
           "build_ok": b["build_ok"], "build_log_sha256": b["log_sha256"], "files": project_files(project), "theorems": th, "rtl_sources": srcs,
           "how": "python -m flow.trace_v1 lean-record; the build ran `lake build` in a scratch copy with `#print axioms` appended",
           "note": "A record is evidence that a build succeeded at these file hashes. CI without Lean reads it and shows the status as a recorded build, never as a re-run."}
    p = record_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    return p


# ---- approvals: a human's act ----------------------------------------------------------------------------
def approvals_path(design: Path) -> Path:
    return design / "verif" / "lean_approvals.yaml"


def load_approvals(design: Path) -> dict[str, dict]:
    """item id -> approval entry. The file is edited by the owner only; nothing in this repository writes it."""
    p = approvals_path(design)
    if not p.exists():
        return {}
    raw = yaml.safe_load(p.read_text()) or {}
    return {a["item"]: a for a in raw.get("approvals") or [] if isinstance(a, dict) and a.get("item")}


def approval_problems(design: Path, item_ids: set[str], items: dict[str, dict]) -> list[str]:
    """Structural problems with the approvals file (gate failures): an entry for an unknown item, a missing field, or an approver that is not a
    human. An approval is never inferred, so an agent cannot set one by editing the testplan: `approved_by` in the plan itself is refused."""
    p = approvals_path(design)
    out: list[str] = []
    if p.exists():
        raw = yaml.safe_load(p.read_text()) or {}
        if raw.get("schema") != APPROVAL_SCHEMA:
            out.append(f"{p.name}: schema must be {APPROVAL_SCHEMA}")
        for a in raw.get("approvals") or []:
            iid = a.get("item") if isinstance(a, dict) else None
            if iid not in item_ids:
                out.append(f"{p.name}: approval for unknown item {iid!r}")
                continue
            for k in ("theorem", "statement_sha256", "definitions_sha256", "approved_by", "approver_kind", "date"):
                if not a.get(k):
                    out.append(f"{p.name}: approval of {iid} lacks {k}")
            if a.get("approver_kind") != "human":
                out.append(f"{p.name}: approval of {iid}: approver_kind must be human (only a human approves a statement)")
            if a.get("theorem") and a["theorem"] != (items[iid].get("lean") or {}).get("theorem"):
                out.append(f"{p.name}: approval of {iid} names a different theorem than the item")
    for iid, it in items.items():
        for k in ("approved_by", "approver_kind", "approval", "statement_approved", "approved"):
            if k in it or k in (it.get("lean") or {}):
                out.append(f"{iid}: `{k}` in the testplan is refused: approvals live in verif/lean_approvals.yaml and are written by a human")
    return out


# ---- the item's problems (gate) ---------------------------------------------------------------------------
def item_problems(item: dict, approvals: dict[str, dict]) -> list[str]:
    out: list[str] = []
    lean = item.get("lean")
    if not isinstance(lean, dict) or not lean.get("module") or not lean.get("theorem"):
        return ["a formal_lean item needs `lean: {module, theorem}` (project defaults to formal/lean)"]
    project = lean.get("project", DEFAULT_PROJECT)
    f = frozen(project, lean["module"], lean["theorem"])
    if f is None:
        out.append(f"theorem {lean['theorem']} not found in module {lean['module']} of {project}")
    link = item.get("rtl_link")
    if not isinstance(link, dict) or link.get("kind") not in RTL_LINKS:
        out.append(f"a formal_lean item needs `rtl_link: {{kind: one of {', '.join(RTL_LINKS)}}}`")
        return out
    kind = link["kind"]
    srcs = link.get("source") or []
    if kind != "model_only" and not srcs:
        out.append(f"rtl_link {kind} must name the RTL it is about: `source: [{{file, lines, commit?}}]`")
    for s in srcs:
        if not isinstance(s, dict) or not s.get("file") or not re.fullmatch(r"\d+-\d+", str(s.get("lines", ""))):
            out.append("each rtl_link source needs `file` and `lines: A-B`")
        elif not s.get("commit") and source_hash(s) is None:          # a commit-pinned source is pinned in the record (CI's checkout may lack the object)
            out.append(f"rtl_link source {source_key(s)} cannot be read (file, line range or commit)")
    if kind in ("transcription_tested", "transcription_untested") and not link.get("transcribed_in"):
        out.append(f"rtl_link {kind} must name the Lean file or definitions that hold the transcription (`transcribed_in`)")
    if kind == "transcription_tested":
        cc = link.get("crosscheck") or {}
        if not cc.get("file") or not (ROOT / cc["file"]).exists():
            out.append("rtl_link transcription_tested needs `crosscheck: {file, reference}` naming an existing cross-check file")
        elif not cc.get("reference"):
            out.append("rtl_link transcription_tested: the cross-check must name the independent reference it compares with (`crosscheck.reference`)")
    if kind == "rtl_generated" and not link.get("generator"):
        out.append("rtl_link rtl_generated must name the generator tool (`generator`)")
    ap = approvals.get(item["id"])
    if ap and f is not None and (ap.get("statement_sha256") != f["statement_sha256"] or ap.get("definitions_sha256") != f["definitions_sha256"]):
        which = "statement" if ap.get("statement_sha256") != f["statement_sha256"] else "definitions"
        out.append(f"frozen {which} of {lean['theorem']} changed since {ap.get('approved_by')} approved it on {ap.get('date')}: "
                   "the statement is the specification; restore it or ask for a new approval")
    return out


# ---- judging an item -------------------------------------------------------------------------------------
def judge_lean(item: dict, design: Path, mode: str, cache: dict) -> dict[str, Any]:
    """Pass / fail / not_run / stale / unapproved for one formal_lean item. ``mode``: ``recorded`` (the committed record only; what committed
    matrices use), ``live`` (run lake build; an error without the toolchain) or ``auto`` (live when the toolchain is present)."""
    lean = item.get("lean") or {}
    link = item.get("rtl_link") or {}
    project, module, theorem = lean.get("project", DEFAULT_PROJECT), lean.get("module"), lean.get("theorem")
    res: dict[str, Any] = {"id": item["id"], "method": "formal_lean", "title": item.get("title", ""), "status": "not_run", "value": None, "detail": "",
                           "evidence": None, "instrument": None, "planned": item.get("planned")}
    li: dict[str, Any] = {"theorem": theorem, "module": module, "project": project, "rtl_link": link.get("kind"),
                          "rtl_link_text": RTL_LINK_TEXT.get(link.get("kind", ""), "no RTL link recorded"), "build_source": None, "tier": None,
                          "approved": False, "approved_by": None, "approved_on": None, "statement_sha256": None}
    res["lean"] = li
    rp = record_path(project)
    rec = load_record(project)
    if rec is not None:
        res["evidence"] = {"file": rp.relative_to(ROOT).as_posix(), "exists": True}
    f = frozen(project, module, theorem) if module and theorem else None
    if f is None:
        res.update(status="fail", detail=f"theorem {theorem} not found in module {module}")
        return res
    li["statement_sha256"] = f["statement_sha256"]
    use_live = mode == "live" or (mode == "auto" and toolchain_available())
    if mode == "live" and not toolchain_available():
        res.update(status="not_run", detail="live build requested but the Lean toolchain is not installed")
        return res
    entry = None
    if use_live:
        b = cache.get(("lean_live", project))
        if b is None:
            b = cache[("lean_live", project)] = _live_all(project, cache)
        entry = (b["theorems"] or {}).get(theorem)
        li["build_source"] = "lake build (live)"
    elif rec is not None:
        entry = (rec.get("theorems") or {}).get(theorem)
        li["build_source"] = "recorded build (not re-run)"
    if entry is None:
        planned = f" (planned: {item['planned']})" if item.get("planned") else ""
        res.update(status="not_run", detail=("no recorded build for this theorem; run `python -m flow.trace_v1 lean-record`" if rec is not None or not use_live else
                                              "the theorem was not built") + planned)
        li["build_source"] = li["build_source"] or "none"
        return res
    li["tier"], li["axioms"] = entry.get("tier"), entry.get("axioms")
    # staleness against the record (the record is what a no-toolchain reader trusts; in a live run only the transcribed RTL is compared)
    stale: list[str] = []
    if rec is not None:
        if not use_live:
            now = project_files(project)
            changed = sorted(k for k in set(now) | set(rec.get("files") or {}) if now.get(k) != (rec.get("files") or {}).get(k))
            if changed:
                stale.append("Lean files changed since the recorded build: " + ", ".join(changed[:4]) + (f" (+{len(changed) - 4} more)" if len(changed) > 4 else ""))
            re_ = (rec.get("theorems") or {}).get(theorem) or {}
            if re_.get("statement_sha256") and re_["statement_sha256"] != f["statement_sha256"]:
                stale.append("the statement changed since the recorded build")
        for s in link.get("source") or []:
            k = source_key(s)
            had = (rec.get("rtl_sources") or {}).get(k)
            nowh = source_hash(s)
            if had is None:
                stale.append(f"the record does not pin transcribed RTL {k}")
            elif nowh is not None and nowh != had:
                stale.append(f"transcribed RTL lines changed since the record: {k}")
    elif not use_live:
        stale.append("no build record")
    if not entry.get("build_ok"):
        res.update(status="fail", detail="the Lean build failed" + (f": {entry.get('first_error')}" if entry.get("first_error") else ""))
        return res
    if entry.get("tier") == "unsound":
        res.update(status="fail", detail="the axiom audit failed: the proof depends on " + ", ".join(entry.get("axioms") or []))
        return res
    ap = load_approvals(design).get(item["id"])
    if ap:
        li.update(approved_by=ap.get("approved_by"), approved_on=str(ap.get("date")))
        if ap.get("statement_sha256") != f["statement_sha256"] or ap.get("definitions_sha256") != f["definitions_sha256"]:
            res.update(status="fail", detail="the frozen statement (or the definitions it rests on) changed since it was approved")
            return res
        li["approved"] = True
    base = (f"{theorem}: {TIER_TEXT[entry['tier']]}; {li['rtl_link_text']}; {li['build_source']}")
    if stale:
        res.update(status="stale", detail=base, stale_because="; ".join(stale))
        return res
    if not li["approved"]:
        res.update(status="unapproved", detail=f"statement not approved; {base}")
        return res
    res.update(status="pass", detail=f"statement approved by {li['approved_by']} on {li['approved_on']}; {base}")
    return res


def _live_all(project: str, cache: dict) -> dict[str, Any]:
    pairs = sorted(cache.get(("lean_pairs", project)) or [])
    return build_live(project, pairs)


def prime(plan: dict, cache: dict) -> None:
    """Tell the cache every (module, theorem) of the plan so one live build covers them all."""
    for it in plan["verification"]:
        if it.get("method") == "formal_lean" and isinstance(it.get("lean"), dict) and it["lean"].get("module"):
            cache.setdefault(("lean_pairs", it["lean"].get("project", DEFAULT_PROJECT)), set()).add((it["lean"]["module"], it["lean"]["theorem"]))


def statement_report(design: Path, item: dict) -> str:
    """What a human reads before approving: the statement, the definitions it rests on, and the two hashes. Writes nothing."""
    lean = item["lean"]
    f = frozen(lean.get("project", DEFAULT_PROJECT), lean["module"], lean["theorem"])
    if f is None:
        return f"theorem {lean['theorem']} not found"
    return "\n".join([f"item {item['id']}: {lean['theorem']} in {lean['module']}", "", "STATEMENT (comments removed, whitespace normalised):", f["statement"], "",
                      "DEFINITIONS the statement rests on (every def and abbrev of the module):", *f["definitions"], "",
                      f"statement_sha256:   {f['statement_sha256']}", f"definitions_sha256: {f['definitions_sha256']}", "",
                      f"To approve, the owner adds an entry to {approvals_path(design).relative_to(ROOT).as_posix()} with item, theorem, both hashes,",
                      "approved_by, approver_kind: human and date. Nothing in this repository writes that file."])
