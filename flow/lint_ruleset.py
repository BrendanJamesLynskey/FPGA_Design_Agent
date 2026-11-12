#!/usr/bin/env python3
"""Check a design against FDA-HDL, the versioned HDL coding standard (brief 53; flow/hdl_rules.yaml,
docs/hdl_coding_standard.md).

    python3 flow/lint_ruleset.py designs/<d> [--gates build/base/gates.json] [--standards build/standards.json]
        [--no-verilator] [--json OUT]

Three sources of findings, each mapped to a rule:

- Verilator ``--lint-only -Wall`` on the build's sources (build.yaml) and the design's lint stubs (``lint/*.sv``);
- the Vivado findings in the build's ``gates.json`` (report_methodology, report_drc and report_cdc rule lists of every
  stage) at severity Warning or above;
- ``flow/standards_check.py``'s result (a rule that failed or could not run).

A finding is waived by an entry of ``lint/waivers.yaml`` whose ``rule`` is its rule id and whose ``match`` (a glob)
matches its key (glob with literal brackets, or ``re:<regex>``: ``verilator:CODE file:line``, ``vivado:RULE-ID@stage``, ``standards:STD-ID file:line``); the waiver
needs ``reason``, ``owner`` and ``date`` or it does not count. Each rule ends ``pass``, ``waived`` (every finding
waived), ``fail`` or ``not_run`` (its tool or report was not available). Exit 0 only if no rule failed and every rule
was evaluated: a run with a rule ``not_run`` prints INCOMPLETE and exits 1.
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    from flow.traceability import match_item
except ImportError:                                     # run as a script
    from traceability import match_item                        # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
RULES_FILE = Path(__file__).with_name("hdl_rules.yaml")
SEVERE = ("error", "critical warning", "warning")
_VL = re.compile(r"^%(Warning|Error)-?([A-Z0-9_]*):\s*(\S+?):(\d+):(?:\d+:)?\s*(.*)$")


def load_rules(path: Path = RULES_FILE) -> dict[str, Any]:
    return yaml.safe_load(path.read_text())


def rule_problems(rs: dict[str, Any]) -> list[str]:
    """The rule set's own shape: a name, a version, unique ids, a title, a rationale and at least one check per rule,
    and exactly one catch-all per tool."""
    out = []
    if not rs.get("standard") or not rs.get("version"):
        out.append("the rule set needs `standard` and `version`")
    seen = set()
    for r in rs.get("rules") or []:
        rid = r.get("id")
        if rid in seen:
            out.append(f"{rid}: id used twice")
        seen.add(rid)
        if len(str(r.get("rationale") or "").split()) < 6:
            out.append(f"{rid}: no rationale")
        if not r.get("title"):
            out.append(f"{rid}: no title")
        if not r.get("checks") or not any(r["checks"].get(k) for k in ("verilator", "vivado", "standards")):
            out.append(f"{rid}: maps to no tool check")
    for tool in ("verilator", "vivado", "standards"):
        n = sum(1 for r in rs.get("rules") or [] if "*" in ((r.get("checks") or {}).get(tool) or []))
        if n != 1:
            out.append(f"{tool}: {n} catch-all rules (need exactly one)")
    return out


def rule_for(rs: dict[str, Any], tool: str, code: str) -> str:
    """The rule a finding maps to: the first exact or glob match, the catch-all last."""
    catch = None
    for r in rs["rules"]:
        pats = (r.get("checks") or {}).get(tool) or []
        for p in pats:
            if p == "*":
                catch = catch or r["id"]
            elif p == code or fnmatch.fnmatchcase(code, p):
                return r["id"]
    return catch or "HDL-UNMAPPED"


# ---- finding sources ----------------------------------------------------------------------------------------------
def verilator_findings(design: Path) -> tuple[list[dict[str, Any]] | None, str]:
    """``(findings, note)``; findings is None when Verilator is not installed or the build sources cannot be read."""
    exe = shutil.which("verilator")
    if not exe:
        return None, "verilator is not on PATH"
    try:
        b = yaml.safe_load((design / "build.yaml").read_text())
    except (OSError, yaml.YAMLError) as e:
        return None, f"build.yaml unreadable: {e}"
    srcs = [f for g in b.get("sources") or [] for f in sorted(glob.glob(str(ROOT / g)))]
    stubs = sorted(str(p) for p in (design / "lint").glob("*.sv"))
    if not srcs:
        return None, "build.yaml lists no sources that exist"
    cmd = [exe, "--lint-only", "-Wall", "-Wno-fatal", "--top-module", str(b["top"]), *srcs, *stubs]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=600)
    out = []
    for line in (r.stderr or "").splitlines():
        m = _VL.match(line.strip())
        if not m:
            continue
        sev, code, f, ln, msg = m.groups()
        try:
            f = Path(f).resolve().relative_to(ROOT).as_posix()
        except ValueError:
            pass
        code = code or ("ERROR" if sev == "Error" else "WARNING")
        out.append({"tool": "verilator", "code": code, "key": f"verilator:{code} {f}:{ln}", "severity": sev.lower(),
                    "message": msg.strip()})
    note = "" if r.returncode == 0 or out else f"verilator exited {r.returncode}: {(r.stderr or '').strip()[:300]}"
    return out, note


def vivado_findings(gates: dict[str, Any]) -> list[dict[str, Any]]:
    """Rule findings at Warning or above from every stage's methodology, DRC and CDC lists (and the top-level copies)."""
    seen: dict[str, dict[str, Any]] = {}

    def take(stage: str, block: dict | None) -> None:
        for r in (block or {}).get("rules") or []:
            if str(r.get("severity", "")).lower() not in SEVERE:
                continue
            key = f"vivado:{r.get('rule')}@{stage}"
            if key not in seen:
                seen[key] = {"tool": "vivado", "code": str(r.get("rule")), "key": key, "severity": str(r.get("severity")),
                             "message": f"{r.get('description', '')} (x{r.get('count', 1)})"}
    for st, sd in (gates.get("stages") or {}).items():
        for k in ("methodology", "drc", "cdc"):
            take(st, sd.get(k) if isinstance(sd, dict) else None)
    for k in ("methodology", "drc", "cdc"):
        take("route", gates.get(k))
    return list(seen.values())


def standards_findings(std: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for r in std.get("rules") or []:
        if r.get("status") in ("fail", "not_run"):
            fs = r.get("findings") or [{"file": "-", "line": 0, "message": r.get("why_not_run", r["status"])}]
            for f in fs:
                out.append({"tool": "standards", "code": r["id"], "key": f"standards:{r['id']} {f.get('file')}:{f.get('line')}",
                            "severity": r["status"], "message": f.get("message", "")})
    return out


# ---- waivers ------------------------------------------------------------------------------------------------------
def load_waivers(design: Path) -> tuple[list[dict[str, Any]], list[str]]:
    p = design / "lint" / "waivers.yaml"
    if not p.is_file():
        return [], []
    try:
        ws = (yaml.safe_load(p.read_text()) or {}).get("waivers") or []
    except (yaml.YAMLError, AttributeError) as e:
        return [], [f"lint/waivers.yaml is not valid: {e}"]
    good, bad = [], []
    for i, w in enumerate(ws):
        miss = [k for k in ("rule", "match", "reason", "owner", "date") if not str((w or {}).get(k) or "").strip()]
        if miss:
            bad.append(f"lint/waivers.yaml entry {i}: no {', '.join(miss)}")
        else:
            good.append(w)
    return good, bad


def evaluate(design: Path, gates: Path | None, standards: Path | None, run_verilator: bool = True,
             rs: dict[str, Any] | None = None) -> dict[str, Any]:
    rs = rs or load_rules()
    findings: list[dict[str, Any]] = []
    ran = {"verilator": False, "vivado": False, "standards": False}
    notes = {}
    if run_verilator:
        vf, note = verilator_findings(design)
        if vf is not None:
            findings += vf
            ran["verilator"] = True
        if note:
            notes["verilator"] = note
    else:
        notes["verilator"] = "not run (--no-verilator)"
    if gates and gates.is_file():
        findings += vivado_findings(json.loads(gates.read_text()))
        ran["vivado"] = True
    else:
        notes["vivado"] = "no gates.json given or found"
    if standards and standards.is_file():
        findings += standards_findings(json.loads(standards.read_text()))
        ran["standards"] = True
    else:
        notes["standards"] = "no standards.json given or found"
    waivers, bad_waivers = load_waivers(design)
    for f in findings:
        f["rule"] = rule_for(rs, f["tool"], f["code"])
        f["waived_by"] = next((w for w in waivers if w["rule"] == f["rule"] and match_item(f["key"], str(w["match"]))), None)
    rules = []
    for r in rs["rules"]:
        tools = [t for t in ("verilator", "vivado", "standards") if (r.get("checks") or {}).get(t)]
        fs = [f for f in findings if f["rule"] == r["id"]]
        open_ = [f for f in fs if not f["waived_by"]]
        if r["id"] == "HDL-WAIVE-01" and bad_waivers:
            status = "fail"
        elif open_:
            status = "fail"
        elif fs:
            status = "waived"
        elif not any(ran[t] for t in tools):
            status = "not_run"
        else:
            status = "pass"
        rules.append({"id": r["id"], "title": r["title"], "status": status, "tools": tools,
                      "ran": [t for t in tools if ran[t]],
                      "findings": [{k: f[k] for k in ("key", "severity", "message")} for f in open_],
                      "waived": [{"key": f["key"], "reason": f["waived_by"]["reason"], "owner": f["waived_by"]["owner"],
                                  "date": str(f["waived_by"]["date"])} for f in fs if f["waived_by"]]})
    unused = [w for w in waivers if not any(f["waived_by"] is w for f in findings)]
    fails = [r["id"] for r in rules if r["status"] == "fail"]
    return {"standard": rs["standard"], "version": rs["version"], "design": design.name, "ran": ran, "notes": notes,
            "rules": rules, "bad_waivers": bad_waivers,
            "unused_waivers": [f"{w['rule']} {w['match']}" for w in unused],
            "counts": {s: sum(1 for r in rules if r["status"] == s) for s in ("pass", "waived", "fail", "not_run")},
            # a rule that could not be checked is not a pass: the result is complete only when every rule was evaluated
            "complete": not any(r["status"] == "not_run" for r in rules),
            "pass": not fails and not bad_waivers and not any(r["status"] == "not_run" for r in rules)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("design")
    ap.add_argument("--gates")
    ap.add_argument("--standards")
    ap.add_argument("--no-verilator", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    rel = lambda p: None if not p else (Path(p) if Path(p).is_absolute() else ROOT / p)
    rs = load_rules()
    probs = rule_problems(rs)
    if probs:
        print("rule set problems:\n  " + "\n  ".join(probs))
        return 2
    rep = evaluate(rel(a.design), rel(a.gates), rel(a.standards), not a.no_verilator, rs)
    print(f"{rep['standard']} v{rep['version']} on {rep['design']}: ran {', '.join(k for k, v in rep['ran'].items() if v) or 'nothing'}")
    for k, v in rep["notes"].items():
        print(f"  note {k}: {v}")
    for r in rep["rules"]:
        extra = "; ".join(f["key"] for f in r["findings"][:4]) or "; ".join(f"{w['key']} (waived: {w['reason'][:60]})"
                                                                           for w in r["waived"][:3])
        print(f"  {r['status']:8} {r['id']:12} {r['title'][:60]:60} {extra}")
    for b in rep["bad_waivers"]:
        print(f"  BAD waiver: {b}")
    for u in rep["unused_waivers"]:
        print(f"  unused waiver: {u}")
    verdict = "PASS" if rep["pass"] else ("FAIL" if [r for r in rep["rules"] if r["status"] == "fail"] or rep["bad_waivers"]
                                          else "INCOMPLETE (rules not run: not a pass)")
    print(f"lint ruleset: {verdict} {rep['counts']}")
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(rep, indent=1, default=str) + "\n")
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
