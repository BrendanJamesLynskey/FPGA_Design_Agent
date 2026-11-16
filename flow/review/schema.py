"""The review findings schema (brief 84).

One finding is one thing a reader of the review can act on. Every finding has a severity, a place, the evidence for it,
the rule or reason, a suggested fix and a confidence. The same shape is used for findings from the check suite and for the
judgement layer's, so the two can be merged, compared and scored.

    severity    critical  the design is wrong or unsafe in a way that will bite in use (data loss, lock-up, protocol break)
                major     a real defect or a missing safeguard that should be fixed before the design is relied on
                minor     a weakness, a style or maintenance issue, a missing note
                info      an observation that needs no change (never counted as a false alarm by the benchmark)
    confidence  high | medium | low   how sure the reviewer is that the finding is real (not how bad it is)
    source      check:<name>   found by code in the check suite
                judge          found by the reviewer's reading of the design
                both           a check finding the reviewer confirmed and re-assessed
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "1"
SEVERITIES = ("critical", "major", "minor", "info")
CONFIDENCES = ("high", "medium", "low")
#: closed set, so findings can be grouped and scored; "other" is for what fits nowhere
CATEGORIES = (
    "cdc",               # clock-domain crossing
    "reset",             # reset style, polarity, missing reset of state, async reset in a datapath
    "protocol",          # an interface rule broken (handshake, back-pressure, stability while stalled)
    "functional",        # wrong behaviour: off-by-one, wrong width, wrong condition
    "arithmetic",        # overflow, saturation, rounding, signedness
    "timing",            # clocks, constraints, exceptions, I/O timing, closure risk
    "scalability",       # a parameter or size limit that breaks silently
    "documentation",     # an undocumented behaviour, a hole in the interface contract
    "verification",      # the tests miss something, or the test environment itself is wrong
    "tb-defect",         # a defect in the testbench that can make a wrong result look right (see CHECKLIST)
    "style",             # lint, naming, structure
    "other",
)
#: the checklist the reviewer works from; general review knowledge, never a case's answer
CHECKLIST = {
    "tb-defect": [
        "a comparison that is true or false on X or Z (== or != against a value that can be unknown) instead of ===/!== or an explicit X check",
        "a cycle counter and the signal it samples updated in different scheduling regions, so the count is off by one",
        "a DUT input driven on the same clock edge on which the DUT samples it",
        "a driver and a probe that race, so a measured latency is read one cycle too high or too low",
    ],
}


@dataclass
class Location:
    file: str = ""
    line: int | None = None
    end_line: int | None = None
    obj: str = ""                    # a netlist object, module, signal or register name

    def text(self) -> str:
        if not self.file:
            return self.obj or "-"
        s = self.file + (f":{self.line}" if self.line else "")
        if self.end_line and self.end_line != self.line:
            s += f"-{self.end_line}"
        return s + (f" ({self.obj})" if self.obj else "")


@dataclass
class Finding:
    title: str
    severity: str
    category: str
    location: Location
    evidence: str
    rule: str
    fix: str
    confidence: str = "medium"
    source: str = "judge"
    id: str = ""
    refs: list[str] = field(default_factory=list)      # ids of the check findings this one builds on

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "severity": self.severity, "category": self.category,
                "location": {"file": self.location.file, "line": self.location.line,
                             "end_line": self.location.end_line, "object": self.location.obj},
                "evidence": self.evidence, "rule": self.rule, "fix": self.fix, "confidence": self.confidence,
                "source": self.source, "refs": list(self.refs)}


def _int(v: Any) -> int | None:
    try:
        i = int(v)
        return i if i > 0 else None
    except (TypeError, ValueError):
        return None


def from_dict(d: dict[str, Any], source: str = "judge") -> tuple[Finding | None, list[str]]:
    """A finding from loose JSON (the judge's reply). Returns (finding, problems); a finding with problems that
    cannot be repaired is None. Repairs are only cosmetic (case, a missing optional field): never a guess at content."""
    problems: list[str] = []
    loc = d.get("location") or {}
    if isinstance(loc, str):                                    # "file:12" or "file:12-18"
        m = re.match(r"^(.*?)(?::(\d+)(?:-(\d+))?)?$", loc.strip())
        loc = {"file": m.group(1), "line": m.group(2), "end_line": m.group(3)} if m else {"file": loc}
    sev = str(d.get("severity", "")).lower().strip()
    cat = str(d.get("category", "")).lower().strip()
    conf = str(d.get("confidence", "medium")).lower().strip()
    if sev not in SEVERITIES:
        problems.append(f"severity {sev!r} is not one of {SEVERITIES}")
    if cat not in CATEGORIES:
        problems.append(f"category {cat!r} is not one of the closed set")
    if conf not in CONFIDENCES:
        conf = "medium"
    title = str(d.get("title", "")).strip()
    if not title:
        problems.append("no title")
    if problems:
        return None, problems
    f = Finding(title=title, severity=sev, category=cat,
                location=Location(str(loc.get("file", "") or ""), _int(loc.get("line")), _int(loc.get("end_line")),
                                  str(loc.get("object", loc.get("obj", "")) or "")),
                evidence=str(d.get("evidence", "")).strip(), rule=str(d.get("rule", "")).strip(),
                fix=str(d.get("fix", "")).strip(), confidence=conf, source=source,
                refs=[str(r) for r in d.get("refs") or [] if r])
    if not f.evidence:
        problems.append("no evidence (kept; the report marks it)")
    return f, problems


def assign_ids(fs: list[Finding]) -> None:
    """Stable ids: a hash of the place and the title, so the same finding keeps its id across runs of the same text."""
    seen: dict[str, int] = {}
    for f in fs:
        h = hashlib.sha256(f"{f.location.file}|{f.location.line}|{f.category}|{f.title.lower()}".encode()).hexdigest()[:6]
        seen[h] = seen.get(h, 0) + 1
        f.id = f"F-{h}" + (f"-{seen[h]}" if seen[h] > 1 else "")


SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}


def sort_findings(fs: list[Finding]) -> list[Finding]:
    return sorted(fs, key=lambda f: (SEV_RANK[f.severity], f.location.file, f.location.line or 0, f.title))
