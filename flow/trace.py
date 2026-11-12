#!/usr/bin/env python3
"""Requirements traceability matrix and its gates (brief 53): requirement -> design element -> test or proof -> result
-> coverage, with DO-254-style evidence checks. It is evidence of a process, not a claim of compliance with any standard.

    python3 flow/trace.py designs/t1_dimmer_counter --runs build/verif/verilator [--also build/verif/icarus]
        [--coverage build/verif/verilator] [--formal build/verif/formal] [--gates build/base/gates.json]
        [--hw results/f0b/t1_dimmer_counter_bringup.json] [--baseline old/trace.json] [--defer hardware,analysis]
        [--json build/trace/trace.json] [--md build/trace/trace.md]

Reads:

- ``spec.yaml`` ``requirements: [{id, text, proof: [simulation|formal|hardware|analysis]}]``;
- the **tags** on every test and property, read from the source (no simulation needed):
  - cocotb tests: ``@req("REQ-01", ...)`` (flow/req.py) or a ``# req: REQ-01`` comment directly above the test;
    ``robustness=``/``structural=`` (or ``# robustness: <reason>``) for a test that verifies no requirement;
  - SVA assertions and cover properties (`` `V_SAME/V_NEXT/V_RST/V_COVER(NAME, ...)``): a ``// req: REQ-01`` comment
    on the macro's line or on the comment lines directly above it (``// robustness: ...``, ``// structural: ...``);
  - SymbiYosys jobs: a ``# req: REQ-01`` line anywhere in the ``.sby`` file;
  - RTL (the design-element column): ``// req: REQ-01`` inside a module names that module as implementing it;
    checkers bound into a module (``bind <module> <checker>``) add that module for the requirements they cite;
- ``verif/testplan.yaml``: the ``proof:`` list (artefacts for analysis and hardware, and any simulation or formal
  artefact named there), ``replan:``, ``waivers:`` and the planned functional bins;
- ``verif/justifications.yaml`` (optional): coverage-hole justifications and re-confirmations, each with owner, reason
  and date; ``lint/waivers.yaml`` (flow/lint_ruleset.py) and inline ``// std-waive:`` comments are checked too;
- the run records: every seed's ``results.xml``; ``coverage*.dat`` and ``coverage*.yml``; SymbiYosys ``status``
  files; the build's ``gates.json``; the bring-up JSON.

Gates (each fails with the ids it is missing):

- ``requirements_verified``: every requirement has at least one passing verification of each method it states
  (simulation: a passing test on every seed; formal: a job whose tasks all PASS; analysis: the named flow gate true;
  hardware: the named bring-up step passed). A method listed in ``--defer`` may be ``pending`` (its evidence comes from
  a later stage); a fail never passes.
- ``artefacts_cite_requirements``: every test, assertion, cover property and formal job cites at least one known
  requirement, or is marked ``robustness`` or ``structural`` with a reason.
- ``coverage_holes_justified``: every unhit line, branch, toggle point, planned functional bin and cover property is
  either closed or matches a justification (testplan waiver or ``verif/justifications.yaml``; ``item`` is a glob with
  literal brackets, or ``re:<regex>``).
- ``waivers_complete``: every waiver and justification has an owner, a reason and a date (YYYY-MM-DD).
- ``changed_requirements_reverified`` (with ``--baseline``): a requirement whose text changed since the baseline while
  its evidence did not is stale until re-confirmed.
"""

from __future__ import annotations

import argparse
import ast
import datetime as _dt
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    from flow import change_record as cr
    from flow import verif_gates as vg
except ImportError:                                  # run as a script: flow/ itself is on sys.path
    import change_record as cr                       # type: ignore[no-redef]
    import verif_gates as vg                         # type: ignore[no-redef]

ROOT = vg.ROOT
SCHEMA = "fpga-design-agent/trace/v1"
CLASSES = ("robustness", "structural")
MIN_REASON = 8                                        # characters: "n/a" is not a reason
GATES = ("requirements_verified", "artefacts_cite_requirements", "coverage_holes_justified", "waivers_complete",
         "changed_requirements_reverified")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BARE_ID = re.compile(r"\bREQ-[A-Za-z0-9_.]*[A-Za-z0-9_]")
_TAG = re.compile(r"\b(req|robustness|structural)\s*:\s*(.*)$", re.I)
_MACRO = re.compile(r"`V_(SAME|NEXT|RST|COVER)\s*\(\s*(\w+)\s*,")


# ---- tags ---------------------------------------------------------------------------------------------------------
def _parse_tag_text(texts: list[str], known: set[str]) -> dict[str, Any]:
    """Tags from comment texts (without the comment marker). ``req:`` lists ids; bare ``REQ-xx`` tokens and known
    ids in a ``req:`` line count; ``robustness:``/``structural:`` carry the reason."""
    ids: list[str] = []
    cls = reason = None
    for t in texts:
        m = _TAG.search(t)
        if m:
            kind, rest = m.group(1).lower(), m.group(2).strip()
            if kind == "req":
                ids += [x for x in re.split(r"[\s,;]+", rest.split("(")[0]) if x]
                continue
            cls, reason = kind, rest
            continue
        ids += _BARE_ID.findall(t)
    seen: list[str] = []
    for i in ids:
        i = i.strip().rstrip(".")
        if i and i not in seen:
            seen.append(i)
    return {"cites": seen, "class": cls, "reason": reason}


def _comment_block_above(lines: list[str], idx: int, marker: str) -> list[str]:
    """Comment lines directly above line ``idx`` (0-based), nearest last; stops at the first non-comment line."""
    out = []
    j = idx - 1
    while j >= 0 and lines[j].strip().startswith(marker):
        out.insert(0, lines[j].strip()[len(marker):].strip())
        j -= 1
    return out


def _is_cocotb_test(dec: ast.expr) -> bool:
    node = dec.func if isinstance(dec, ast.Call) else dec
    return (isinstance(node, ast.Attribute) and node.attr == "test" and isinstance(node.value, ast.Name)
            and node.value.id == "cocotb")


def _req_decorator(dec: ast.expr) -> dict[str, Any] | None:
    if not isinstance(dec, ast.Call):
        return None
    f = dec.func
    name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
    if name != "req":
        return None
    ids = [a.value for a in dec.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    cls = reason = None
    for kw in dec.keywords:
        if kw.arg in CLASSES and isinstance(kw.value, ast.Constant) and kw.value.value:
            cls, reason = kw.arg, str(kw.value.value)
    return {"cites": ids, "class": cls, "reason": reason}


def bench_artefacts(bench_dir: Path, modules: list[str], known: set[str]) -> list[dict[str, Any]]:
    """Every cocotb test of the bench modules with its tags (``module.test`` names, as the results use)."""
    out = []
    for m in modules:
        f = bench_dir / f"{m}.py"
        try:
            src = f.read_text()
            tree = ast.parse(src)
        except (OSError, SyntaxError):
            continue
        lines = src.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            if not any(_is_cocotb_test(d) for d in node.decorator_list):
                continue
            first = min([d.lineno for d in node.decorator_list] + [node.lineno]) - 1
            texts = _comment_block_above(lines, first, "#")
            texts += [l.strip()[1:].strip() for l in lines[first:node.lineno - 1] if l.strip().startswith("#")]
            tag = _parse_tag_text(texts, known)
            for d in node.decorator_list:
                rd = _req_decorator(d)
                if rd:
                    tag["cites"] += [i for i in rd["cites"] if i not in tag["cites"]]
                    if rd["class"]:
                        tag["class"], tag["reason"] = rd["class"], rd["reason"]
            body = "\n".join(lines[first:getattr(node, "end_lineno", node.lineno)])
            out.append({"kind": "test", "name": f"{m}.{node.name}", "file": cr._rel(f), "line": node.lineno,
                        "source_sha256": cr.sha256_text(body), **tag})
    return out


def checker_artefacts(chk_dir: Path, known: set[str]) -> list[dict[str, Any]]:
    """Every `V_*(NAME, ...)` assertion and cover property in the checker files, with its tags and its checker module."""
    out = []
    for f in sorted(chk_dir.glob("*.sv")):
        try:
            lines = f.read_text().splitlines()
        except OSError:
            continue
        module = None
        for i, l in enumerate(lines):
            mm = re.match(r"\s*module\s+(\w+)", l)
            if mm:
                module = mm.group(1)
            for m in _MACRO.finditer(l.split("//", 1)[0]):
                texts = _comment_block_above(lines, i, "//")
                if "//" in l:
                    texts.append(l.split("//", 1)[1])
                kind = "cover" if m.group(1) == "COVER" else "assertion"
                out.append({"kind": kind, "name": m.group(2), "file": cr._rel(f), "line": i + 1, "checker": module,
                            "source_sha256": cr.sha256_text(l.strip()), **_parse_tag_text(texts, known)})
    return out


def formal_artefacts(formal_src: Path, known: set[str]) -> list[dict[str, Any]]:
    out = []
    for f in sorted(formal_src.glob("*.sby")):
        try:
            text = f.read_text()
        except OSError:
            continue
        texts = [l.strip()[1:].strip() for l in text.splitlines() if l.strip().startswith("#")]
        out.append({"kind": "formal", "name": f.stem, "file": cr._rel(f), "line": 1,
                    "source_sha256": cr.sha256_text(text), **_parse_tag_text(texts, known)})
    return out


def rtl_elements(rtl_files: list[Path], chk_dir: Path, known: set[str]) -> tuple[dict[str, set[str]], dict[str, str]]:
    """``(req -> modules tagged in RTL, checker module -> bound target module)``."""
    by_req: dict[str, set[str]] = {}
    for f in rtl_files:
        try:
            lines = f.read_text().splitlines()
        except OSError:
            continue
        module, pending = None, []                  # tags in a header comment apply to the next module
        for l in lines:
            mm = re.match(r"\s*module\s+(\w+)", l)
            if mm:
                module = mm.group(1)
                for i in pending:
                    by_req.setdefault(i, set()).add(module)
                pending = []
            if "//" in l:
                tag = _parse_tag_text([l.split("//", 1)[1]], known)
                if not re.search(r"\breq\s*:", l, re.I):
                    continue                            # only an explicit `req:` tag names a design element
                if module:
                    for i in tag["cites"]:
                        by_req.setdefault(i, set()).add(module)
                else:
                    pending += tag["cites"]
    binds: dict[str, str] = {}
    for f in chk_dir.glob("*.sv"):
        try:
            text = re.sub(r"//[^\n]*", "", f.read_text())
        except OSError:
            continue
        for m in re.finditer(r"\bbind\s+(\w+)\s+(\w+)", text):
            binds[m.group(2)] = m.group(1)
    return by_req, binds


# ---- justifications and waivers -----------------------------------------------------------------------------------
def load_justifications(design: Path) -> dict[str, Any]:
    p = design / "verif" / "justifications.yaml"
    if not p.is_file():
        return {}
    try:
        j = yaml.safe_load(p.read_text()) or {}
    except yaml.YAMLError as e:
        raise vg.PlanError(f"verif/justifications.yaml is not valid YAML: {' '.join(str(e).split())}")
    return j if isinstance(j, dict) else {}


def _waiver_problem(w: Any) -> str | None:
    if not isinstance(w, dict):
        return "not a mapping"
    miss = []
    if len(str(w.get("reason") or "").strip()) < MIN_REASON:
        miss.append("reason")
    if not str(w.get("owner") or "").strip():
        miss.append("owner")
    d = w.get("date")
    if isinstance(d, (_dt.date, _dt.datetime)):
        d = d.isoformat()[:10]
    if not (isinstance(d, str) and _DATE.match(d)):
        miss.append("date (YYYY-MM-DD)")
    return ("no " + ", no ".join(miss)) if miss else None


def inline_waivers(rtl_files: list[Path]) -> list[dict[str, Any]]:
    """``// std-waive: RULE reason [owner: X; date: YYYY-MM-DD]`` comments in the RTL (flow/standards_check.py)."""
    out = []
    for f in rtl_files:
        try:
            lines = f.read_text().splitlines()
        except OSError:
            continue
        for i, l in enumerate(lines):
            m = re.search(r"//\s*std-waive:\s*(\S+)\s*(.*)", l)
            if not m:
                continue
            rest = m.group(2)
            meta = dict(re.findall(r"(owner|date)\s*[:=]\s*([^;\]]+)", rest))
            reason = re.sub(r"\[[^\]]*\]", "", rest).strip()
            out.append({"where": f"{cr._rel(f)}:{i + 1}", "rule": m.group(1), "reason": reason,
                        "owner": meta.get("owner", "").strip(), "date": meta.get("date", "").strip()})
    return out


def all_waivers(design: Path, plan: dict, just: dict, rtl_files: list[Path]) -> list[dict[str, Any]]:
    """Every waiver and justification the evidence relies on, with where it lives."""
    out = []
    for cat, ws in (plan.get("waivers") or {}).items():
        for w in ws or []:
            out.append({"where": f"testplan waivers.{cat}", "item": (w or {}).get("item") if isinstance(w, dict) else w, "w": w})
    for k in ("coverage", "reconfirmed"):
        for w in just.get(k) or []:
            out.append({"where": f"justifications.{k}", "item": (w or {}).get("item") or (w or {}).get("requirement")
                        if isinstance(w, dict) else w, "w": w})
    lw = design / "lint" / "waivers.yaml"
    if lw.is_file():
        try:
            lws = (yaml.safe_load(lw.read_text()) or {}).get("waivers") or []
        except (yaml.YAMLError, AttributeError):
            lws = ["lint/waivers.yaml is not valid"]
        for w in lws:
            out.append({"where": "lint/waivers.yaml", "item": (w or {}).get("rule") if isinstance(w, dict) else w, "w": w})
    for w in inline_waivers(rtl_files):
        out.append({"where": w["where"], "item": w["rule"], "w": w})
    for o in out:
        o["problem"] = _waiver_problem(o.pop("w"))
    return out


# ---- coverage holes -----------------------------------------------------------------------------------------------
def match_item(item: str, pat: str) -> bool:
    """A justification or waiver pattern: ``re:<regex>`` (full match), else a glob in which only ``*`` and ``?`` are
    wildcards (brackets are literal, so ``count[3]`` means that bit)."""
    if pat.startswith("re:"):
        try:
            return re.fullmatch(pat[3:], item) is not None
        except re.error:
            return False
    rx = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pat)
    return re.fullmatch(rx, item) is not None



_WAIVER_KINDS = {"code_coverage": ("line", "branch", "toggle"), "functional_bins": ("bin",), "cover_properties": ("cover",)}


def coverage_holes(plan: dict, design: Path, cov_dir: Path | None, covers: list[dict]) -> dict[str, Any]:
    """Unhit points of the design RTL (line, branch, toggle), planned functional bins and cover properties."""
    if not cov_dir or not list(cov_dir.glob("seed*/coverage*")):
        return {"measured": False, "summary": {}, "holes": [], "cover_hits": {}}
    rtl_rel = plan.get("design_rtl") or (f"{design.relative_to(ROOT).as_posix()}/rtl/" if design.is_relative_to(ROOT)
                                          else f"{design.name}/rtl/")
    code = vg.merge_code_cov(cov_dir, rtl_rel) if list(cov_dir.glob("seed*/coverage*.dat")) else {}
    holes = []
    summary = {}
    for typ in ("line", "branch", "toggle"):
        c = code.get(typ) or {}
        summary[typ] = {k: c.get(k) for k in ("points", "hit", "pct")}
        holes += [{"kind": typ, "item": u} for u in c.get("unhit") or []]
    func = vg.merge_func_cov(cov_dir)
    planned = sorted({b for r in plan.get("requirements") or [] for b in (r.get("bins") or [])})
    tot = hit = 0
    for g in planned:
        for b, n in (func.get(g) or {}).items():
            tot += 1
            hit += n > 0
            if n == 0:
                holes.append({"kind": "bin", "item": f"{g}:{b}"})
    summary["bins"] = {"points": tot, "hit": hit, "pct": round(100 * hit / tot, 2) if tot else None}
    user = code.get("user") or {}
    hits = {c["name"]: sum(v for k, v in user.items() if c["name"] in k) for c in covers}
    if code:
        holes += [{"kind": "cover", "item": n} for n, h in sorted(hits.items()) if h == 0]
        summary["cover"] = {"points": len(hits), "hit": sum(1 for h in hits.values() if h), "pct":
                            round(100 * sum(1 for h in hits.values() if h) / len(hits), 2) if hits else None}
    no_points = bool(code) and not any((code.get(t) or {}).get("points") for t in ("line", "branch", "toggle"))
    return {"measured": bool(code) or bool(func), "summary": summary, "holes": holes, "cover_hits": hits if code else {},
            "rtl_rel": rtl_rel, "no_rtl_points": no_points}


def justify(holes: list[dict], plan: dict, just: dict) -> list[dict]:
    """Attach the matching justification (glob on ``item``, same kind) to each hole; ``justified_by`` None if none."""
    rules: list[tuple[str | None, str, str, str]] = []          # (kind or None, pattern, where, reason)
    for cat, kinds in _WAIVER_KINDS.items():
        for w in (plan.get("waivers") or {}).get(cat) or []:
            if isinstance(w, dict) and w.get("item"):
                for k in kinds:
                    rules.append((k, str(w["item"]), f"testplan waivers.{cat}", str(w.get("reason", ""))))
    for w in just.get("coverage") or []:
        if isinstance(w, dict) and w.get("item"):
            rules.append((w.get("kind"), str(w["item"]), "justifications.coverage", str(w.get("reason", ""))))
    for h in holes:
        h["justified_by"] = None
        for k, pat, where, reason in rules:
            if (k is None or k == h["kind"]) and match_item(h["item"], pat):
                h["justified_by"] = {"where": where, "item": pat, "reason": reason}
                break
    return holes


# ---- results ------------------------------------------------------------------------------------------------------
def test_result(name: str, res: dict[int, dict[str, bool]], also: dict[str, dict[int, dict[str, bool]]]) -> dict[str, Any]:
    if not res:
        return {"result": "pending", "detail": "no simulation results"}
    bad = [f"seed{s}" for s, tt in sorted(res.items()) if not tt.get(name, False)]
    cross = {}
    for sim, r2 in also.items():
        if r2:
            cross[sim] = "pass" if all(tt.get(name, False) for tt in r2.values()) else "fail"
    out = {"result": "fail" if bad else "pass",
           "detail": ("failed or missing on " + ", ".join(bad)) if bad else f"passed on {len(res)} seed(s)"}
    if cross:
        out["cross_check"] = cross
    return out


def formal_result(job: str, fr: dict[str, str]) -> dict[str, Any]:
    tasks = {k[len(job) + 1:]: v for k, v in fr.items() if k.startswith(job + "_")}
    if not fr:
        return {"result": "pending", "detail": "no formal results"}
    if not tasks:
        return {"result": "fail", "detail": "no task of this job ran"}
    ok = all(v == "PASS" for v in tasks.values())
    return {"result": "pass" if ok else "fail", "detail": ", ".join(f"{k}={v}" for k, v in sorted(tasks.items()))}


# ---- the matrix ---------------------------------------------------------------------------------------------------
def build(design: Path, runs: Path | None, also: list[Path] | None = None, coverage: Path | None = None,
          formal: Path | None = None, gates: Path | None = None, hw: Path | None = None, baseline: Path | None = None,
          defer: tuple[str, ...] = (), build_dir: Path | None = None) -> dict[str, Any]:
    """The traceability matrix and its gates for one design. Raises :class:`flow.verif_gates.PlanError` on an input that
    cannot be read (``main`` turns it into a failed gate)."""
    plan_path = design / "verif" / "testplan.yaml"
    plan, spec = vg.load_inputs(design, plan_path)
    just = load_justifications(design)
    spec_reqs = [r for r in (spec.get("requirements") or []) if isinstance(r, dict) and r.get("id")]
    known = {str(r["id"]) for r in spec_reqs}
    bench_dir = vg.plan_file(design, plan["bench"]["dir"])
    chk_dir = vg.plan_file(design, plan["checkers"])
    formal_src = vg.plan_file(design, plan["formal_dir"])
    rtl_files = sorted((design / "rtl").glob("*.sv")) + sorted((design / "rtl").glob("*.v"))

    arts = (bench_artefacts(bench_dir, plan["bench"]["modules"], known) + checker_artefacts(chk_dir, known)
            + formal_artefacts(formal_src, known))
    res = vg.read_results([runs]) if runs else {}
    also_res = {d.name: vg.read_results([d]) for d in (also or [])}
    fr = vg.read_formal(formal) if formal else {}
    cov = coverage_holes(plan, design, coverage or runs, [a for a in arts if a["kind"] == "cover"])
    failing_any = any(not ok for tt in res.values() for ok in tt.values())
    for a in arts:
        if a["kind"] == "test":
            a.update(test_result(a["name"], res, also_res))
        elif a["kind"] == "formal":
            a.update(formal_result(a["name"], fr))
        elif a["kind"] == "cover":
            h = cov["cover_hits"].get(a["name"])
            a.update({"result": "pending", "detail": "no coverage data"} if h is None else
                     {"result": "pass" if h else "fail", "detail": f"hit {h} time(s) over all seeds"})
        else:
            a.update({"result": "pending", "detail": "no simulation results"} if not res else
                     {"result": "fail" if failing_any else "pass",
                      "detail": "a test failed in some seed: the assertion may be the cause" if failing_any else
                                f"bound in {len(res)} seed(s), no failure"})
    by_name = {(a["kind"], a["name"]): a for a in arts}

    # proof-list entries (analysis, hardware, and any simulation/formal artefact the testplan names)
    entries = [e for e in (plan.get("proof") or []) if isinstance(e, dict)]
    re_entries, _bad = vg.replan_entries(plan, spec_reqs)
    gates_json = json.loads(gates.read_text()) if gates and gates.exists() else None
    hw_json = json.loads(hw.read_text()) if hw and hw.exists() else None
    elems, binds = rtl_elements(rtl_files, chk_dir, known)

    rows = []
    for r in spec_reqs:
        rid = str(r["id"])
        cites = [a for a in arts if rid in a["cites"]]
        methods = []
        for m in r.get("proof") or []:
            ver: list[dict[str, Any]] = []
            if m == "simulation":
                for a in cites:
                    if a["kind"] == "test":
                        ver.append({"artefact": a["name"], "via": "tag", "result": a["result"], "detail": a["detail"]})
                for e in entries:
                    if e.get("requirement") == rid and e.get("method") == m and not any(v["artefact"] == e.get("artefact") for v in ver):
                        a = by_name.get(("test", str(e.get("artefact"))))
                        ver.append({"artefact": str(e.get("artefact")), "via": "testplan proof",
                                    "result": a["result"] if a else "fail",
                                    "detail": a["detail"] if a else "named in the testplan proof list but not a test in the bench"})
            elif m == "formal":
                for a in cites:
                    if a["kind"] == "formal":
                        ver.append({"artefact": a["name"], "via": "tag", "result": a["result"], "detail": a["detail"]})
                for e in entries + re_entries:
                    if e.get("requirement") != rid or e.get("method") != "formal" or any(v["artefact"] == e.get("artefact") for v in ver):
                        continue
                    rp = e.get("replan")
                    if rp:
                        a = by_name.get(("test", str(e["artefact"]))) if rp["to"] == "simulation" else None
                        row = vg.trace_table([r], [e], res, fr, gates_json, hw_json)
                        resu = a["result"] if a else (row[0]["result"] if row else "fail")
                        ver.append({"artefact": str(e["artefact"]), "via": f"replan formal->{rp['to']}", "result": resu,
                                    "detail": f"re-planned ({rp['why']})"})
                    else:
                        a = by_name.get(("formal", str(e.get("artefact"))))
                        ver.append({"artefact": str(e.get("artefact")), "via": "testplan proof",
                                    "result": a["result"] if a else "fail",
                                    "detail": a["detail"] if a else "named in the testplan proof list but no such .sby job"})
            else:                                           # analysis, hardware: flow gates and bring-up steps
                es = [e for e in entries if e.get("requirement") == rid and e.get("method") == m and e.get("artefact")]
                for row in vg.trace_table([{"id": rid, "proof": [m]}], es, res, fr, gates_json, hw_json):
                    if row["artefact"] != "-":
                        ver.append({"artefact": row["artefact"], "via": "testplan proof", "result": row["result"],
                                    "detail": row["detail"]})
            if any(v["result"] == "pass" for v in ver):
                status = "pass"
            elif not ver:
                status = "missing"
            elif all(v["result"] == "pending" for v in ver):
                status = "pending"
            else:
                status = "fail"
            methods.append({"method": m, "status": status, "verifications": ver})
        support = [{"kind": a["kind"], "name": a["name"], "result": a["result"], "detail": a["detail"]}
                   for a in cites if a["kind"] in ("assertion", "cover")]
        modules = set(elems.get(rid, set()))
        for a in cites:
            if a.get("checker") in binds:
                modules.add(binds[a["checker"]])
        cov_props = [a for a in cites if a["kind"] == "cover"]
        ev_items = [{"kind": a["kind"], "name": a["name"], "source_sha256": a["source_sha256"], "result": a["result"]}
                    for a in cites] + [{"kind": "proof", "name": v["artefact"], "source_sha256": "", "result": v["result"]}
                                       for mm in methods for v in mm["verifications"] if v["via"] != "tag"]
        rows.append({"id": rid, "text": r.get("text", ""), "proof": list(r.get("proof") or []),
                     "design_elements": sorted(modules), "methods": methods, "supporting": support,
                     "coverage": {"cover_properties": len(cov_props),
                                  "cover_properties_hit": sum(1 for a in cov_props if a["result"] == "pass")},
                     "req_hash": cr.req_hash(r), "evidence_hash": cr.evidence_hash(ev_items),
                     "status": ("pass" if methods and all(mm["status"] == "pass" for mm in methods) else
                                "fail" if any(mm["status"] in ("fail", "missing") for mm in methods) or not methods else "pending")})

    # ---- gates
    defer = tuple(defer)
    not_verified = [f"{row['id']}:{mm['method']}={mm['status']}" for row in rows for mm in row["methods"]
                    if mm["status"] != "pass" and not (mm["status"] == "pending" and mm["method"] in defer)]
    no_method = [row["id"] for row in rows if not row["methods"]]
    g1 = vg.chk(not_verified + [f"{i}:no proof method" for i in no_method], [], not not_verified and not no_method and bool(rows),
                ("requirements without a passing verification of their stated method: " + vg._more(not_verified + no_method, 12)
                 + ". For each, add or fix a test or property that cites it (simulation: a test tagged with the id that passes "
                   "on every seed; formal: a .sby job tagged with it whose tasks PASS; analysis/hardware: a testplan proof "
                   "entry naming the flow gate or bring-up step)") if rows else "spec.yaml has no requirements")
    untagged = [f"{a['kind']} {a['name']} ({a['file']}:{a['line']})" for a in arts if not a["cites"] and not a["class"]]
    unknown = [f"{a['kind']} {a['name']} cites {i}" for a in arts for i in a["cites"] if i not in known]
    no_reason = [f"{a['kind']} {a['name']} is {a['class']} without a reason" for a in arts
                 if a["class"] and len(str(a["reason"] or "").strip()) < MIN_REASON and not a["cites"]]
    bad2 = untagged + unknown + no_reason
    g2 = vg.chk(bad2, [], not bad2,
                ("; ".join(x for x in (("untagged: " + vg._more(untagged, 10)) if untagged else "",
                                       ("unknown requirement ids: " + vg._more(unknown, 10)) if unknown else "",
                                       ("no reason: " + vg._more(no_reason, 10)) if no_reason else "") if x)
                 + ". Tag each test with @req(\"<id>\") or a `# req: <id>` comment, each property with `// req: <id>`, each "
                   ".sby job with `# req: <id>`; a check that verifies no requirement says `robustness: <reason>` or "
                   "`structural: <reason>`") if bad2 else None)
    holes = justify(cov["holes"], plan, just)
    unjust = [f"{h['kind']} {h['item']}" for h in holes if not h["justified_by"]]
    if cov.get("no_rtl_points"):
        g3 = vg.chk("no points in the design RTL", "every hole closed or justified", False,
                    f"the coverage data has no line, branch or toggle point under {cov['rtl_rel']}: the run simulated other "
                    "copies of the sources (another directory) or none; re-run the coverage simulation on this design")
    elif not cov["measured"]:
        g3 = vg.chk("not measured", "every hole closed or justified", "coverage" in defer,
                    "no coverage data (seed*/coverage*.dat or coverage*.yml) in the coverage directory: run the bench under "
                    "Verilator with coverage (flow.cocotb_run) and pass that directory as --coverage")
    else:
        g3 = vg.chk(unjust, [], not unjust,
                    (f"{len(unjust)} coverage hole(s) neither closed nor justified: " + vg._more(unjust, 10) + ". Close each "
                     "with a test, or justify it in verif/justifications.yaml (coverage: [{kind, item (a glob), reason, owner, "
                     "date}])") if unjust else None)
    wv = all_waivers(design, plan, just, rtl_files)
    bad4 = [f"{w['where']} {w['item']}: {w['problem']}" for w in wv if w["problem"]]
    g4 = vg.chk(bad4, [], not bad4, ("waivers or justifications without owner, reason or date: " + vg._more(bad4, 10)
                                     + ". Each needs `owner`, a `reason` of at least a sentence and a `date` (YYYY-MM-DD)")
                if bad4 else None)
    base = None
    if baseline:
        try:
            base = json.loads(baseline.read_text())
        except (OSError, ValueError) as e:
            raise vg.PlanError(f"baseline {baseline} is not readable JSON: {e}")
    change = cr.diff_baseline([{"id": r["id"], "req_hash": r["req_hash"], "evidence_hash": r["evidence_hash"]} for r in rows],
                              base, just.get("reconfirmed") or [])
    g5 = vg.chk(change["stale"], [], not change["stale"],
                ("requirement text changed since the baseline but its evidence did not: " + ", ".join(change["stale"])
                 + ". The old evidence was made for the old text: change or re-run the evidence, or re-confirm it in "
                   "verif/justifications.yaml (reconfirmed: [{requirement, req_hash, owner, reason, date}])")
                if change["stale"] else None)
    for i in change["stale"]:
        for row in rows:
            if row["id"] == i:
                row["status"] = "stale"
    checks = {"requirements_verified": g1, "artefacts_cite_requirements": g2, "coverage_holes_justified": g3,
              "waivers_complete": g4, "changed_requirements_reverified": g5}
    tagged = sum(1 for a in arts if a["cites"])
    return {"schema": SCHEMA, "design": design.name,
            "generated": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "note": "DO-254-style evidence: a record of what was verified and how; not a claim of compliance with any standard.",
            "defer": list(defer), "inputs": cr.read_manifest(design, build_dir),
            "evidence_sources": {"runs": cr._rel(runs) if runs else None, "also": [cr._rel(d) for d in also or []],
                                 "coverage": cr._rel(coverage or runs) if (coverage or runs) else None,
                                 "formal": cr._rel(formal) if formal else None, "gates": cr._rel(gates) if gates else None,
                                 "hw": cr._rel(hw) if hw else None, "baseline": cr._rel(baseline) if baseline else None},
            "requirements": rows,
            "artefacts": [{k: a[k] for k in ("kind", "name", "file", "line", "cites", "class", "reason", "result", "detail",
                                             "source_sha256") if k in a} | ({"cross_check": a["cross_check"]} if "cross_check" in a else {})
                          for a in arts],
            "artefact_summary": {"total": len(arts), "citing": tagged,
                                 "robustness": sum(1 for a in arts if a["class"] == "robustness" and not a["cites"]),
                                 "structural": sum(1 for a in arts if a["class"] == "structural" and not a["cites"]),
                                 "untagged": len(untagged)},
            "coverage": {"measured": cov["measured"], "summary": cov["summary"], "holes": holes},
            "waivers": wv, "change": change, "gates": checks, "pass": all(c["pass"] for c in checks.values())}


# ---- rendering ----------------------------------------------------------------------------------------------------
def _cell(x: Any) -> str:
    return str(x).replace("|", "\\|").replace("\n", " ")


def to_markdown(t: dict) -> str:
    """The matrix as Markdown: one row per requirement and method, then the artefacts, holes, waivers and gates."""
    out = [f"# Traceability matrix: {t['design']}", "",
           f"Generated {t['generated']} by `flow/trace.py` ({t['schema']}). {t['note']}", ""]
    inp = t.get("inputs") or {}
    fl = inp.get("flow") or {}
    out += [f"Inputs: {inp.get('source')} record; flow commit `{fl.get('commit')}`{' (dirty tree)' if fl.get('dirty') else ''}; "
            f"knowledge-bank pin `{inp.get('kb_pin')}`; {len(inp.get('inputs') or {})} input files hashed.", ""]
    out += ["| Requirement | Design elements | Method | Verification (how linked) | Result | Supporting properties |",
            "|---|---|---|---|---|---|"]
    for r in t["requirements"]:
        sup = ", ".join(f"{s['name']} ({s['result']})" for s in r["supporting"]) or "-"
        first = True
        for m in r["methods"] or [{"method": "-", "status": "missing", "verifications": []}]:
            ver = "; ".join(f"{v['artefact']} ({v['via']}): {v['result']}" for v in m["verifications"]) or "none"
            out.append("| " + " | ".join(_cell(x) for x in (
                f"**{r['id']}** {r['text']}" if first else "", ", ".join(r["design_elements"]) or "-" if first else "",
                m["method"], ver, m["status"], sup if first else "")) + " |")
            first = False
    s = t["artefact_summary"]
    out += ["", f"Artefacts: {s['total']} ({s['citing']} cite a requirement, {s['robustness']} robustness, "
                f"{s['structural']} structural, {s['untagged']} untagged).", ""]
    cs = (t["coverage"] or {}).get("summary") or {}
    if cs:
        out += ["Coverage: " + "; ".join(f"{k} {v.get('hit')}/{v.get('points')} ({v.get('pct')} %)" for k, v in cs.items()
                                          if isinstance(v, dict) and v.get("points")), ""]
    holes = t["coverage"].get("holes") or []
    if holes:
        out += ["| Coverage hole | Justification |", "|---|---|"]
        groups: dict[tuple, list[str]] = {}
        for h in holes:
            j = h["justified_by"]
            key = (h["kind"], j["item"] if j else None, j["reason"] if j else None)
            groups.setdefault(key, []).append(h["item"])
        for (k, pat, reason), items in groups.items():
            shown = items[0] if len(items) == 1 else f"{len(items)} points, e.g. {items[0]}"
            out.append(f"| {_cell(k)}: {_cell(shown)} | {_cell(f'{pat}: {reason}') if pat else '**none**'} |")
        out.append("")
    if t["waivers"]:
        out += ["| Waiver | Item | Problem |", "|---|---|---|"]
        out += [f"| {_cell(w['where'])} | {_cell(w['item'])} | {_cell(w['problem'] or 'complete')} |" for w in t["waivers"]]
        out.append("")
    out += ["| Gate | Result | Detail |", "|---|---|---|"]
    for n, c in t["gates"].items():
        out.append(f"| {n} | {'PASS' if c['pass'] else 'FAIL'} | {_cell(c.get('why') or (c['value'] if c['value'] else 'none missing'))} |")
    ch = t.get("change") or {}
    if ch.get("baseline"):
        out += ["", f"Change since baseline {ch['baseline'].get('generated')}: text changed {ch['text_changed'] or 'none'}; "
                    f"evidence changed {ch['evidence_changed'] or 'none'}; stale {ch['stale'] or 'none'}; "
                    f"added {ch['added'] or 'none'}; removed {ch['removed'] or 'none'}."]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("design")
    ap.add_argument("--runs", help="directory of seed*/results.xml (the simulation that counts)")
    ap.add_argument("--also", action="append", default=[], help="another simulator's seed*/results.xml (cross-check)")
    ap.add_argument("--coverage", help="directory of seed*/coverage*.dat and coverage*.yml (default: --runs)")
    ap.add_argument("--formal", help="SymbiYosys output directory (flow/formal.sh)")
    ap.add_argument("--gates", help="the build's gates.json (analysis evidence)")
    ap.add_argument("--hw", help="the bring-up JSON (hardware evidence)")
    ap.add_argument("--baseline", help="an earlier trace.json: lists what changed and gates stale requirements")
    ap.add_argument("--defer", default="", help="comma list of methods (simulation, formal, analysis, hardware) or "
                                                "'coverage' whose evidence may still be pending at this stage")
    ap.add_argument("--build-dir", help="build directory holding brief 54's manifest.json, if any")
    ap.add_argument("--json")
    ap.add_argument("--md")
    a = ap.parse_args(argv)
    rel = lambda p: None if not p else (Path(p) if Path(p).is_absolute() else ROOT / p)
    design = rel(a.design)
    try:
        t = build(design, rel(a.runs), [rel(x) for x in a.also], rel(a.coverage), rel(a.formal), rel(a.gates), rel(a.hw),
                  rel(a.baseline), tuple(x.strip() for x in a.defer.split(",") if x.strip()), rel(a.build_dir))
    except (vg.PlanError, OSError, KeyError, TypeError, ValueError) as e:
        msg = e.args[0] if isinstance(e, vg.PlanError) and e.args else f"{type(e).__name__}: {e}"
        t = {"schema": SCHEMA, "design": Path(a.design).name, "pass": False,
             "gates": {"trace_inputs_readable": vg.chk(str(msg)[:600], "readable", False)}}
    for n, c in t["gates"].items():
        print(f"{'ok ' if c['pass'] else 'BAD'} {n}: {c['value'] if c['value'] not in ([], '') else 'none missing'}")
        if c.get("why"):
            print(f"    why: {c['why']}")
    for r in t.get("requirements") or []:
        for m in r["methods"]:
            arts = ", ".join(v["artefact"] for v in m["verifications"]) or "-"
            print(f"    {r['id']:8} {m['method']:10} {m['status']:8} {arts}")
    print(f"trace: {'PASS' if t['pass'] else 'FAIL'}")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(t, indent=1, default=str) + "\n")
    if a.md and "requirements" in t:
        Path(a.md).parent.mkdir(parents=True, exist_ok=True)
        Path(a.md).write_text(to_markdown(t))
    return 0 if t["pass"] else 1


def static_problems(design: Path) -> list[str]:
    """The tagging problems a tests role can fix before any simulation (brief 53): untagged tests and properties, unknown
    ids, a robustness/structural mark without a reason. One line each; empty when clean or when the inputs cannot be read
    (the V0/V1 self-check reports those)."""
    try:
        t = build(design, None)
    except (vg.PlanError, OSError, KeyError, TypeError, ValueError):
        return []
    c = t["gates"]["artefacts_cite_requirements"]
    return [] if c["pass"] else [f"TRACE artefacts_cite_requirements: {c['why']}"]


if __name__ == "__main__":
    sys.exit(main())
