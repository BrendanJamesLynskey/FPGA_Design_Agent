#!/usr/bin/env python3
"""Per-crossing synchroniser MTBF, parsed from Vivado's ``report_synchronizer_mtbf`` (brief 189 item 12; idea from Edwards 2026, ch 6). Advisory.

"Two flops is enough" is a claim; the tool's report turns it into a number for every synchroniser chain it can identify, from the chain's
stage count, its total settling time, the destination clock rate and the data toggle rate. ``flow/build.tcl`` writes ``mtbf.rpt`` after
routing (a failure of the command never fails the build); this module parses that report into one record per crossing and compares each
with a target.

Family difference (measured, results/105_constraints_survey): the command gives numbers on UltraScale+ (xck26: 24 chains in the
survey fixture, 1,345 in the KR260 design) and only a warning on 7-series (xc7a100t), so a 7-series build has no MTBF record, and the record
says so (``status: no_report`` or ``no_chains``) instead of passing silently. The report lists only chains whose registers carry
ASYNC_REG (the survey's plain variant listed none), so a missing crossing is a finding for the structural CDC check, not a good MTBF.

    python3 -m flow.mtbf REPORT.rpt [--min-years 1000] [--out mtbf.json]

Record: ``{"enforced": false, "status", "overall_years", "crossings": [{path, mtbf_years, toggle_mtrs, sample_mhz, settling_ns, from, to,
stages, net}], "worst": {...}, "findings": [...]}``. Finding MTBF-01: a chain below ``--min-years`` (the target is the design's to set; the
default of 1,000 YEARS (not seconds) is a floor for advisory output, not a standard). MTBF-02: a chain of one stage. MTBF-03: the tool gives no MTBF for a chain whose data toggles (`UNDEFINED` with no toggle rate); `UNDEFINED` with a ZERO* toggle rate (static data) or an INFINITE settling time is only counted (``undefined_static``)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_MIN_YEARS = 1000.0
# UNITS (brief 246): every MTBF figure here is in YEARS. Vivado prints each cell with its own unit ("6.48e+51 years", "1.32 days": UG835 says the
# command reports "in dynamic time units, from seconds to years"), so a cell is converted to years; the number in ``mtbf_years`` is never seconds.
_YEARS = re.compile(r"^\s*>?\s*([0-9.]+(?:e[+-]?\d+)?)\s*(years?|days?|hours?|min(?:ute)?s?|sec(?:ond)?s?|s)\s*$", re.I)      # "> 1.8e+308 years" is a lower bound: beyond the tool's range
_TO_YEARS = {"year": 1.0, "day": 1 / 365.25, "hour": 1 / 8766.0, "min": 1 / 525960.0, "sec": 1 / 31557600.0, "s": 1 / 31557600.0}


def _years(cell: str) -> float | None:
    m = _YEARS.match(cell.strip())
    if m:
        unit = m.group(2).lower()
        return float(m.group(1)) * _TO_YEARS[next(k for k in ("year", "day", "hour", "min", "sec", "s") if unit.startswith(k))]
    return float("inf") if "inf" in cell.lower() else None


def _table(text: str, heading: str) -> list[dict[str, str]]:
    """Rows of the first ``|`` table after the section heading containing ``heading``, keyed by the header cells."""
    m = re.search(rf"^{re.escape(heading)}\s*\n-{{3,}}\s*$", text, re.M)       # the section, not its line in the table of contents
    if not m:
        return []
    i = m.start()
    rows: list[list[str]] = []
    for line in text[i:].splitlines()[2:]:
        s = line.strip()
        if s.startswith("+"):
            if rows and len(rows) > 1:
                continue
            continue
        if s.startswith("|"):
            rows.append([c.strip() for c in s.strip("|").split("|")])
        elif rows:
            break
    if len(rows) < 2:
        return []
    hdr = rows[0]
    return [dict(zip(hdr, r)) for r in rows[1:] if len(r) == len(hdr)]


def _static(c: dict[str, Any]) -> bool:
    """UNDEFINED with a ZERO* toggle rate (static data) or an INFINITE settling time: no failure rate to compute, not a finding."""
    return c["toggle_text"].upper().startswith("ZERO") or c["settling_text"].upper().startswith("INFINITE")


def parse(text: str) -> dict[str, Any]:
    summ = {r.get("Structure Type"): r for r in _table(text, "1. Design summary")}
    chains = []
    for r in _table(text, "2. Default Synchronizer Chain Summary"):
        def num(k: str) -> float | None:
            try:
                return float(r.get(k, ""))
            except ValueError:
                return None
        chains.append({"path": int(r["CDC Path"]) if r.get("CDC Path", "").isdigit() else r.get("CDC Path"), "mtbf_years": _years(r.get("MTBF", "")),
                       "mtbf_text": r.get("MTBF", ""), "toggle_text": r.get("Data Toggle Rate(Mtrs)", ""),
                       "settling_text": r.get("Total Settling Time(ns)", ""),
                       "toggle_mtrs": num("Data Toggle Rate(Mtrs)"), "sample_mhz": num("Data Sample Rate(Mhz)"),
                       "settling_ns": num("Total Settling Time(ns)"), "from": r.get("Sending Domain"), "to": r.get("Receiving Domain"),
                       "stages": int(r["Number Stages"]) if r.get("Number Stages", "").isdigit() else None, "net": r.get("CDC Net Name")})
    dev = re.search(r"\|\s*Device\s*:\s*(\S+)", text)
    ver = re.search(r"Vivado v\.?(\S+)", text)
    return {"device": dev.group(1) if dev else None, "vivado": ver.group(1) if ver else None,
            "overall_years": _years((summ.get("Synchronizers") or {}).get("MTBF", "")), "chains_in_design": int((summ.get("Synchronizers") or {}).get("Total in Design", 0) or 0),
            "crossings": chains}


def record(report: Path | None, min_years: float = DEFAULT_MIN_YEARS) -> dict[str, Any]:
    rec: dict[str, Any] = {"enforced": False, "report": str(report) if report else None, "min_years": min_years, "findings": []}
    if report is None or not Path(report).is_file():
        return {**rec, "status": "no_report", "crossings": [], "note": "no mtbf.rpt: the command was not run, or the part gives no numbers (7-series prints a warning)"}
    p = parse(Path(report).read_text(errors="replace"))
    rec.update(p)
    if not p["crossings"]:
        rec["status"] = "no_chains"
        rec["note"] = "the report lists no synchroniser chain (the registers need ASYNC_REG, or the design has no crossing)"
        return rec
    rec["status"] = "ok"
    rec["undefined_static"] = sum(1 for c in p["crossings"] if c["mtbf_years"] is None and _static(c))
    vals = [c for c in p["crossings"] if c["mtbf_years"] is not None]
    rec["worst"] = min(vals, key=lambda c: c["mtbf_years"]) if vals else None
    for c in p["crossings"]:
        if c["mtbf_years"] is None and not _static(c):
            rec["findings"].append({"code": "MTBF-03", "where": f"{c['from']}->{c['to']} {c['net']}", "mtbf_text": c["mtbf_text"],
                                    "message": f"the tool gives no MTBF ({c['mtbf_text']}, toggle rate {c['toggle_text']})"})
        if c["mtbf_years"] is not None and c["mtbf_years"] < min_years:
            rec["findings"].append({"code": "MTBF-01", "where": f"{c['from']}->{c['to']} {c['net']}", "mtbf_years": c["mtbf_years"],
                                    "message": f"chain MTBF {c['mtbf_years']:.3g} years is below {min_years:g}"})
        if c["stages"] is not None and c["stages"] < 2:
            rec["findings"].append({"code": "MTBF-02", "where": f"{c['from']}->{c['to']} {c['net']}", "message": "a one-stage chain"})
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("report", nargs="?")
    ap.add_argument("--min-years", type=float, default=DEFAULT_MIN_YEARS)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    rec = record(Path(a.report) if a.report else None, a.min_years)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(rec, indent=1) + "\n")
    w = rec.get("worst")
    print(f"{rec['status']}: {len(rec['crossings'])} crossing(s)" + (f", worst {w['mtbf_years']:.3g} years ({w['from']}->{w['to']} {w['net']})" if w else "")
          + f", {len(rec['findings'])} advisory finding(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
