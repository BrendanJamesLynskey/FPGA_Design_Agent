"""The design package's facts as the spec interview sees them (brief 174).

``board_facts.yaml`` (written by ``python -m flow.package ingest``) holds facts with a cited source. Before the interview asks a
question, :func:`fact_for` looks for a fact that answers it; a fact with a source and a confidence other than ``low`` is used and the
question is not asked. A question that no fact answers is asked as before. The rules are deliberately narrow: a wrong match would
answer a question the user should have been asked, so only these shapes match, and the matching fact must be unambiguous.

- the device ("which part", "which device"), key ``part``;
- the Ethernet PHY ("PHY"), key ``chip.phy.*`` when the board has one PHY family;
- a port named in the question ("pin", "I/O standard", "IOSTANDARD" with a port name that has a ``pin.<port>`` fact);
- a series resistor on a named net ("series resistor", "series R", with a net that has a ``series_r.<net>`` fact);
- a clock frequency when the question names a port with a ``clock.<port>`` fact.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

FILE = "board_facts.yaml"


def load_facts(design: Path) -> list[dict[str, Any]]:
    """Rows of board_facts.yaml in the design directory (or in ``package/``); empty when there is none or it cannot be read."""
    for f in (Path(design) / FILE, Path(design) / "package" / FILE):
        if f.exists():
            try:
                doc = yaml.safe_load(f.read_text()) or {}
            except yaml.YAMLError:
                return []
            return [r for r in doc.get("facts") or [] if _sourced(r)]
    return []


def _sourced(r: dict[str, Any]) -> bool:
    s = r.get("source") or {}
    return bool(s.get("file") and s.get("locator")) and r.get("confidence") != "low"


def fact_for(text: str, facts: list[dict[str, Any]]) -> dict[str, Any] | None:
    t = text.lower()
    by: dict[str, list[dict[str, Any]]] = {}
    for r in facts:
        by.setdefault(r["key"], []).append(r)

    def one(rs: list[dict[str, Any]] | None) -> dict[str, Any] | None:
        return rs[0] if rs and len({str(x["value"]) for x in rs}) == 1 else None
    if re.search(r"\b(which|what)\b.*\b(part|device|fpga)\b", t):
        return one(by.get("part"))
    if re.search(r"\bphy\b", t):
        phys = [k for k in by if k.startswith("chip.phy.")]
        return one(by[phys[0]]) if len(phys) == 1 else None
    for k in by:
        if k.startswith("pin.") and re.search(r"\b(pin|i/o standard|iostandard|io standard|package pin)\b", t) and re.search(r"(?<![\w])" + re.escape(k[4:].lower()) + r"(?![\w])", t):
            return one(by[k])
        if k.startswith("series_r.") and re.search(r"series (resistor|r\b)", t) and re.search(r"(?<![\w])" + re.escape(k[9:].lower()) + r"(?![\w])", t):
            return one(by[k])
        if k.startswith("clock.") and re.search(r"(frequency|mhz|clock)", t) and re.search(r"(?<![\w])" + re.escape(k[6:].lower()) + r"(?![\w])", t):
            return one(by[k])
    return None


def answer_text(r: dict[str, Any]) -> str:
    v = r["value"]
    if isinstance(v, dict):
        v = v.get("mpn") or ", ".join(f"{a}={b}" for a, b in v.items() if not isinstance(b, (list, dict)))
    return str(v)


def evidence_text(r: dict[str, Any]) -> str:
    s = r["source"]
    return f"board_facts.yaml {r['key']} = {answer_text(r)} ({s['file']}, {s['locator']}, sha256 {str(s.get('sha256'))[:12]}, {r.get('confidence')})"
