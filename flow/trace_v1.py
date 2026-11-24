#!/usr/bin/env python3
"""Spec-to-evidence traceability, schema v1 (brief 116).

    python -m flow.trace_v1 check  [DESIGN ...]      gate: orphan checks, untraced requirements, bad references (exit 1)
    python -m flow.trace_v1 write  [DESIGN ...]      write verif/matrix.md and verif/matrix.html per design and docs/traceability_matrix.{md,html}
    python -m flow.trace_v1 pin    DESIGN            write verif/evidence_pins.yaml (what each checked file was when its evidence was recorded)
    python -m flow.trace_v1 show   DESIGN            the one-line thoroughness summary and the gaps
    python -m flow.trace_v1 lean-record [DESIGN ...] rebuild the Lean project with `lake build` and write its hash-pinned build record (brief 125; needs the toolchain)
    python -m flow.trace_v1 lean-statement DESIGN ITEM   print the Lean statement and hashes a human reads before approving it (writes nothing)
    python -m flow.trace_v1 agreement-hash DESIGN [REQ]  print the text hash an agreement in verif/agreements.yaml pins (writes nothing; brief 143a)
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
        evidence: {file: results/x/*.json, reader: json|text|junit|gates|exists|mutation, field: a.b.c, regex: ..., tests: [stem::name]}
        pass_when: [{field: a.b, op: eq, value: 0}]    # non-measuring items; a measuring item is judged against its requirement's bound
        checks: [designs/x/rtl/a.sv]                   # the RTL/spec this evidence is about (staleness)
        build: designs/x/variant/build.yaml            # optional: the build the evidence ran; its sources, constraints and IP scripts join `checks` (brief 143a)
        written_by: implementing_agent | independent_bench | human   # test items; unmarked counts as the implementing agent's own (brief 143a)
        bounded: {depth: 24}                           # formal BMC only
        rigour: [designs/x/verif/formal/a.sby]         # formal: SymbiYosys jobs judged by flow/formal_rigour.py (brief 143c): pass only if every assertion is proved with its antecedent reached
        planned: "brief 112"                           # a hook for evidence that does not exist yet
        reviewer: name, reviewer_kind: human|agent, date: YYYY-MM-DD   # review
        lean: {module: Gray.Spec, theorem: Gray.gray_step, project: formal/lean}                                  # formal_lean (brief 125)
        rtl_link: {kind: rtl_generated|transcription_tested|transcription_untested|model_only,                     # how the Lean model meets the RTL
                   source: [{file: designs/x/rtl/a.sv, lines: "77-82", commit: <sha, optional>}], transcribed_in: Gray/Spec.lean,
                   crosscheck: {file: formal/lean/Gray/CrossCheck.lean, reference: "what independent thing it is compared with"}}

Agreement, reviews and waivers are records a human owns (flow/trace_records.py, brief 143a); the plan cannot claim them. A formal_lean statement is approved only by a human, in ``verif/lean_approvals.yaml`` (never in this file; see flow/lean_tier.py).
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

try:
    from flow import trace_records as TR
except ModuleNotFoundError:  # run as `python flow/trace_v1.py` with only flow/ on sys.path (brief 153's guard test)
    import trace_records as TR  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_V1 = "fpga-design-agent/testplan/v1"
SCHEMA_V0 = "fpga-design-agent/testplan/v0"
KINDS = ("functional", "performance", "interface", "safety")
METHODS = ("sim_test", "uvm_test", "assertion", "formal", "formal_lean", "coverage_bin", "timing", "sim_measurement", "board_measurement", "review")
MEASURING = ("timing", "sim_measurement", "board_measurement")
INSTRUMENTS = ("eye_scan", "jtag_registers", "sysmon", "ila_capture", "latency_loop", "optical_ddm", "external_equipment")
STATUSES = ("pass", "fail", "not_run", "not_in_run", "skipped", "stale", "bounded", "unapproved")
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
    for p in sorted((ROOT / "arith").glob("*/verif/testplan.yaml")):          # brief 139b: the arithmetic library's functions
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
        plan0 = upgrade_v0(design, raw)
        _add_goal_requirements(design, plan0)
        return plan0
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
    _add_goal_requirements(design, plan)
    return plan


def _add_goal_requirements(design: Path, plan: dict[str, Any]) -> None:
    """Brief 159: the typed goals of ``<design>/spec.yaml goals:`` (``agent.graph.goals``) become ``performance`` requirements
    ``GOAL-<metric>[-<name>]`` unless the plan already defines that id. A verification item must still trace to each (until one does, the
    goal is an untraced requirement, a gate gap): a goal is never counted as verified because it was written down."""
    sp = design / "spec.yaml"
    if not sp.is_file():
        return
    from flow import goals as G
    try:
        spec = yaml.safe_load(sp.read_text()) or {}
        reqs = G.requirements(spec) if isinstance(spec, dict) and spec.get("goals") else []
    except (G.GoalError, yaml.YAMLError) as e:
        raise PlanError(f"{sp}: {e}")
    have = {r.get("id") for r in plan["requirements"]}
    plan["requirements"] += [r for r in reqs if r["id"] not in have]


def legacy_items(design: Path, raw: dict) -> list[dict]:
    rec = raw.get("evidence_record") or f"results/04f/{design.name}_verif_gates.json"
    try:
        from flow import sources
    except ImportError:                       # run as a script: flow/ itself is on sys.path
        import sources                     # type: ignore[no-redef]
    rtl = [str(p.relative_to(ROOT)) for p in sources.design_rtl(design)]       # every language (brief 153)
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
FRESH_DIR: Path | None = None      # brief 143d: when set, `resolve` looks for the evidence in this directory of fresh records (mirroring repository paths)


def resolve(pattern: str) -> Path | None:
    """A repo-relative path or glob; the last match in sorted order (run directories are time stamps)."""
    hits = sorted(glob.glob(str((FRESH_DIR or ROOT) / pattern)))
    return Path(hits[-1]) if hits else None


def rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return p.resolve().as_posix()


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


def _junit(p: Path) -> dict[str, str]:
    """Test name to "pass", "fail" or "skipped" as recorded in the JUnit file (brief 138: a skip is not a failure)."""
    out: dict[str, str] = {}
    for tc in ET.parse(p).getroot().iter("testcase"):
        stem = (tc.get("classname") or "").split(".")[-1]
        tags = {c.tag for c in tc}
        out[f"{stem}::{tc.get('name')}"] = "fail" if tags & {"failure", "error"} else "skipped" if "skipped" in tags else "pass"
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
    if item["method"] == "review":               # brief 143a: a review passes only through its record in verif/reviews.yaml
        res.update(TR.review_status((cache.get("reviews") or {}).get(item["id"]), ROOT))
        p = resolve(ev["file"]) if ev.get("file") else None
        res["evidence"] = {"file": rel(p), "exists": True} if p else None
        return res
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
            # Brief 138: failed (present and failed) is `fail`; a name absent from the recorded run, or a `stem::*` that matches nothing, is `not_in_run`
            # (the evidence predates the test); skipped in the run is `skipped`. Neither of the last two is a failure.
            missing = [t for t in want if t not in runs] + ([t for t in ev.get("tests") or [] if t.endswith("::*") and not any(k.startswith(t[:-1]) for k in runs)])
            bad = [t for t in want if runs.get(t) == "fail"]
            skipped = [t for t in want if runs.get(t) == "skipped"]
            npass = sum(1 for t in want if runs.get(t) == "pass")
            status = "fail" if bad else "not_in_run" if missing else "skipped" if skipped else "pass" if want else "not_in_run"
            parts = ([f"failed: {', '.join(bad)}"] if bad else []) + ([f"not in the recorded run: {', '.join(missing)}"] if missing else []) \
                + ([f"skipped in the recorded run: {', '.join(skipped)}"] if skipped else [])
            res.update(status=status, value=f"{npass} of {len(want) + sum(1 for t in missing if t.endswith('::*'))} tests passed",
                       detail="; ".join(parts) or f"{len(want)} test(s) passed in the recorded run")
            return res
        if reader == "gates":
            g = cache.setdefault(("json", str(p)), json.loads(p.read_text()))
            return _gates(item, ev, g, res)
        if reader == "mutation":            # brief 143b: a mutation-score record judged against a `mutation_floor` (flow/mutation_score.py)
            from flow import mutation_score
            return mutation_score.judge(item, req_by_id, p, res, ROOT)
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


def effective_checks(it: dict) -> list[str]:
    """The files a piece of evidence is about: the item's `checks`, plus, for an item that ran a build (`build: path/to/build.yaml`), the build file and every
    source, constraint and IP script it lists, so that staleness covers what was actually built and tested (brief 143a). Duplicates dropped, order kept."""
    out = list(it.get("checks") or [])
    b = it.get("build")
    if b:
        out.append(b)
        try:
            y = yaml.safe_load((ROOT / b).read_text()) or {}
        except (OSError, yaml.YAMLError):
            y = {}
        for k in ("sources", "constraints", "ip_tcl"):
            out += [x for x in (y.get(k) or []) if isinstance(x, str)]
    return list(dict.fromkeys(out))


def compute_pins(design: Path) -> dict:
    """For each item with `checks`: the evidence file's hash and the hash of every checked file *as of the commit that last changed the
    evidence file* (the working tree where the evidence is not committed yet). A checked file that has changed since is why the
    evidence is stale. Needs git history; the collector itself reads only the pins, so it is deterministic."""
    plan = load(design)
    out: dict[str, Any] = {}
    for it in plan["verification"]:
        ev = it.get("evidence") or {}
        p = resolve(ev["file"]) if ev.get("file") else None
        if p is None or not effective_checks(it):
            continue
        er = rel(p)
        clean = _git("status", "--porcelain", "--", er)
        commit = (ev.get("run_commit") or _git("log", "-1", "--format=%H", "--", er) or "").strip()   # run_commit: the commit the run was made at
        use_tree = (clean is None or clean.strip() != "" or not commit) and not ev.get("run_commit")
        checks = {}
        for c in effective_checks(it):
            cp = ROOT / c
            checks[c] = (sha(cp) if cp.exists() else "absent") if use_tree else _sha_at(commit, c)
        out[it["id"]] = {"evidence": er, "evidence_sha256": sha(p), "checks": checks}
    return out


def write_pins(design: Path) -> Path:
    p = pins_path(design)
    head = ("# Generated by `python -m flow.trace_v1 pin` (brief 116); do not edit.\n"
            "# For each item: the evidence file's hash, and the hash of every file the evidence is about as of the commit that last changed\n"
            "# the evidence. The collector compares them with the files today: a difference marks the evidence stale.\n")
    new = compute_pins(design)
    old = load_pins(design)
    kept: list[str] = []
    for iid, pin in new.items():
        o = old.get(iid)
        # a pin is not moved forward unless the evidence itself changed: re-pinning old evidence to today's tree would make it look fresh (brief 143a)
        if o and o.get("evidence_sha256") == pin["evidence_sha256"]:
            for f, h in pin["checks"].items():
                if f in (o.get("checks") or {}) and o["checks"][f] != h:
                    pin["checks"][f] = o["checks"][f]
                    kept.append(f"{iid}: {f}")
    p.write_text(head + yaml.safe_dump({"pins": new}, sort_keys=True, width=140))
    for k in kept:
        print(f"pin kept (evidence unchanged, file changed since; the evidence stays stale until it is re-recorded): {k}")
    return p


def staleness(item: dict, res: dict, pins: dict) -> str | None:
    if not effective_checks(item) or not (res.get("evidence") or {}).get("exists"):
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


def collect(design: Path, lean: str = "recorded", fresh: Path | None = None) -> dict[str, Any]:
    """``lean``: where a formal_lean item's build status comes from (see flow/lean_tier.py): the committed record, ``lake build`` now, or auto.
    ``fresh``: a directory of fresh records (flow/fresh_evidence.py). Verdicts still come from the committed records; each item also gets
    ``fresh = {state, detail}`` with state ``differs`` (committed record differs from the fresh run), ``agrees`` or ``not_rerun`` (brief 143d)."""
    plan = load(design)
    reqs = plan["requirements"]
    req_by_id = {r["id"]: r for r in reqs}
    pins = load_pins(design)
    cache: dict = {}
    from flow import lean_tier
    lean_tier.prime(plan, cache)
    policy = TR.load_policy(ROOT / "flow" / "method_mix_policy.yaml")
    cache["reviews"] = TR.load_reviews(design)[0]
    agreements = TR.load_agreements(design)[0]
    results = []
    for it in plan["verification"]:
        r = lean_tier.judge_lean(it, design, lean, cache) if it.get("method") == "formal_lean" else judge(it, req_by_id, cache)
        r["requirements"] = list(it.get("requirements") or [])
        r["checks"] = effective_checks(it)
        if it.get("bounded") is not None:
            r["bounded"] = it["bounded"]
        r["written_by"] = it.get("written_by")
        if r["status"] == "pass":
            why = staleness(it, r, pins)
            if why:
                r["status"], r["stale_because"] = "stale", why
            elif it.get("bounded") is not None:
                r["status"] = "bounded"
        if it.get("rigour"):                    # brief 143c: a vacuous, unreachable-cover or unjustified-bounded proof is not a pass
            from flow import formal_rigour
            formal_rigour.apply_to_item(it, r)
        results.append(r)
    by_req: dict[str, list] = {r["id"]: [] for r in reqs}
    for r in results:
        for q in r["requirements"]:
            if q in by_req:
                by_req[q].append(r)
    rows = []
    for q in reqs:
        items = by_req[q["id"]]
        rows.append(rollup(q, items, policy, TR.agreement_of(q, agreements), design))
    gaps = find_gaps(plan, rows, results, req_by_id, design)
    if fresh is not None:
        from flow import fresh_evidence
        fresh_evidence.annotate(plan, results, design, Path(fresh))
        for r in rows:
            r["fresh_differs"] = sum(1 for i in results if r["id"] in i["requirements"] and (i.get("fresh") or {}).get("state") == "differs")
    return {"design": plan["design"], "path": rel(design), "source_schema": plan["source_schema"], "requirements": rows, "items": results,
            "gaps": gaps, "summary": summarise(rows, results, gaps), "notes": plan.get("notes", "")}


def _no_pass_state(st: list[str]) -> str:
    """With no passing item: skipped or not-in-the-recorded-run (brief 138) if an item says so, else not_run. All three count as no passing evidence."""
    return "not_in_run" if "not_in_run" in st else "skipped" if "skipped" in st else "not_run"


def rollup(q: dict, items: list[dict], policy: dict | None = None, agreement: dict | None = None, design: Path | None = None) -> dict:
    st = [i["status"] for i in items]
    meas = [i for i in items if i["method"] in MEASURING and i.get("judged_by_bound")]
    perf = q.get("kind") == "performance" or bool(q.get("performance"))
    basis = None
    mix_ok, missing = TR.mix(q.get("kind"), items, policy)
    if "fail" in st:
        state = "fail"
    elif perf:
        ok = [i for i in meas if i["status"] == "pass"]
        if ok and mix_ok:
            state = "verified"
            basis = ("board" if any(i["method"] == "board_measurement" for i in ok) else
                     "timing" if any(i["method"] == "timing" for i in ok) else "simulation")
        elif any(i["status"] == "stale" for i in meas):
            state = "stale"
        elif any(i["status"] == "pass" for i in items):
            state = "no_measurement"
        else:
            state = _no_pass_state(st)
    else:
        if "pass" in st:
            state = "verified" if mix_ok else "partially_verified"
        elif "bounded" in st:
            state = "bounded"
        elif "stale" in st:
            state = "stale"
        elif "unapproved" in st:
            state = "unapproved"
        else:
            state = _no_pass_state(st)
    waived: list[dict] = []
    if state in ("partially_verified", "no_measurement") and missing and design is not None:     # a waiver in effect covers every missing group
        live, _dead = TR.active_waivers(design, q["id"], q.get("kind"))
        cover = {g for w in live for g in w["waives"]}
        if set(missing) <= cover:
            waived = [w for w in live if set(w["waives"]) & set(missing)]
            state = "waived"
    ext = q.get("external")
    hw_done = any(i["method"] == "board_measurement" and i["status"] == "pass" for i in items)
    hw_methods = sorted({i["method"] for i in items if i["status"] == "pass"})
    row = {k: q[k] for k in ("id", "kind", "title", "text", "source", "spec_status", "performance", "external", "spec") if k in q}
    passing = [i for i in items if i["status"] == "pass"]
    lean_only = bool(passing) and all(i["method"] == "formal_lean" and (i.get("lean") or {}).get("rtl_link") != "rtl_generated" for i in passing)
    row["lean_transcription_only"] = lean_only
    # a verified requirement whose every passing item is a Lean proof with a delegated (not human) statement acceptance (brief 135)
    row["rests_on_delegated"] = bool(passing) and all(i["method"] == "formal_lean" and (i.get("lean") or {}).get("approver_kind") == "agent_delegated" for i in passing)
    ag = agreement or {"state": "draft", "note": "", "by": None, "date": None}
    row.update(agreement=ag["state"], agreement_note=ag["note"], agreement_by=ag["by"], agreement_date=ag["date"], agreement_dropped=bool(ag.get("dropped")))
    row.update(mix_satisfied=None if not ((policy or {}).get("kinds") or {}).get(q.get("kind")) else mix_ok,
               missing_methods=[policy["groups"][g]["label"] for g in missing] if policy and state in ("partially_verified", "no_measurement", "waived") else [],
               waivers=[{"id": w.get("id"), "waives": w["waives"], "reason": w.get("reason"), "expires": str(w.get("expires")), "approver_kind": w["approver_kind"],
                         "by": w.get("approved_by") or w.get("accepted_by")} for w in waived],
               own_tests_only=TR.own_tests_only(items))
    row.update(state=state, basis=basis, stale_items=sum(1 for x in st if x == "stale"), items=[i["id"] for i in items], passing_methods=hw_methods,
               hardware_verified=hw_done, hardware_only=bool(ext),
               hardware_closure=None if not ext else ("done" if hw_done else "open"))
    return row


def _names(results: list, rid: str, status: str) -> str:
    """The detail of this requirement's items with the given status, so the gap list names the missing or skipped tests."""
    return "; ".join(i["detail"] for i in results if rid in (i.get("requirements") or []) and i["status"] == status)


def find_gaps(plan: dict, rows: list, results: list, req_by_id: dict, design: Path | None = None) -> list[dict]:
    g: list[dict] = []
    for r in rows:
        if not r["items"]:
            g.append({"type": "untraced_requirement", "id": r["id"], "text": "no verification item traces to this requirement", "gate": True})
        elif r["state"] == "partially_verified":
            g.append({"type": "method_mix_missing", "id": r["id"], "text": f"{r['kind']} requirement: passes, but the required mix of methods is not met; lacks " + "; ".join(r["missing_methods"]), "gate": False})
        elif r["state"] in ("not_run", "not_in_run", "skipped", "no_measurement", "stale", "bounded", "fail"):
            g.append({"type": "no_passing_evidence", "id": r["id"], "state": r["state"], "text": {
                "not_run": "no passing evidence", "not_in_run": "no passing evidence: " + _names(results, r["id"], "not_in_run"),
                "skipped": "no passing evidence: " + _names(results, r["id"], "skipped"), "no_measurement": "a performance requirement with no measured value inside the bound",
                "stale": "its evidence is stale", "bounded": "only a bounded formal result", "fail": "an item fails"}[r["state"]], "gate": False})
        for w in r.get("waivers") or []:
            g.append({"type": "waiver_in_effect", "id": r["id"], "text": f"waiver {w['id']} ({w['approver_kind']}: {w['by']}) covers {', '.join(w['waives'])} until {w['expires']}: {w['reason']}", "gate": False})
        if r.get("own_tests_only") and r["state"] != "fail":
            g.append({"type": "own_tests_only", "id": r["id"], "text": "everything that passes is a test the implementing agent wrote (or whose author is not recorded); the house rule is that these never count alone", "gate": False})
        if r.get("agreement_dropped"):
            g.append({"type": "agreement_dropped", "id": r["id"], "text": r["agreement_note"] + "; it is a draft again until agreed anew", "gate": False})
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
    if design is not None:
        for t in TR.agreement_problems(design, plan["requirements"]):
            g.append({"type": "record_problem", "id": design.name, "text": t, "gate": True})
        for t in TR.review_problems(design, plan["verification"], ROOT):
            g.append({"type": "record_problem", "id": design.name, "text": t, "gate": True})
        pol = TR.load_policy(ROOT / "flow" / "method_mix_policy.yaml")
        for t in TR.waiver_problems(design, plan["requirements"], set((pol or {}).get("groups") or {})):
            g.append({"type": "record_problem", "id": design.name, "text": t, "gate": True})
        for q in plan["requirements"]:
            for w in TR.active_waivers(design, q["id"], q.get("kind"))[1]:
                g.append({"type": "waiver_expired", "id": q["id"], "text": f"waiver {w.get('id')} expired on {w.get('expires')} and waives nothing", "gate": False})
    for t in TR.author_problems(plan["verification"]):
        g.append({"type": "bad_item", "id": t.split(":")[0], "text": t.split(": ", 1)[1], "gate": True})
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
        if it.get("build") and not (ROOT / it["build"]).exists():
            g.append({"type": "bad_item", "id": it.get("id"), "text": f"build file {it['build']} does not exist", "gate": True})
        for c in effective_checks(it):
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
    lean = {"items": len(lean_r), "approved": sum(1 for i in lean_r if (i.get("lean") or {}).get("approver_kind") == "human"),
            "delegated": sum(1 for i in lean_r if (i.get("lean") or {}).get("approver_kind") == "agent_delegated"),
            "statement_not_approved": sum(1 for i in lean_r if i["status"] == "unapproved"),
            "by_status": {k: sum(1 for i in lean_r if i["status"] == k) for k in STATUSES if any(i["status"] == k for i in lean_r)},
            "by_tier": {t: sum(1 for i in lean_r if (i.get("lean") or {}).get("tier") == t) for t in ("kernel_only", "compiled_decision_procedure", "unsound")},
            "by_rtl_link": {t: sum(1 for i in lean_r if (i.get("lean") or {}).get("rtl_link") == t) for t in
                            ("rtl_generated", "transcription_tested", "transcription_untested", "model_only")},
            "build_sources": sorted({(i.get("lean") or {}).get("build_source") or "none" for i in lean_r})}
    s = {"requirements": len(rows), "by_kind": kinds, "lean": lean, "by_state": states, "items": len(results), "by_method": meth, "gap_counts": gt,
         "verified_on_delegated": sum(1 for r in rows if r["state"] == "verified" and r.get("rests_on_delegated")), "external": len(ext), "external_hardware_done": sum(1 for r in ext if r["hardware_closure"] == "done"),
         "performance_board": sum(1 for r in rows if r["kind"] == "performance" and r["basis"] == "board"),
         "performance_sim_only": sum(1 for r in rows if r["kind"] == "performance" and r["basis"] == "simulation"),
         "performance_timing": sum(1 for r in rows if r["kind"] == "performance" and r["basis"] == "timing"),
         "spec_agreed": sum(1 for r in rows if r.get("agreement") == "agreed_human"),
         "agreement": {k: sum(1 for r in rows if r.get("agreement") == k) for k in ("draft", "agreed_human", "agreed_delegated")},
         "own_tests_only": sum(1 for r in rows if r.get("own_tests_only")),
         "waived": sum(1 for r in rows if r["state"] == "waived"),
         "human_reviews": sum(1 for i in results if i["method"] == "review" and i.get("reviewer_kind") == "human" and i["status"] == "pass"),
         "delegated_reviews": sum(1 for i in results if i["method"] == "review" and i.get("reviewer_kind") == "agent_delegated" and i["status"] == "pass")}
    s["line"] = summary_line(s)
    return s


def summary_line(s: dict) -> str:
    kinds = ", ".join(f"{n} {k}" for k, n in s["by_kind"].items() if n)
    st = s["by_state"]
    ver = st.get("verified", 0)
    dele = s.get("verified_on_delegated", 0)
    bits = [f"{s['requirements']} requirements ({kinds}); {ver} verified" + (f", of which {dele} rest on delegated acceptances (the planner accepted the Lean statement on the owner's delegation; not human approvals)" if dele else "")]
    for k, lab in (("partially_verified", "partially verified (the required mix of methods is not met)"), ("waived", "verified under a waiver"), ("bounded", "bounded only"), ("stale", "stale"), ("fail", "failing"), ("no_measurement", "performance with no measurement"), ("not_run", "with no passing evidence")):
        if st.get(k):
            bits.append(f"{st[k]} {lab}")
    nop = st.get("not_run", 0) + st.get("not_in_run", 0) + st.get("skipped", 0)      # brief 138: all three are "no passing evidence", none is failing
    if nop:
        why = [f"{st[k]} {lab}" for k, lab in (("not_in_run", "not in the recorded run"), ("skipped", "skipped in the recorded run")) if st.get(k)]
        bits.append(f"{nop} with no passing evidence" + (f" ({', '.join(why)})" if why else ""))
    if s["external"]:
        bits.append(f"{s['external_hardware_done']} of {s['external']} requirements that depend on an external element closed by hardware")
    if s["performance_board"] or s["performance_sim_only"] or s["performance_timing"]:
        bits.append(f"performance verified: {s['performance_board']} on the board, {s['performance_timing']} by post-route timing, {s['performance_sim_only']} in simulation only")
    a = s["agreement"]
    bits.append(f"{a['agreed_human']} of {s['requirements']} requirements agreed by a human, {a['agreed_delegated']} agreed on the owner's delegation (not human), {a['draft']} draft")
    if s["own_tests_only"]:
        bits.append(f"{s['own_tests_only']} resting only on the implementing agent's own tests")
    bits.append(f"{s['human_reviews']} human and {s['delegated_reviews']} delegated review(s) recorded")
    L = s["lean"]
    if L["items"]:
        ks, cd = L["by_tier"]["kernel_only"], L["by_tier"]["compiled_decision_procedure"]
        bits.append(f"{L['items']} Lean proof item(s) (all widths): {L['approved']} with a human-approved statement, {L.get('delegated', 0)} with a statement accepted on the owner's delegation (not a human approval), "
                    f"{L['statement_not_approved']} with statement not approved; "
                    f"{ks} kernel only, {cd} using a compiled decision procedure; build status from: {', '.join(L['build_sources'])}")
    return "; ".join(bits) + "."


def collect_all(designs: list[Path] | None = None, lean: str = "recorded", fresh: Path | None = None) -> dict[str, Any]:
    ds = designs if designs is not None else v1_designs()
    out = [collect(d, lean, fresh) for d in ds]
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
STATE_TEXT = {"verified": "verified", "partially_verified": "partially verified", "waived": "verified under a waiver", "fail": "FAILS", "not_run": "not run", "not_in_run": "not in the recorded run", "skipped": "skipped in the recorded run", "stale": "stale", "bounded": "bounded only", "no_measurement": "no measurement",
              "unapproved": "proved, statement not approved"}
MARK = {"pass": "pass", "fail": "FAIL", "not_run": "not run", "not_in_run": "not in the recorded run", "skipped": "skipped", "stale": "stale", "bounded": "bounded", "unapproved": "statement not approved"}


def _tag(i: dict) -> str:
    """The status of a cell item; a Lean proof also says its axiom tier, how the Lean model meets the RTL, and where the build status came from."""
    t = MARK[i["status"]] + (f" [{i['instrument']}]" if i.get("instrument") else "")
    if (i.get("fresh") or {}).get("state") == "differs":
        t += " [committed record differs from fresh run]"
    L = i.get("lean")
    if i["method"] == "formal_lean" and L:
        from flow import lean_tier as lt
        bits = [lt.TIER_TEXT.get(L.get("tier") or "", "no build"), lt.RTL_LINK_SHORT.get(L.get("rtl_link") or "", "no RTL link"), (L.get("build_source") or "").replace(" (not re-run)", "")]
        if i["status"] == "pass":
            bits.insert(0, lt.approval_short(L))
        t += " [" + "; ".join(b for b in bits if b) + "]"
    elif i["method"] in TR.AUTHORED:
        t += f" [{TR.AUTHOR_SHORT.get(i.get('written_by'), 'author not recorded')}]"
    elif i["method"] == "review" and i.get("reviewer_kind"):
        t += f" [{i['reviewer_kind'].replace('_', ' ')} review]"
    return t


def _link(from_dir: Path, target: str) -> str:
    return os.path.relpath(ROOT / target, from_dir).replace(os.sep, "/")


def _state_cell(r: dict) -> str:
    t = STATE_TEXT[r["state"]]
    if r["state"] in ("partially_verified", "no_measurement") and r.get("missing_methods"):
        t += "; lacks " + "; ".join(r["missing_methods"])
    if r["state"] == "waived":
        t += ": " + "; ".join(f"{w['id']} ({w['approver_kind']}, until {w['expires']})" for w in r["waivers"]) + "; lacks " + "; ".join(r["missing_methods"])
    if r.get("own_tests_only") and r["state"] != "fail":
        t += "; rests only on the implementing agent's own tests"
    if r["state"] == "verified" and r.get("external") and not r["hardware_verified"]:
        return "passes without hardware; hardware verification open"
    if r["state"] == "verified" and r["kind"] == "performance":
        t += f" ({'board-measured' if r['basis'] == 'board' else 'post-route timing' if r['basis'] == 'timing' else 'simulation only'})"
    if r["state"] == "verified" and r.get("stale_items"):
        t += f"; {r['stale_items']} item(s) stale"
    if r["state"] == "verified" and r.get("lean_transcription_only"):
        t += "; the Lean proof is of a transcription of the RTL, not of the RTL itself"
    if r.get("fresh_differs"):
        t += f"; {r['fresh_differs']} item(s): committed record differs from fresh run"
    if r["state"] == "verified" and r.get("rests_on_delegated"):
        t += "; rests on a delegated acceptance of the Lean statement, not a human approval"
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
          "`bounded` means a formal bounded model check only. A requirement is verified only when its passing items meet the method mix for its kind "
          "(`flow/method_mix_policy.yaml`); a test is marked with who wrote it, and a test whose author is not recorded counts as the implementing agent's own. "
          "Agreement comes only from `verif/agreements.yaml`, never from the testplan.", ""]
    L += ["| Requirement | Kind | Agreement | State | " + " | ".join(COL[m] for m in METHODS) + " |", "|---|---|---|---|" + "---|" * len(METHODS)]
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
        L.append(f"| **{r['id']}** {r['title']}{ext} | {r['kind']} | {TR.AGREEMENT_TEXT[r['agreement']]} | {_state_cell(r)} | " + " | ".join(cells) + " |")
    L += ["", "## Gaps", ""]
    if not d["gaps"]:
        L.append("None.")
    order = ["record_problem", "method_mix_missing", "own_tests_only", "waiver_in_effect", "waiver_expired", "agreement_dropped", "lean_frozen_statement_changed", "lean_approval", "lean_failing", "lean_statement_unapproved", "untraced_requirement", "orphan_check", "hardware_open", "external_not_hardware_verified", "performance_sim_only", "no_passing_evidence", "stale_evidence", "bad_item"]
    names = {"record_problem": "Agreement, review or waiver record problems", "method_mix_missing": "Requirements whose passing items do not meet the required method mix",
             "own_tests_only": "Requirements resting only on the implementing agent's own tests", "waiver_in_effect": "Waivers in effect", "waiver_expired": "Expired waivers (waive nothing)",
             "agreement_dropped": "Agreements dropped because the requirement text changed", "lean_frozen_statement_changed": "Lean: an approved statement changed (the statement is the specification)", "lean_approval": "Lean: approval file problems",
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
        L += [f"### {r['id']}: {r['title']}", "", f"- Kind: {r['kind']}; state: {_state_cell(r)}; agreement: {TR.AGREEMENT_TEXT[r['agreement']]}{(' (' + r['agreement_note'] + ')') if r.get('agreement_note') else ''}."]
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
.pass{font-weight:600}.fail{color:var(--bad);font-weight:700}.not_run,.not_in_run,.skipped,.stale,.bounded,.unapproved,.partially_verified,.no_measurement,.waived{color:var(--mut);font-style:italic}.gap{border-left:3px solid var(--fg);padding-left:8px}
a{color:inherit}code{font-size:12px}.mut{color:var(--mut)}"""


def render_html(d: dict, out_dir: Path) -> str:
    E = html.escape
    items = {i["id"]: i for i in d["items"]}
    h = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>{E(d['design'])} traceability</title><style>{CSS}</style></head><body><main>",
         f"<h1>{E(d['design'])}: specification to evidence</h1><p class=mut>{E(FRAMING)}</p><p><b>Summary.</b> {E(d['summary']['line'])}</p>",
         "<h2>Matrix</h2><div class=wrap><table><thead><tr><th>Requirement<th>Kind<th>Agreement<th>State" + "".join(f"<th>{E(COL[m])}" for m in METHODS) + "</tr></thead><tbody>"]
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
        h.append(f"<tr><th><b>{E(r['id'])}</b> {E(r['title'])}{ext}<td>{r['kind']}<td>{E(TR.AGREEMENT_TEXT[r['agreement']])}<td><span class={'pass' if r['state'] == 'verified' else r['state']}>{E(_state_cell(r))}</span>" + "".join(cells) + "</tr>")
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
    ap.add_argument("cmd", choices=["check", "write", "pin", "show", "lean-record", "lean-statement", "fresh", "agreement-hash"])
    ap.add_argument("designs", nargs="*")
    ap.add_argument("--lean", choices=["recorded", "live", "auto"], default=None,
                    help="where a formal_lean item's build status comes from (default: recorded for write and check, auto for show)")
    ap.add_argument("--fresh", default=None, metavar="DIR",
                    help="a directory of fresh records (python -m flow.fresh_evidence run ...): show and write mark items whose committed record differs from the fresh run; "
                         "write puts the marked matrices in DIR/matrices instead of the tree; the command `fresh` compares and exits 1 on a difference (brief 143d)")
    a = ap.parse_args(argv)
    if a.cmd == "fresh":
        from flow import fresh_evidence
        if not a.fresh:
            print("usage: fresh --fresh DIR [DESIGN ...]")
            return 2
        return fresh_evidence.main(["compare", "--fresh", a.fresh, *a.designs])
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
    if a.cmd == "agreement-hash":
        if not 1 <= len(a.designs) <= 2:
            print("usage: agreement-hash DESIGN [REQUIREMENT-ID]")
            return 2
        d = ROOT / a.designs[0] if not Path(a.designs[0]).is_absolute() else Path(a.designs[0])
        agr = TR.load_agreements(d)[0]
        for q in load(d)["requirements"]:
            if len(a.designs) == 2 and q["id"] != a.designs[1]:
                continue
            print(f"{q['id']}  {TR.req_hash(q)}  {TR.AGREEMENT_TEXT[TR.agreement_of(q, agr)['state']]}")
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
            c = collect(d, a.lean or "auto", Path(a.fresh) if a.fresh else None)
            print(c["design"], "-", c["summary"]["line"])
            for x in c["gaps"]:
                print("  ", x["type"], x["id"], "-", x["text"])
            for x in c["items"]:
                if (x.get("fresh") or {}).get("state") == "differs":
                    print("   committed record differs from fresh run:", x["id"], "-", x["fresh"]["detail"])
        return 0
    if a.fresh:
        fd = Path(a.fresh)
        all_ = collect_all(ds, a.lean or "recorded", fd)
        for d, dp in zip(all_["designs"], ds):
            od = fd / "matrices" / dp.name
            od.mkdir(parents=True, exist_ok=True)
            (od / "matrix.md").write_text(render_md(d, od))
            (od / "matrix.html").write_text(render_html(d, od))
            print("wrote", od / "matrix.md")
        return 0
    for p, t in outputs(ds, a.lean or "recorded").items():
        p.write_text(t)
        print("wrote", rel(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
