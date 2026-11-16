"""Findings from the check suite (brief 84): the baseline arm, and the evidence the judgement layer starts from.

``run_suite`` runs the registry (brief 71, ``flow.checks``) at RTL scope on the copy of the design, and maps each finding
to the review schema by code. Nothing here is a model's opinion: severity comes from the check's own verdict (a blocking
finding is ``major``, an advisory one ``minor``) and the category from the rule prefix. A check that did not run is listed,
not counted as a pass.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from flow.review.schema import Finding, Location, assign_ids

CATEGORY_BY_RULE = (
    ("HDL-RST", "reset"), ("HDL-CDC", "cdc"), ("HDL-XDC", "timing"), ("HDL-CLK", "timing"), ("HDL-METH", "timing"),
    ("HDL-IF", "protocol"), ("HDL-VER", "verification"), ("HDL-DOC", "documentation"), ("HDL-WID", "functional"),
    ("HDL-SYN-01", "functional"), ("HDL-SYN-02", "functional"), ("HDL-SYN-03", "functional"), ("HDL-SYN-05", "functional"),
    ("HDL-SYN", "style"), ("HDL-SIG", "style"), ("HDL-LINT", "style"), ("HDL-STD", "style"), ("HDL-DRC", "timing"),
    ("HDL-VIV", "timing"), ("HDL-WAIVE", "other"), ("HDL-GT", "timing"),
)
#: findings a design the agent did not write raises only because the agent's own layout file (architecture.yaml, which
#: declares clocks and interfaces) is missing: kept as ``info`` when that file is absent, never dropped
LAYOUT_NOISE = {"STD-ARCH-00", "STD-CLK-02", "STD-AXI-02"}
#: a rule whose violation is a defect, not a style point, at the severity the house standard gives it
MAJOR_RULES = {"HDL-RST-01", "HDL-RST-02", "HDL-RST-03", "HDL-RST-05", "HDL-CDC-01", "HDL-SYN-01", "HDL-SYN-02", "HDL-SYN-05",
               "HDL-CLK-01", "HDL-IF-03"}
LOC = re.compile(r"^(?P<file>[^\s:]+?)(?::(?P<line>\d+))?(?:\b|$)")


def tool_env() -> dict[str, str]:
    """PATH for the suite: Verilator from ~/.local/opt (no root), the rest is found by the checks themselves."""
    vr = Path.home() / ".local/opt/verilator-5048/root/usr/share/verilator"
    env = {}
    if (vr / "bin").is_dir():
        env["VERILATOR_ROOT"] = str(vr)
        env["PATH"] = f"{vr / 'bin'}:{os.environ.get('PATH', '')}"
    return env


def category(rule: str) -> str:
    for p, c in CATEGORY_BY_RULE:
        if rule.startswith(p):
            return c
    return "other"


def _loc(where: str, src: Path, work: Path) -> Location:
    where = (where or "").strip()
    m = re.match(r"^(.+?):(\d+)$", where)
    f, ln = (m.group(1), int(m.group(2))) if m else (where, None)
    for base in (work, src):
        try:
            f = Path(f).resolve().relative_to(base.resolve()).as_posix() if Path(f).is_absolute() else f
        except ValueError:
            pass
    f = re.sub(r"^runs/review/[^/]+/design/", "", f)
    return Location(f if f not in ("-", "") else "", ln or None)


def map_findings(rep: dict[str, Any], src: Path, work: Path) -> list[Finding]:
    out: list[Finding] = []
    for c in rep["checks"]:
        name = c["check"]
        for f in c.get("findings") or []:
            if "waived" in f:
                continue
            rule = f.get("rule") or "HDL-STD-00"
            code = f.get("code", "")
            blocking = bool(f.get("blocking"))
            sev = "major" if blocking and rule in MAJOR_RULES else "minor" if blocking else "info"
            if code in LAYOUT_NOISE and not (src / "architecture.yaml").is_file():
                sev = "info"
            f_ = f.get("file") if f.get("file") not in (None, "-") else None
            loc = _loc(f"{f_}:{f.get('line')}" if f_ and f.get("line") else str(f.get("where", "")), src, work)
            out.append(Finding(title=f"{name}: {code} {str(f.get('message', ''))[:90]}".strip(), severity=sev, category=category(rule),
                               location=loc, evidence=str(f.get("message", ""))[:400], rule=f"{rule} ({code})",
                               fix=str(f.get("fix", ""))[:300], confidence="high", source=f"check:{name}"))
    assign_ids(out)
    return out


def run_suite(prep: dict[str, Any], scope: str = "rtl", names: str = "all") -> dict[str, Any]:
    """Run the registry on the copy. Returns {report, findings, digest, not_run}. No Vivado session is started."""
    from flow import checks as C
    old = {k: os.environ.get(k) for k in tool_env()}
    os.environ.update(tool_env())
    try:
        rep = C.run(prep["src"], names, scope, "detail", root=C.ROOT)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    fs = map_findings(rep, prep["src"], prep["work"])
    ran = {c["check"]: ("partial" if c["status"] == "pass" and c.get("incomplete") else c["status"]) for c in rep["checks"]}
    why = {c["check"]: c.get("why", "") for c in rep["checks"] if c["status"] == "not_run"}
    return {"report": rep, "findings": fs, "digest": rep["digest"], "ran": ran, "not_run": why, "skipped": rep.get("skipped") or {}}
