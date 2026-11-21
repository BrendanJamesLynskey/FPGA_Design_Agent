#!/usr/bin/env python3
"""Spec-to-evidence traceability, schema v1 (brief 116).

    python -m flow.trace_v1 check  [DESIGN ...]      gate: orphan checks, untraced requirements, bad references (exit 1)
    python -m flow.trace_v1 write  [DESIGN ...]      write verif/matrix.md and verif/matrix.html per design and docs/traceability_matrix.{md,html}
    python -m flow.trace_v1 pin    DESIGN            write verif/evidence_pins.yaml (what each checked file was when its evidence was recorded)
    python -m flow.trace_v1 show   DESIGN            the one-line thoroughness summary and the gaps
    python -m flow.trace_v1 lean-record [DESIGN ...] rebuild the Lean project with `lake build` and write its hash-pinned build record (brief 125; needs the toolchain)
    python -m flow.trace_v1 lean-statement DESIGN ITEM   print the Lean statement and hashes a human reads before approving it (writes nothing)
    --lean {recorded,live,auto}                      where a formal_lean item's build status comes from: the committed record (default for `write`, `check`,
                                                     so committed matrices do not depend on the machine), `lake build` now, or live when the toolchain exists

The human specifies the requirements and checks that the verification is thorough; the agent holds the knowledge to implement and to
verify; the user can read any of the implementation but does not have to. This module is the place where those two meet: it reads
``designs/<d>/verif/testplan.yaml`` (schema v1, or v0 which is upgraded in memory), reads the evidence files the items point at, and
COMPUTES every status. A status is never typed in the plan.

Schema v1 (a superset of v0, so ``flow/verif_gates.py`` still reads a v1 file that keeps v0's keys)::

    schema: fpga-design-agent/testplan/v1
    requirements:
      - id: B96-P-LAT-E
        kind: functional | performance | interface | safety
        title: ...
        text: ...
        source: designs/x/docs/design.md#anchor        # or spec.yaml paths in `spec:` (v0)
        spec_status: draft | agreed                    # a human agrees a requirement; the agent never does
        external: "10G NIC"                            # optional: depends on an element outside the design
        performance: {quantity: echo latency E, unit: clocks, op: le, bound: 22, condition: "100 restarts, fibre loopback"}
    verification:
      - id: V-...
        requirements: [B96-P-LAT-E]
        method: sim_test | uvm_test | assertion | formal | formal_lean | coverage_bin | timing | sim_measurement | board_measurement | review
        instrument: eye_scan | jtag_registers | sysmon | ila_capture | latency_loop | optical_ddm | external_equipment   # board_measurement
        title: ...
        evidence: {file: results/x/*.json, reader: json|text|junit|gates|exists, field: a.b.c, regex: ..., tests: [stem::name]}
        pass_when: [{field: a.b, op: eq, value: 0}]    # non-measuring items; a measuring item is judged against its requirement's bound
        checks: [designs/x/rtl/a.sv]                   # the RTL/spec this evidence is about (staleness)
        bounded: {depth: 24}                           # formal BMC only
        planned: "brief 112"                           # a hook for evidence that does not exist yet
        reviewer: name, reviewer_kind: human|agent, date: YYYY-MM-DD   # review
        lean: {module: Gray.Spec, theorem: Gray.gray_step, project: formal/lean}                                  # formal_lean (brief 125)
        rtl_link: {kind: rtl_generated|transcription_tested|transcription_untested|model_only,                     # how the Lean model meets the RTL
                   source: [{file: designs/x/rtl/a.sv, lines: "77-82", commit: <sha, optional>}], transcribed_in: Gray/Spec.lean,
                   crosscheck: {file: formal/lean/Gray/CrossCheck.lean, reference: "what independent thing it is compared with"}}

A formal_lean statement is approved only by a human, in ``verif/lean_approvals.yaml`` (never in this file; see flow/lean_tier.py).
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_V1 = "fpga-design-agent/testplan/v1"
SCHEMA_V0 = "fpga-design-agent/testplan/v0"
KINDS = ("functional", "performance", "interface", "safety")
METHODS = ("sim_test", "uvm_test", "assertion", "formal", "formal_lean", "coverage_bin", "timing", "sim_measurement", "board_measurement", "review")
MEASURING = ("timing", "sim_measurement", "board_measurement")
INSTRUMENTS = ("eye_scan", "jtag_registers", "sysmon", "ila_capture", "latency_loop", "optical_ddm", "external_equipment")
STATUSES = ("pass", "fail", "not_run", "stale", "bounded", "unapproved")
OPS = ("eq", "ne", "le", "ge", "lt", "gt", "true", "false", "in")
LABEL = {"sim_test": "simulation test", "uvm_test": "UVM test", "assertion": "assertion (SVA)", "formal": "formal", "formal_lean": "Lean proof (all widths)", "coverage_bin": "coverage",
         "timing": "post-route timing", "sim_measurement": "simulation measurement", "board_measurement": "board measurement", "review": "review"}
COL = {"sim_test": "sim test", "uvm_test": "UVM", "assertion": "SVA", "formal": "formal", "formal_lean": "Lean", "coverage_bin": "coverage", "timing": "timing",
       "sim_measurement": "sim measure", "board_measurement": "board", "review": "review"}
FRAMING = ("The human specifies the requirements and checks that the verification is thorough enough. The agent holds the knowledge to "
           "implement and to verify. You can open any of the implementation or the evidence, and you do not have to. Hardware on the board, "
           "with attached instruments, is a verification layer of its own: where a requirement depends on something outside the design "
           "(an optical link, a network card, a data source) it may be the only way to close it.")


class PlanError(Exception):
    """The testplan or an evidence reader's configuration is malformed (reported by the gate, never a traceback)."""


# ---- loading ---------------------------------------------------------------------------------------------
def plan_path(design: Path) -> Path:
    return design / "verif" / "testplan.yaml"


def v1_designs() -> list[Path]:
    """Designs whose testplan is schema v1 or v0 (every one is rendered; only v1 files are gated)."""
    out = []
    for p in sorted((ROOT / "designs").glob("*/verif/testplan.yaml")):
        out.append(p.parent.parent)
    for p in sorted((ROOT / "arith").glob("*/verif/testplan.yaml")):       # brief 139a: the arithmetic library's functions
        out.append(p.parent.parent)
    return out


def load(design: Path) -> dict[str, Any]:
    p = plan_path(design)
    try:
        raw = yaml.safe_load(p.read_text())
    except (OSError, yaml.YAMLError) as e:
        raise PlanError(f"{p}: {e}")
    if not isinstance(raw, dict):
        raise PlanError(f"{p}: not a mapping")
    schema = raw.get("schema")
    if schema == SCHEMA_V0:
        return upgrade_v0(design, raw)
    if schema != SCHEMA_V1:
        raise PlanError(f"{p}: unknown schema {schema!r}")
    plan = {"design": raw.get("design") or design.name, "schema": schema, "source_schema": schema,
            "requirements": [dict(r) for r in raw.get("requirements") or []],
            "verification": [dict(i) for i in raw.get("verification") or []],
            "discover": raw.get("discover") or [], "notes": raw.get("notes") or ""}
    if raw.get("evidence_record"):               # v0's per-requirement lists, kept in a v1 file, are expanded too
        plan["verification"] += legacy_items(design, raw)
        for r in plan["requirements"]:
            r.setdefault("kind", "functional")
            r.setdefault("title", ", ".join(r.get("spec", [])))
            r.setdefault("spec_status", "unspecified")
            r.setdefault("source", raw.get("spec", ""))
    return plan


def legacy_items(design: Path, raw: dict) -> list[dict]:
    rec = raw.get("evidence_record") or f"results/04f/{design.name}_verif_gates.json"
    rtl = sorted(str(p.relative_to(ROOT)) for p in (design / "rtl").glob("*.sv"))
    items = []
    for r in raw.get("requirements") or []:
        for method, key, rd in (("sim_test", "tests", "v0_test"), ("assertion", "assertions", "v0_assertion"),
                                ("assertion", "cover_props", "v0_cover"), ("coverage_bin", "bins", "v0_bin"), ("formal", "formal", "v0_formal")):
            for n in r.get(key) or []:
                it = {"id": f"{r['id']}:{n}", "requirements": [r["id"]], "method": method, "title": n, "ref": n,
                      "evidence": {"file": rec, "reader": "gates", "kind": rd, "name": n}, "checks": rtl}
                if method == "formal":
                    it["bounded"] = {"depth": "bounded proof (SymbiYosys BMC)"}
                items.append(it)
    return items


def upgrade_v0(design: Path, raw: dict) -> dict[str, Any]:
    """v0 -> v1 in memory: every v0 requirement is functional; every name it lists becomes an item whose evidence is the V-stage
    gate record named by ``evidence_record`` (default ``results/04f/<design>_verif_gates.json``)."""
    raw = dict(raw)
    raw.setdefault("evidence_record", f"results/04f/{design.name}_verif_gates.json")
    raw["schema"] = SCHEMA_V1
    plan = {"design": raw.get("design") or design.name, "schema": SCHEMA_V1, "source_schema": SCHEMA_V0, "requirements": [],
            "verification": legacy_items(design, raw), "discover": [], "notes": "upgraded in memory from schema v0"}
    for r in raw.get("requirements") or []:
        plan["requirements"].append({"id": r["id"], "kind": "functional", "title": ", ".join(r.get("spec", [])), "text": "",
                                     "source": raw.get("spec", ""), "spec": r.get("spec", []), "spec_status": "unspecified"})
    return plan


# ---- evidence readers ------------------------------------------------------------------------------------
def resolve(pattern: str) -> Path | None:
    """A repo-relative path or glob; the last match in sorted order (run directories are time stamps)."""
    hits = sorted(glob.glob(str(ROOT / pattern)))
    return Path(hits[-1]) if hits else None


def rel(p: Path) -> str:
    return p.resolve().relative_to(ROOT).as_posix()


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dig(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            if part not in cur:
                raise KeyError(path)
            cur = cur[part]
        else:
            raise KeyError(path)
    return cur


def cmp(value: Any, op: str, bound: Any) -> bool:
    if op == "true":
        return value is True
    if op == "false":
        return value is False
    if op == "in":
        return value in bound
    if op == "eq":
        return value == bound
    if op == "ne":
        return value != bound
    v, b = float(value), float(bound)
    return {"le": v <= b, "ge": v >= b, "lt": v < b, "gt": v > b}[op]


def _junit(p: Path) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for tc in ET.parse(p).getroot().iter("testcase"):
        stem = (tc.get("classname") or "").split(".")[-1]
        out[f"{stem}::{tc.get('name')}"] = not any(c.tag in ("failure", "error", "skipped") for c in tc)
    return out


def read_value(ev: dict, path: Path) -> Any:
    reader = ev.get("reader", "json")
    if reader == "json":
        return dig(json.loads(path.read_text()), ev["field"]) if ev.get("field") else True
    if reader == "text":
        m = re.search(ev["regex"], path.read_text(), re.M)
        if not m:
            raise KeyError(f"no match for {ev['regex']!r}")
        g = m.group(1) if m.groups() else True
        try:
            return float(g)
        except (TypeError, ValueError):
            return g
    if reader == "exists":
        return path.stat().st_size > 0
    raise PlanError(f"reader {reader!r} has no value")


def judge(item: dict, req_by_id: dict, cache: dict) -> dict[str, Any]:
    """Pass / fail / not_run for one item from its evidence alone (staleness and boundedness are applied by the caller)."""
    ev = item.get("evidence") or {}
    res: dict[str, Any] = {"id": item["id"], "method": item["method"], "title": item.get("title", ""), "status": "not_run", "value": None,
                           "detail": "", "evidence": None, "instrument": item.get("instrument"), "planned": item.get("planned")}
    if not ev.get("file"):
        res["detail"] = "no evidence file named" + (f" (planned: {item['planned']})" if item.get("planned") else "")
        return res
    p = resolve(ev["file"])
    if p is None:
        res["detail"] = f"evidence not found: {ev['file']}" + (f" (planned: {item['planned']})" if item.get("planned") else "")
        res["evidence"] = {"file": ev["file"], "exists": False}
        return res
    res["evidence"] = {"file": rel(p), "exists": True}
    reader = ev.get("reader", "json")
    try:
        if reader == "junit":
            runs = cache.setdefault(("junit", str(p)), _junit(p))
            want = []
            for t in ev.get("tests") or []:
                if t.endswith("::*"):
                    want += [k for k in runs if k.startswith(t[:-1])]
                else:
                    want.append(t)
            missing = [t for t in want if t not in runs]
            bad = [t for t in want if t in runs and not runs[t]]
            ok = bool(want) and not missing and not bad
            res.update(status="pass" if ok else "fail", value=f"{len(want) - len(bad) - len(missing)} of {len(want)} tests passed",
                       detail=("; ".join(([f"failed: {', '.join(bad[:4])}"] if bad else []) + ([f"absent from the run: {', '.join(missing[:4])}"] if missing else []))
                              or f"{len(want)} test(s) passed in the recorded run"))
            return res
        if reader == "gates":
            g = cache.setdefault(("json", str(p)), json.loads(p.read_text()))
            return _gates(item, ev, g, res)
        if reader == "review":
            res.update(status="pass", detail=f"{item.get('reviewer', '?')} ({item.get('reviewer_kind', 'unspecified')}), {item.get('date', 'undated')}")
            return res
        value = read_value(ev, p)
    except (KeyError, IndexError, ValueError, TypeError, ET.ParseError, json.JSONDecodeError, re.error) as e:
        res.update(status="not_run", detail=f"field not readable ({type(e).__name__}: {e})")
        return res
    res["value"] = value
    if item["method"] in MEASURING and not item.get("pass_when"):
        reqs = [req_by_id[r] for r in item.get("requirements", []) if r in req_by_id and req_by_id[r].get("performance")]
        if not reqs:
            res.update(status="fail", detail="a measuring item must trace to a requirement with a `performance` bound")
            return res
        pf = reqs[0]["performance"]
        ok = cmp(value, pf["op"], pf["bound"])
        res["judged_by_bound"] = True
        res.update(status="pass" if ok else "fail", detail=f"measured {fmt(value)} {pf.get('unit', '')}; bound {pf['op']} {pf['bound']} {pf.get('unit', '')}".replace(" le ", " at most ").replace(" ge ", " at least "))
        return res
    conds = item.get("pass_when") or [{"field": ev.get("field"), "op": "true"}]
    outs = []
    for c in conds:
        try:
            v = dig(json.loads(p.read_text()), c["field"]) if c.get("field") and ev.get("reader", "json") == "json" else value
            outs.append((cmp(v, c["op"], c.get("value")), f"{c.get('field') or 'value'} = {fmt(v)}"))
        except (KeyError, IndexError, ValueError, TypeError):
            outs.append((False, f"{c.get('field')} unreadable"))
    ok = all(o for o, _ in outs)
    res.update(status="pass" if ok else "fail", detail="; ".join(t for _, t in outs))
    return res


def _gates(item: dict, ev: dict, g: dict, res: dict) -> dict:
    """v0 upgrade: one name judged by the V-stage gate record."""
    st = g.get("stages", {})
    chk = lambda s, k: ((st.get(s) or {}).get("checks") or {}).get(k) or {}
    kind, name = ev["kind"], ev["name"]
    if kind == "v0_test":
        miss, bad, seeds = chk("V2", "planned_tests_missing"), chk("V2", "failing_tests"), chk("V2", "seeds_run")
        ok = name not in (miss.get("value") or []) and name not in (bad.get("value") or []) and bool(seeds.get("pass"))
        d = f"seeds {seeds.get('value')}: not missing, not failing" if ok else "missing or failing, or no seeded run"
    elif kind == "v0_assertion":
        c = chk("V2", "assertions_bound_zero_failures")
        ok = bool(c.get("pass")) and name in (c.get("value") or [])
        d = "bound, zero failures" if ok else "not in the bound-assertion list or failing"
    elif kind == "v0_cover":
        c = chk("V3", "cover_properties_unhit")
        ok = name not in (c.get("value") or []) and bool(c.get("pass"))
        d = "hit" if ok else "unhit"
    elif kind == "v0_bin":
        c = chk("V3", "functional_bins_unhit")
        ok = not any(str(u).startswith(name) for u in (c.get("value") or [])) and bool(c.get("pass"))
        d = "every bin hit" if ok else "bins unhit"
    else:
        c = chk("V2", "formal_tasks_not_passing")
        ok = name not in (c.get("value") or []) and bool(c.get("pass"))
        d = "bounded proof and cover pass" if ok else "not passing"
    res.update(status="pass" if ok else "fail", detail=d)
    return res


def fmt(v: Any) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


# ---- staleness: pins -------------------------------------------------------------------------------------
def pins_path(design: Path) -> Path:
    return design / "verif" / "evidence_pins.yaml"


def load_pins(design: Path) -> dict:
    p = pins_path(design)
    return (yaml.safe_load(p.read_text()) or {}).get("pins", {}) if p.exists() else {}


def _git(*a: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _sha_at(commit: str, path: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{path}"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return "absent"
    return hashlib.sha256(r.stdout).hexdigest() if r.returncode == 0 else "absent"


def compute_pins(design: Path) -> dict:
    """For each item with `checks`: the evidence file's hash and the hash of every checked file *as of the commit that last changed the
    evidence file* (the working tree where the evidence is not committed yet). A checked file that has changed since is why the
    evidence is stale. Needs git history; the collector itself reads only the pins, so it is deterministic."""
    plan = load(design)
    out: dict[str, Any] = {}
    for it in plan["verification"]:
        ev = it.get("evidence") or {}
        p = resolve(ev["file"]) if ev.get("file") else None
        if p is None or not it.get("checks"):
            continue
        er = rel(p)
        clean = _git("status", "--porcelain", "--", er)
        commit = (_git("log", "-1", "--format=%H", "--", er) or "").strip()
        use_tree = (clean is None or clean.strip() != "" or not commit)
        checks = {}
        for c in it["checks"]:
            cp = ROOT / c
            checks[c] = (sha(cp) if cp.exists() else "absent") if use_tree else _sha_at(commit, c)
        out[it["id"]] = {"evidence": er, "evidence_sha256": sha(p), "checks": checks}
    return out


def write_pins(design: Path) -> Path:
    p = pins_path(design)
    head = ("# Generated by `python -m flow.trace_v1 pin` (brief 116); do not edit.\n"
            "# For each item: the evidence file's hash, and the hash of every file the evidence is about as of the commit that last changed\n"
            "# the evidence. The collector compares them with the files today: a difference marks the evidence stale.\n")
    p.write_text(head + yaml.safe_dump({"pins": compute_pins(design)}, sort_keys=True, width=140))
    return p


def staleness(item: dict, res: dict, pins: dict) -> str | None:
    if not item.get("checks") or not (res.get("evidence") or {}).get("exists"):
        return None
    pin = pins.get(item["id"])
    if not pin:
        return "no pin recorded (run: python -m flow.trace_v1 pin)"
    p = ROOT / res["evidence"]["file"]
    if pin.get("evidence") != res["evidence"]["file"] or pin.get("evidence_sha256") != sha(p):
        return "the evidence file changed after it was pinned (run: python -m flow.trace_v1 pin)"
    changed = []
    for c, h in (pin.get("checks") or {}).items():
        cp = ROOT / c
        now = sha(cp) if cp.exists() else "absent"
        if now != h:
            changed.append(c)
    if changed:
        return "changed since the evidence was recorded: " + ", ".join(changed[:4]) + (f" (+{len(changed) - 4} more)" if len(changed) > 4 else "")
    return None


# ---- collection ------------------------------------------------------------------------------------------
def discovered(plan: dict) -> set[str]:
    names: set[str] = set()
    for d in plan.get("discover") or []:
        pat = re.compile(d.get("pattern", r"^def (test_\w+)"), re.M)
        for f in sorted(glob.glob(str(ROOT / d["glob"]))):
            stem = Path(f).stem
            names |= {f"{stem}::{m}" for m in pat.findall(Path(f).read_text())}
    return names


def claimed(plan: dict) -> set[str]:
    out: set[str] = set()
    for it in plan["verification"]:
        for t in (it.get("evidence") or {}).get("tests") or []:
            out.add(t)
    return out


def collect(design: Path, lean: str = "recorded") -> dict[str, Any]:
    """``lean``: where a formal_lean item's build status comes from (see flow/lean_tier.py): the committed record, ``lake build`` now, or auto."""
    plan = load(design)
    reqs = plan["requirements"]
    req_by_id = {r["id"]: r for r in reqs}
    pins = load_pins(design)
    cache: dict = {}
    from flow import lean_tier
    lean_tier.prime(plan, cache)
    results = []
    for it in plan["verification"]:
        r = lean_tier.judge_lean(it, design, lean, cache) if it.get("method") == "formal_lean" else judge(it, req_by_id, cache)
        r["requirements"] = list(it.get("requirements") or [])
        r["checks"] = list(it.get("checks") or [])
        if it.get("bounded") is not None:
            r["bounded"] = it["bounded"]
        for k in ("reviewer", "reviewer_kind", "date"):
            if it.get(k):
                r[k] = it[k]
        if r["status"] == "pass":
            why = staleness(it, r, pins)
            if why:
                r["status"], r["stale_because"] = "stale", why
            elif it.get("bounded") is not None:
                r["status"] = "bounded"
        results.append(r)
    by_req: dict[str, list] = {r["id"]: [] for r in reqs}
    for r in results:
        for q in r["requirements"]:
            if q in by_req:
                by_req[q].append(r)
    rows = []
    for q in reqs:
        items = by_req[q["id"]]
        rows.append(rollup(q, items))
    gaps = find_gaps(plan, rows, results, req_by_id, design)
    return {"design": plan["design"], "path": rel(design), "source_schema": plan["source_schema"], "requirements": rows, "items": results,
            "gaps": gaps, "summary": summarise(rows, results, gaps), "notes": plan.get("notes", "")}


def rollup(q: dict, items: list[dict]) -> dict:
    st = [i["status"] for i in items]
    meas = [i for i in items if i["method"] in MEASURING and i.get("judged_by_bound")]
    perf = q.get("kind") == "performance" or bool(q.get("performance"))
    basis = None
    if "fail" in st:
        state = "fail"
    elif perf:
        ok = [i for i in meas if i["status"] == "pass"]
        if ok:
            state = "verified"
            basis = ("board" if any(i["method"] == "board_measurement" for i in ok) else
                     "timing" if any(i["method"] == "timing" for i in ok) else "simulation")
        elif any(i["status"] == "stale" for i in meas):
            state = "stale"
        elif any(i["status"] == "pass" for i in items):
            state = "no_measurement"
        else:
            state = "not_run"
    else:
        if "pass" in st:
            state = "verified"
        elif "bounded" in st:
            state = "bounded"
        elif "stale" in st:
            state = "stale"
        elif "unapproved" in st:
            state = "unapproved"
        else:
            state = "not_run"
    ext = q.get("external")
    hw_done = any(i["method"] == "board_measurement" and i["status"] == "pass" for i in items)
    hw_methods = sorted({i["method"] for i in items if i["status"] == "pass"})
    row = {k: q[k] for k in ("id", "kind", "title", "text", "source", "spec_status", "performance", "external", "spec") if k in q}
    passing = [i for i in items if i["status"] == "pass"]
    lean_only = bool(passing) and all(i["method"] == "formal_lean" and (i.get("lean") or {}).get("rtl_link") != "rtl_generated" for i in passing)
    row["lean_transcription_only"] = lean_only
    row.update(state=state, basis=basis, stale_items=sum(1 for x in st if x == "stale"), items=[i["id"] for i in items], passing_methods=hw_methods,
               hardware_verified=hw_done, hardware_only=bool(ext),
               hardware_closure=None if not ext else ("done" if hw_done else "open"))
    return row


def find_gaps(plan: dict, rows: list, results: list, req_by_id: dict, design: Path | None = None) -> list[dict]:
    g: list[dict] = []
    for r in rows:
        if not r["items"]:
            g.append({"type": "untraced_requirement", "id": r["id"], "text": "no verification item traces to this requirement", "gate": True})
        elif r["state"] in ("not_run", "no_measurement", "stale", "bounded", "fail"):
            g.append({"type": "no_passing_evidence", "id": r["id"], "state": r["state"], "text": {
                "not_run": "no passing evidence", "no_measurement": "a performance requirement with no measured value inside the bound",
                "stale": "its evidence is stale", "bounded": "only a bounded formal result", "fail": "an item fails"}[r["state"]], "gate": False})
        if r["state"] == "verified" and r["kind"] == "performance" and r["basis"] == "simulation":
            g.append({"type": "performance_sim_only", "id": r["id"], "text": "verified in simulation only, not measured on the board", "gate": False})
        if r.get("external") and r["hardware_closure"] == "open":
            g.append({"type": "hardware_open", "id": r["id"], "text": f"depends on {r['external']}; only hardware verification can close it, and it has not been done", "gate": False})
        if r["state"] == "verified" and not r["hardware_verified"] and r.get("external"):
            g.append({"type": "external_not_hardware_verified", "id": r["id"], "text": f"passes in simulation but depends on {r['external']}", "gate": False})
    for i in results:
        if not i["requirements"]:
            g.append({"type": "orphan_check", "id": i["id"], "text": "traces to no requirement", "gate": True})
        for q in i["requirements"]:
            if q not in req_by_id:
                g.append({"type": "orphan_check", "id": i["id"], "text": f"traces to unknown requirement {q}", "gate": True})
        if i["status"] == "stale":
            g.append({"type": "stale_evidence", "id": i["id"], "text": i.get("stale_because", ""), "gate": False})
        if i["status"] == "unapproved":
            g.append({"type": "lean_statement_unapproved", "id": i["id"], "text": "the Lean statement is not approved by a human; until it is, the proof is not counted as verification", "gate": False})
        if i["status"] == "fail" and i["method"] == "formal_lean":
            g.append({"type": "lean_failing", "id": i["id"], "text": i["detail"], "gate": False})
    cl = claimed(plan)
    wild = tuple(c[:-1] for c in cl if c.endswith("::*"))
    for n in sorted(n for n in discovered(plan) - cl if not n.startswith(wild)):
        g.append({"type": "orphan_check", "id": n, "text": "a test found in the bench that no item names", "gate": True})
    from flow import lean_tier
    lean_its = {it["id"]: it for it in plan["verification"] if it.get("method") == "formal_lean"}
    apps = lean_tier.load_approvals(design) if design is not None else {}
    if design is not None:
        for t in lean_tier.approval_problems(design, set(lean_its), lean_its):
            g.append({"type": "lean_approval", "id": design.name, "text": t, "gate": True})
    for it in plan["verification"]:
        if it.get("method") == "formal_lean":
            for t in lean_tier.item_problems(it, apps):
                changed = t.startswith("frozen ")
                g.append({"type": "lean_frozen_statement_changed" if changed else "bad_item", "id": it.get("id"), "text": t, "gate": True})
        if it.get("method") not in METHODS:
            g.append({"type": "bad_item", "id": it.get("id"), "text": f"unknown method {it.get('method')!r}", "gate": True})
        if it.get("method") == "board_measurement" and it.get("instrument") not in INSTRUMENTS:
            g.append({"type": "bad_item", "id": it.get("id"), "text": f"board_measurement needs an instrument from {', '.join(INSTRUMENTS)}", "gate": True})
        for c in it.get("checks") or []:
            if not (ROOT / c).exists():
                g.append({"type": "bad_item", "id": it.get("id"), "text": f"checked file {c} does not exist", "gate": True})
    for q in plan["requirements"]:
        if q.get("kind") not in KINDS:
            g.append({"type": "bad_item", "id": q["id"], "text": f"unknown kind {q.get('kind')!r}", "gate": True})
        if q.get("kind") == "performance":
            pf = q.get("performance") or {}
            if not all(k in pf for k in ("quantity", "unit", "op", "bound", "condition")) or pf.get("op") not in OPS:
                g.append({"type": "bad_item", "id": q["id"], "text": "a performance requirement needs quantity, unit, op, bound and condition", "gate": True})
    return g


def summarise(rows: list, results: list, gaps: list) -> dict:
    kinds = {k: sum(1 for r in rows if r["kind"] == k) for k in KINDS}
    meth = {m: {s: sum(1 for i in results if i["method"] == m and i["status"] == s) for s in STATUSES} for m in METHODS}
    states: dict[str, int] = {}
    for r in rows:
        states[r["state"]] = states.get(r["state"], 0) + 1
    ext = [r for r in rows if r.get("external")]
    gt: dict[str, int] = {}
    for x in gaps:
        gt[x["type"]] = gt.get(x["type"], 0) + 1
    lean_r = [i for i in results if i["method"] == "formal_lean"]
    lean = {"items": len(lean_r), "approved": sum(1 for i in lean_r if (i.get("lean") or {}).get("approved")),
            "statement_not_approved": sum(1 for i in lean_r if i["status"] == "unapproved"),
            "by_status": {k: sum(1 for i in lean_r if i["status"] == k) for k in STATUSES if any(i["status"] == k for i in lean_r)},
            "by_tier": {t: sum(1 for i in lean_r if (i.get("lean") or {}).get("tier") == t) for t in ("kernel_only", "compiled_decision_procedure", "unsound")},
            "by_rtl_link": {t: sum(1 for i in lean_r if (i.get("lean") or {}).get("rtl_link") == t) for t in
                            ("rtl_generated", "transcription_tested", "transcription_untested", "model_only")},
            "build_sources": sorted({(i.get("lean") or {}).get("build_source") or "none" for i in lean_r})}
    s = {"requirements": len(rows), "by_kind": kinds, "lean": lean, "by_state": states, "items": len(results), "by_method": meth, "gap_counts": gt,
         "external": len(ext), "external_hardware_done": sum(1 for r in ext if r["hardware_closure"] == "done"),
         "performance_board": sum(1 for r in rows if r["kind"] == "performance" and r["basis"] == "board"),
         "performance_sim_only": sum(1 for r in rows if r["kind"] == "performance" and r["basis"] == "simulation"),
         "performance_timing": sum(1 for r in rows if r["kind"] == "performance" and r["basis"] == "timing"),
         "spec_agreed": sum(1 for r in rows if r.get("spec_status") == "agreed"),
         "human_reviews": sum(1 for i in results if i["method"] == "review" and i.get("reviewer_kind") == "human" and i["status"] == "pass")}
    s["line"] = summary_line(s)
    return s


def summary_line(s: dict) -> str:
    kinds = ", ".join(f"{n} {k}" for k, n in s["by_kind"].items() if n)
    st = s["by_state"]
    ver = st.get("verified", 0)
    bits = [f"{s['requirements']} requirements ({kinds}); {ver} verified"]
    for k, lab in (("bounded", "bounded only"), ("stale", "stale"), ("fail", "failing"), ("no_measurement", "performance with no measurement"), ("not_run", "with no passing evidence")):
        if st.get(k):
            bits.append(f"{st[k]} {lab}")
    if s["external"]:
        bits.append(f"{s['external_hardware_done']} of {s['external']} requirements that depend on an external element closed by hardware")
    if s["performance_board"] or s["performance_sim_only"] or s["performance_timing"]:
        bits.append(f"performance verified: {s['performance_board']} on the board, {s['performance_timing']} by post-route timing, {s['performance_sim_only']} in simulation only")
    bits.append(f"{s['spec_agreed']} of {s['requirements']} requirements agreed by a human, {s['human_reviews']} human review(s) recorded")
    L = s["lean"]
    if L["items"]:
        ks, cd = L["by_tier"]["kernel_only"], L["by_tier"]["compiled_decision_procedure"]
        bits.append(f"{L['items']} Lean proof item(s) (all widths): {L['approved']} with a human-approved statement, {L['statement_not_approved']} with statement not approved; "
                    f"{ks} kernel only, {cd} using a compiled decision procedure; build status from: {', '.join(L['build_sources'])}")
    return "; ".join(bits) + "."


def collect_all(designs: list[Path] | None = None, lean: str = "recorded") -> dict[str, Any]:
    ds = designs if designs is not None else v1_designs()
    out = [collect(d, lean) for d in ds]
    tot = {"requirements": sum(d["summary"]["requirements"] for d in out), "verified": sum(d["summary"]["by_state"].get("verified", 0) for d in out),
           "designs": len(out)}
    return {"schema": "fda-traceability/1", "framing": FRAMING, "designs": out, "total": tot}


# ---- gate ------------------------------------------------------------------------------------------------
def gate(design: Path, lean: str = "recorded") -> list[str]:
    """Problems that fail CI for a v1 testplan: an orphan check, an untraced requirement, a malformed item. Staleness and
    missing evidence are reported, not failed."""
    try:
        plan = load(design)
    except PlanError as e:
        return [str(e)]
    if plan["source_schema"] != SCHEMA_V1:
        return []                              # v0 files are gated by flow/verif_gates.py
    return [f"{x['type']}: {x['id']}: {x['text']}" for x in collect(design, lean)["gaps"] if x["gate"]]


# ---- rendering -------------------------------------------------------------------------------------------
STATE_TEXT = {"verified": "verified", "fail": "FAILS", "not_run": "not run", "stale": "stale", "bounded": "bounded only", "no_measurement": "no measurement",
              "unapproved": "proved, statement not approved"}
MARK = {"pass": "pass", "fail": "FAIL", "not_run": "not run", "stale": "stale", "bounded": "bounded", "unapproved": "statement not approved"}


def _tag(i: dict) -> str:
    """The status of a cell item; a Lean proof also says its axiom tier, how the Lean model meets the RTL, and where the build status came from."""
    t = MARK[i["status"]] + (f" [{i['instrument']}]" if i.get("instrument") else "")
    L = i.get("lean")
    if i["method"] == "formal_lean" and L:
        from flow import lean_tier as lt
        bits = [lt.TIER_TEXT.get(L.get("tier") or "", "no build"), lt.RTL_LINK_SHORT.get(L.get("rtl_link") or "", "no RTL link"), (L.get("build_source") or "").replace(" (not re-run)", "")]
        t += " [" + "; ".join(b for b in bits if b) + "]"
    return t


def _link(from_dir: Path, target: str) -> str:
    return os.path.relpath(ROOT / target, from_dir).replace(os.sep, "/")


def _state_cell(r: dict) -> str:
    t = STATE_TEXT[r["state"]]
    if r["state"] == "verified" and r.get("external") and not r["hardware_verified"]:
        return "passes without hardware; hardware verification open"
    if r["state"] == "verified" and r["kind"] == "performance":
        t += f" ({'board-measured' if r['basis'] == 'board' else 'post-route timing' if r['basis'] == 'timing' else 'simulation only'})"
    if r["state"] == "verified" and r.get("stale_items"):
        t += f"; {r['stale_items']} item(s) stale"
    if r["state"] == "verified" and r.get("lean_transcription_only"):
        t += "; the Lean proof is of a transcription of the RTL, not of the RTL itself"
    return t


def render_md(d: dict, out_dir: Path) -> str:
    items = {i["id"]: i for i in d["items"]}
    L = [f"# {d['design']}: specification to evidence", "",
         "<!-- Generated by `python -m flow.trace_v1 write` (brief 116) from verif/testplan.yaml and the evidence files it names. Do not edit. -->", "",
         FRAMING, "", f"**Summary.** {d['summary']['line']}", ""]
    if d["notes"]:
        L += [d["notes"].strip(), ""]
    L += ["## Matrix", "", "Rows are requirements, columns are verification methods. A cell lists each item with its computed status and links to its evidence. "
          "Status is read from the evidence by code; it is never typed. `stale` means a file the evidence is about changed after the evidence was recorded; "
          "`bounded` means a formal bounded model check only.", ""]
    L += ["| Requirement | Kind | State | " + " | ".join(COL[m] for m in METHODS) + " |", "|---|---|---|" + "---|" * len(METHODS)]
    for r in d["requirements"]:
        cells = []
        for m in METHODS:
            parts = []
            for iid in r["items"]:
                i = items[iid]
                if i["method"] != m:
                    continue
                tag = _tag(i)
                ev = i.get("evidence")
                parts.append(f"{tag}: [{i['id'].split(':')[-1][:28]}]({_link(out_dir, ev['file'])})" if ev and ev.get("exists") else f"{tag}: {i['id'].split(':')[-1][:28]}")
            cells.append("<br>".join(parts) or "")
        ext = f" Depends on: {r['external']}; hardware verification {r['hardware_closure']}." if r.get("external") else ""
        L.append(f"| **{r['id']}** {r['title']}{ext} | {r['kind']} | {_state_cell(r)} | " + " | ".join(cells) + " |")
    L += ["", "## Gaps", ""]
    if not d["gaps"]:
        L.append("None.")
    order = ["lean_frozen_statement_changed", "lean_approval", "lean_failing", "lean_statement_unapproved", "untraced_requirement", "orphan_check", "hardware_open", "external_not_hardware_verified", "performance_sim_only", "no_passing_evidence", "stale_evidence", "bad_item"]
    names = {"lean_frozen_statement_changed": "Lean: an approved statement changed (the statement is the specification)", "lean_approval": "Lean: approval file problems",
             "lean_failing": "Lean proofs that fail", "lean_statement_unapproved": "Lean proofs whose statement is not approved by a human",
             "untraced_requirement": "Requirements with no verification item", "orphan_check": "Orphan checks (trace to no requirement)",
             "hardware_open": "Requirements that depend on an external element and are not yet verified on hardware",
             "external_not_hardware_verified": "Depend on an external element, passing without hardware verification",
             "performance_sim_only": "Performance requirements verified in simulation only", "no_passing_evidence": "Requirements with no passing evidence",
             "stale_evidence": "Stale evidence", "bad_item": "Malformed entries"}
    for t in order:
        xs = [x for x in d["gaps"] if x["type"] == t]
        if xs:
            L += [f"### {names[t]}", ""] + [f"- `{x['id']}`: {x['text']}" for x in xs] + [""]
    L += ["## Requirements in full", ""]
    for r in d["requirements"]:
        L += [f"### {r['id']}: {r['title']}", "", f"- Kind: {r['kind']}; state: {_state_cell(r)}; specification status: {r.get('spec_status', 'unspecified')}."]
        if r.get("source"):
            L.append(f"- Source: `{r['source']}`")
        if r.get("text"):
            L.append(f"- {r['text']}")
        pf = r.get("performance")
        if pf:
            L.append(f"- Bound: {pf['quantity']} {_opw(pf['op'])} {pf['bound']} {pf['unit']}; condition: {pf['condition']}.")
        if r.get("external"):
            L.append(f"- External element: {r['external']}. Hardware verification: {r['hardware_closure']}.")
        for iid in r["items"]:
            i = items[iid]
            ev = i.get("evidence")
            where = f" [evidence]({_link(out_dir, ev['file'])})" if ev and ev.get("exists") else ""
            extra = f" ({i['stale_because']})" if i.get("stale_because") else ""
            L.append(f"  - {LABEL[i['method']]}{' / ' + i['instrument'] if i.get('instrument') else ''}: **{MARK[i['status']]}**, {i['title'] or i['id']}: {i['detail']}{extra}.{where}")
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def _opw(op: str) -> str:
    return {"le": "at most", "ge": "at least", "lt": "below", "gt": "above", "eq": "equal to"}.get(op, op)


CSS = """:root{--bg:#fff;--fg:#111;--mut:#555;--line:#c9c9c9;--ok:#111;--bad:#b00020;--soft:#f2f2f2}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111;--fg:#eee;--mut:#aaa;--line:#444;--ok:#eee;--bad:#ff8a80;--soft:#1c1c1c}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}main{max-width:1200px;margin:0 auto;padding:16px}
h1{font-size:1.4rem}h2{font-size:1.15rem;margin-top:2rem}.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top}th{background:var(--soft)}
.pass{font-weight:600}.fail{color:var(--bad);font-weight:700}.not_run,.stale,.bounded,.unapproved{color:var(--mut);font-style:italic}.gap{border-left:3px solid var(--fg);padding-left:8px}
a{color:inherit}code{font-size:12px}.mut{color:var(--mut)}"""


def render_html(d: dict, out_dir: Path) -> str:
    E = html.escape
    items = {i["id"]: i for i in d["items"]}
    h = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>{E(d['design'])} traceability</title><style>{CSS}</style></head><body><main>",
         f"<h1>{E(d['design'])}: specification to evidence</h1><p class=mut>{E(FRAMING)}</p><p><b>Summary.</b> {E(d['summary']['line'])}</p>",
         "<h2>Matrix</h2><div class=wrap><table><thead><tr><th>Requirement<th>Kind<th>State" + "".join(f"<th>{E(COL[m])}" for m in METHODS) + "</tr></thead><tbody>"]
    for r in d["requirements"]:
        cells = []
        for m in METHODS:
            parts = []
            for iid in r["items"]:
                i = items[iid]
                if i["method"] != m:
                    continue
                ev = i.get("evidence")
                lab = E(i["id"].split(":")[-1][:28]) + (f" <span class=mut>[{E(i['instrument'])}]</span>" if i.get("instrument") else "")
                lab = f"<a href='{E(_link(out_dir, ev['file']))}'>{lab}</a>" if ev and ev.get("exists") else lab
                extra = ""
                if i["method"] == "formal_lean":
                    extra = " <span class=mut>[" + E(_tag(i).split("[", 1)[1].rstrip("]")) + "]</span>" if "[" in _tag(i) else ""
                parts.append(f"<span class={i['status']}>{MARK[i['status']]}</span> {lab}{extra}")
            cells.append("<td>" + "<br>".join(parts))
        ext = f"<br><span class=mut>Depends on: {E(r['external'])}; hardware verification {r['hardware_closure']}.</span>" if r.get("external") else ""
        h.append(f"<tr><th><b>{E(r['id'])}</b> {E(r['title'])}{ext}<td>{r['kind']}<td><span class={'pass' if r['state'] == 'verified' else r['state']}>{E(_state_cell(r))}</span>" + "".join(cells) + "</tr>")
    h.append("</tbody></table></div><h2>Gaps</h2>")
    if not d["gaps"]:
        h.append("<p>None.</p>")
    for x in d["gaps"]:
        h.append(f"<p class=gap><code>{E(str(x['id']))}</code> {E(x['type'].replace('_', ' '))}: {E(x['text'])}</p>")
    h.append("<h2>Requirements in full</h2>")
    for r in d["requirements"]:
        pf = r.get("performance")
        h.append(f"<h3>{E(r['id'])}: {E(r['title'])}</h3><p>{E(r.get('text', ''))}" + (f" Bound: {E(pf['quantity'])} {_opw(pf['op'])} {E(str(pf['bound']))} {E(pf['unit'])}; condition: {E(pf['condition'])}." if pf else "") + "</p><ul>")
        for iid in r["items"]:
            i = items[iid]
            ev = i.get("evidence")
            a = f" <a href='{E(_link(out_dir, ev['file']))}'>evidence</a>" if ev and ev.get("exists") else ""
            h.append(f"<li>{E(LABEL[i['method']])}: <span class={i['status']}>{MARK[i['status']]}</span> {E(i['title'] or i['id'])}: {E(str(i['detail']))}{a}</li>")
        h.append("</ul>")
    h.append("</main></body></html>")
    return "".join(h)


def render_project_md(all_: dict) -> str:
    L = ["# Specification to evidence: every design", "",
         "<!-- Generated by `python -m flow.trace_v1 write` (brief 116). Do not edit. -->", "", all_["framing"], "",
         "| Design | Summary | Matrix |", "|---|---|---|"]
    for d in all_["designs"]:
        L.append(f"| `{d['design']}` | {d['summary']['line']} | [matrix](../{d['path']}/verif/matrix.md) ([html](../{d['path']}/verif/matrix.html)) |")
    L += ["", "## Gaps by design", ""]
    for d in all_["designs"]:
        c = d["summary"]["gap_counts"]
        L.append(f"- `{d['design']}`: " + (", ".join(f"{n} {k.replace('_', ' ')}" for k, n in sorted(c.items())) or "none"))
    return "\n".join(L) + "\n"


def render_project_html(all_: dict) -> str:
    E = html.escape
    h = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Specification to evidence</title><style>{CSS}</style></head><body><main><h1>Specification to evidence: every design</h1>",
         f"<p class=mut>{E(all_['framing'])}</p><div class=wrap><table><thead><tr><th>Design<th>Summary<th>Matrix</tr></thead><tbody>"]
    for d in all_["designs"]:
        h.append(f"<tr><th>{E(d['design'])}<td>{E(d['summary']['line'])}<td><a href='../{E(d['path'])}/verif/matrix.html'>matrix</a></tr>")
    h.append("</tbody></table></div></main></body></html>")
    return "".join(h)


def outputs(designs: list[Path], lean: str = "recorded") -> dict[Path, str]:
    all_ = collect_all(designs, lean)
    out: dict[Path, str] = {}
    for d, dp in zip(all_["designs"], designs):
        od = dp / "verif"
        out[od / "matrix.md"] = render_md(d, od)
        out[od / "matrix.html"] = render_html(d, od)
    out[ROOT / "docs" / "traceability_matrix.md"] = render_project_md(all_)
    out[ROOT / "docs" / "traceability_matrix.html"] = render_project_html(all_)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check", "write", "pin", "show", "lean-record", "lean-statement"])
    ap.add_argument("designs", nargs="*")
    ap.add_argument("--lean", choices=["recorded", "live", "auto"], default=None,
                    help="where a formal_lean item's build status comes from (default: recorded for write and check, auto for show)")
    a = ap.parse_args(argv)
    if a.cmd == "lean-statement":
        from flow import lean_tier
        if len(a.designs) != 2:
            print("usage: lean-statement DESIGN ITEM-ID")
            return 2
        d = ROOT / a.designs[0] if not Path(a.designs[0]).is_absolute() else Path(a.designs[0])
        its = [i for i in load(d)["verification"] if i["id"] == a.designs[1] and i.get("method") == "formal_lean"]
        if not its:
            print("no such formal_lean item")
            return 2
        print(lean_tier.statement_report(d, its[0]))
        return 0
    ds = [(ROOT / x if not Path(x).is_absolute() else Path(x)) for x in a.designs] or v1_designs()
    if a.cmd == "lean-record":
        from flow import lean_tier
        if not lean_tier.toolchain_available():
            print("the Lean toolchain (lake) is not installed; install elan, or run this where it is")
            return 2
        items = lean_tier.lean_items([load(d) for d in ds])
        for project in sorted({(i["lean"].get("project", lean_tier.DEFAULT_PROJECT)) for i in items}):
            print("wrote", lean_tier.write_record(items, project))
        return 0
    if a.cmd == "pin":
        for d in ds:
            print("wrote", write_pins(d))
        return 0
    if a.cmd == "check":
        bad = 0
        for d in ds:
            for p in gate(d, a.lean or "recorded"):
                print(f"{d.name}: {p}")
                bad = 1
        print("traceability gate:", "FAIL" if bad else "ok")
        return bad
    if a.cmd == "show":
        for d in ds:
            c = collect(d, a.lean or "auto")
            print(c["design"], "-", c["summary"]["line"])
            for x in c["gaps"]:
                print("  ", x["type"], x["id"], "-", x["text"])
        return 0
    for p, t in outputs(ds, a.lean or "recorded").items():
        p.write_text(t)
        print("wrote", rel(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
