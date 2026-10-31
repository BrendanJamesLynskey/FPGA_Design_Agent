#!/usr/bin/env python3
"""Parse a build directory's Vivado reports into one JSON, and pass or fail the build, stage by stage.

    python3 flow/gates.py designs/<name>/build/<variant> [--json gates.json]

Exit status 0 = every gate passed. The checks are grouped by UltraFast stage
(docs/methodology.md; AMD UG949 v2025.2), and the JSON names the first stage
that failed:

    rtl         report_methodology on the elaborated RTL: no critical warnings
    post_synth  check_timing all zero, methodology and DRC clean (no critical
                warnings, no DRC errors), report_qor_assessment score >= 4;
                post-synthesis WNS recorded, not gated
    post_place  WHS > -0.5 ns after placement (large hold violations must be
                fixed before routing); WNS recorded
    post_route  setup, hold and pulse-width slack non-negative with zero totals;
                no unconstrained endpoints; no DRC errors or critical warnings;
                no critical methodology violations; no critical CDC violations;
                report_power run for the board's thermal environment with the
                junction at or below 85 C
    bitstream   the bitstream (and, for an ILA build, the .ltx) present

A stage whose reports are absent (an older build) is marked ``ran: false`` and
skipped. The top-level ``gates`` dict keeps the F0A names for the post_route
and bitstream checks and adds the other stages' checks under stage-prefixed
names. Raw tool messages and rule IDs only: no fix hints (the harness stays
neutral).

``parse_utilization``, ``parse_wns`` and ``parse_report_power`` started as copies
of the HW Design Space Agent's parsers (see the attribution comments); the rest
is new here.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# --- copied and extended from HW_Design_Space_Agent -----------------------------

# From BrendanJamesLynskey/HW_Design_Space_Agent @ 80415c6, scripts/vivado_points.py
# parse_utilization (MIT). Extended: LUT/FF/CARRY4 plus BRAM tiles, DSPs, IOBs,
# BUFGs, LUTRAM, and "Available" for each.
_UTIL_ROWS = {
    "Slice LUTs": "lut", "LUT as Memory": "lutram", "Slice Registers": "ff", "CARRY4": "carry4",
    "Block RAM Tile": "bram_tile", "DSPs": "dsp", "Bonded IOB": "iob", "BUFGCTRL": "bufg",
}


def parse_utilization(text: str) -> dict[str, Any]:
    """Used (and available) counts from report_utilization's tables."""
    out: dict[str, Any] = {}
    for label, key in _UTIL_ROWS.items():
        m = re.search(rf"^\|\s*{re.escape(label)}\*?\s*\|\s*([0-9.]+)\s*\|(.*)$", text, re.M)
        if not m:
            continue
        used = float(m.group(1))
        out[key] = int(used) if used.is_integer() else used          # BRAM tiles can be x.5
        cells = [c.strip() for c in m.group(2).split("|")]
        nums = [c for c in cells if re.fullmatch(r"[0-9.]+", c)]
        if len(nums) >= 2:                                           # ... Available | Util%
            out[f"{key}_available"] = int(float(nums[-2]))
    return out


# From BrendanJamesLynskey/HW_Design_Space_Agent @ 80415c6, scripts/vivado_points.py
# parse_wns (MIT). Extended: all twelve columns of the Design Timing Summary
# (setup, hold, pulse width; slack, total, failing and total endpoints).
_TIMING_KEYS = ["wns_ns", "tns_ns", "tns_failing_endpoints", "tns_total_endpoints",
                "whs_ns", "ths_ns", "ths_failing_endpoints", "ths_total_endpoints",
                "wpws_ns", "tpws_ns", "tpws_failing_endpoints", "tpws_total_endpoints"]


def parse_timing_summary(text: str) -> dict[str, Any]:
    """The Design Timing Summary row of report_timing_summary."""
    m = re.search(r"Design Timing Summary.*?WNS\(ns\)[^\n]*\n[ \t]*-+[^\n]*\n[ \t]*(\S[^\n]*)", text, re.S)
    if not m:
        raise ValueError("no Design Timing Summary in report")
    vals = m.group(1).split()
    if len(vals) != len(_TIMING_KEYS):
        raise ValueError(f"Design Timing Summary has {len(vals)} columns, expected {len(_TIMING_KEYS)}")
    out: dict[str, Any] = {}
    for k, v in zip(_TIMING_KEYS, vals):
        # Vivado prints NA when a check has no endpoints (e.g. no hold paths)
        out[k] = None if v == "NA" else (int(v) if k.endswith("endpoints") else float(v))
    out["timing_met"] = "All user specified timing constraints are met." in text
    return out


def parse_wns(text: str) -> float:
    """WNS (ns) from the Design Timing Summary (the DSE agent's original interface)."""
    wns = parse_timing_summary(text)["wns_ns"]
    if wns is None:
        raise ValueError("WNS is NA")
    return wns


# From BrendanJamesLynskey/HW_Design_Space_Agent @ 80415c6, src/hw_dse/synth/vivado_power.py
# parse_report_power, _w, _decimals (MIT). Unchanged apart from names.
_SUMMARY = {"total_w": "Total On-Chip Power (W)", "dynamic_w": "Dynamic (W)", "static_w": "Device Static (W)"}
_COMPONENTS = {"Clocks": "clocks_w", "Slice Logic": "slice_logic_w", "Signals": "signals_w", "I/O": "io_w"}
_NOT_CORE = {"I/O", "Static Power", "Total", "Device Static", "On-Chip"}


def _decimals(text: str) -> int:
    t = text.strip()
    d = len(t.split(".", 1)[1]) if "." in t else 0
    return d + 1 if t.startswith("<") else d


def _w(text: str) -> float:
    t = text.strip()
    if t.startswith("<"):
        return round(float(t[1:]) / 2, _decimals(t))
    return float(t)


def parse_report_power(text: str) -> dict[str, Any]:
    """Summary and on-chip component rows of a Vivado report_power text report."""
    out: dict[str, Any] = {}
    for key, label in _SUMMARY.items():
        m = re.search(r"^\|\s*" + re.escape(label) + r"\s*\|\s*([<0-9.]+)\s*\|", text, re.M)
        if m:
            out[key] = _w(m.group(1))
    m = re.search(r"^\|\s*Confidence Level\s*\|\s*(\w+)\s*\|", text, re.M)
    out["confidence"] = m.group(1) if m else ""
    sec = text.split("On-Chip Components", 1)[1] if "On-Chip Components" in text else ""
    core, places = 0.0, 0
    for row in re.finditer(r"^\|( *)([A-Za-z/ ]+?)\s*\|\s*([<0-9.]+)\s*\|", sec, re.M):
        if len(row.group(1)) > 1:
            continue
        name, val = row.group(2).strip(), _w(row.group(3))
        places = max(places, _decimals(row.group(3)))
        if name in _COMPONENTS:
            out[_COMPONENTS[name]] = val
        if name not in _NOT_CORE:
            core += val
        if name == "Total":
            break
    if sec:
        out["core_w"] = round(core, places)
    if "dynamic_w" not in out:
        raise ValueError("no 'Dynamic (W)' row: not a report_power summary")
    return out


# --- new in this repo -------------------------------------------------------------

def parse_power_supplies(text: str) -> dict[str, dict[str, float]]:
    """report_power's Power Supply Summary: per supply, its voltage and total/dynamic/static current (A)."""
    sec = text.split("Power Supply Summary", 1)[1] if "Power Supply Summary" in text else ""
    out: dict[str, dict[str, float]] = {}
    for name, v, tot, dyn, sta in re.findall(
            r"^\|\s*(\w+)\s*\|\s*([0-9.]+)\s*\|\s*([<0-9.]+)\s*\|\s*([<0-9.]+)\s*\|\s*([<0-9.]+)\s*\|", sec, re.M):
        out[name.lower()] = {"v": float(v), "total_a": _w(tot), "dynamic_a": _w(dyn), "static_a": _w(sta)}
        if name.lower() == "vccadc":
            break
    return out


def parse_power_environment(text: str) -> dict[str, Any]:
    """Junction temperature and the thermal environment report_power assumed (Summary and Settings)."""
    def row(label: str) -> str | None:
        m = re.search(r"^\|\s*" + re.escape(label) + r"\s*\|\s*(.*?)\s*\|", text, re.M)
        return m.group(1) if m else None

    def num(label: str) -> float | None:
        v = row(label)
        try:
            return float(v) if v is not None else None
        except ValueError:
            return None

    hs = row("Heat Sink")
    return {"junction_c": num("Junction Temperature (C)"), "max_ambient_c": num("Max Ambient (C)"),
            "theta_ja_c_per_w": num("Effective TJA (C/W)"), "ambient_c": num("Ambient Temp (C)"),
            "airflow_lfm": num("Airflow (LFM)"), "heatsink": hs.split()[0] if hs else None,
            "board": row("Board Selection"), "board_layers": row("# of Board Layers")}


def parse_check_timing(text: str) -> dict[str, int]:
    """Counts from check_timing (or the check_timing section of report_timing_summary)."""
    out: dict[str, int] = {}
    for name, n in re.findall(r"^\s*\d+\.\s+checking\s+(\w+)\s+\((\d+)\)", text, re.M):
        out.setdefault(name, int(n))          # the summary list comes first; details repeat it
    if not out:
        raise ValueError("no 'checking <name> (<n>)' lines: not a check_timing report")
    return out


def parse_rule_table(text: str) -> list[dict[str, Any]]:
    """The REPORT SUMMARY table of report_drc / report_methodology: rule, severity, description, count."""
    rows = []
    for rule, sev, desc, n in re.findall(
            r"^\|\s*([A-Z][A-Z0-9_]*-\d+)\s*\|\s*([A-Za-z ]+?)\s*\|\s*(.*?)\s*\|\s*(\d+)\s*\|\s*$", text, re.M):
        rows.append({"rule": rule, "severity": sev, "description": desc, "count": int(n)})
    if not rows and not re.search(r"(Checks|Violations) found:\s*0", text):
        if "REPORT SUMMARY" not in text:
            raise ValueError("no REPORT SUMMARY: not a DRC or methodology report")
    return rows


def parse_cdc(text: str) -> dict[str, Any]:
    """report_cdc -details: 'All paths are Safely Timed', or the summary rows (ID, severity, count, description)."""
    if "CDC Report" not in text:
        raise ValueError("not a report_cdc report")
    out: dict[str, Any] = {"safely_timed": "All paths are Safely Timed." in text, "rules": []}
    # Summary rows (2025.2):  CDC-1  Critical      2  1-bit unknown CDC circuitry
    # (the per-crossing detail rows start with a row number, so they do not match)
    for rule, sev, n, desc in re.findall(r"^(CDC-\d+)\s+(Critical|Warning|Info)\s+(\d+)\s+(.*?)\s*$", text, re.M):
        out["rules"].append({"rule": rule, "severity": sev, "count": int(n), "description": desc})
    return out


def parse_qor_assessment(text: str) -> dict[str, Any]:
    """report_qor_assessment: the 1-5 score, its text, the flow guidance and the detail rows marked REVIEW."""
    m = re.search(r"^\|\s*QoR Assessment Score\s*\|\s*(\d)\s*-\s*(.*?)\s*\|", text, re.M)
    if not m:
        raise ValueError("no 'QoR Assessment Score' row: not a report_qor_assessment report")
    # the Flow Guidance row and its continuation rows (empty first cell) in the summary table
    block = re.search(r"^\|\s*Flow Guidance\s*\|.*?(?=^\+-)", text, re.M | re.S)
    guidance = re.findall(r"^\|[^|]*\|\s*(\S[^|]*?)\s*\|\s*$", block.group(0), re.M) if block else []
    review = []
    for name, thr, actual, status in re.findall(
            r"^\|\s*(\*?\s*[A-Za-z][^|]*?)\s*\|\s*([0-9.]*)\s*\|\s*([0-9.]*)\s*\|[^|]*\|[^|]*\|[^|]*\|\s*(REVIEW|OK)\s*\|",
            text, re.M):
        if status == "REVIEW":
            review.append({"name": name.lstrip("* ").strip(), "threshold": thr, "actual": actual,
                           "affects_score": not name.startswith("*")})
    return {"score": int(m.group(1)), "meaning": m.group(2), "flow_guidance": guidance, "review": review}


UNCONSTRAINED_CHECKS = ("no_clock", "unconstrained_internal_endpoints", "no_input_delay", "no_output_delay",
                        "partial_input_delay", "partial_output_delay", "multiple_clock", "loops", "latch_loops")


STAGES = ("rtl", "post_synth", "post_place", "post_route", "bitstream")
QOR_SCORE_MIN = 4          # UG949 ch. 5 "Assessing Post-Synthesis Quality of Results": "Scores of 1 and 2 have no chance
                           # of meeting timing closure and a score of 3 is unlikely to close"; 4 = likely, 5 = will
PLACE_WHS_MIN_NS = -0.5    # UG949 ch. 6 "Pre- and Post-Placement": hold violations of -0.500 ns or more must be fixed
JUNCTION_MAX_C = 85.0      # commercial grade; the power gate flow/hw.py uses the same limit


def _read(d: Path, name: str) -> str:
    p = d / name
    if not p.exists():
        raise FileNotFoundError(f"{p} missing: did the flow reach the reports stage?")
    return p.read_text(errors="replace")


def _n_sev(rows: list[dict[str, Any]], sev: str) -> int:
    return sum(r["count"] for r in rows if r["severity"].lower() == sev.lower())


def _slack_ok(s: float | None, t: float | None) -> bool:
    return s is None or (s >= 0 and (t or 0.0) == 0.0)


def _rule_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"errors": _n_sev(rows, "Error"), "critical_warnings": _n_sev(rows, "Critical Warning"),
            "warnings": _n_sev(rows, "Warning"), "rules": rows}


def evaluate(build_dir: Path) -> dict[str, Any]:
    d = build_dir
    prep = json.loads((d / "prepare.json").read_text()) if (d / "prepare.json").exists() else {}
    top = prep.get("top") or next((p.stem for p in d.glob("*.bit")), "")
    variant = prep.get("variant", "base")
    stages: dict[str, dict[str, Any]] = {}

    # --- rtl: methodology DRCs on the elaborated design (UG949 ch. 3 "Running RTL DRCs") ---
    if (d / "methodology_rtl.rpt").exists():
        meth_rtl = parse_rule_table(_read(d, "methodology_rtl.rpt"))
        stages["rtl"] = {"ran": True, "gates": {"rtl_methodology_no_critical": _n_sev(meth_rtl, "Critical Warning") == 0},
                         "methodology": _rule_summary(meth_rtl)}
    else:
        stages["rtl"] = {"ran": False, "gates": {}}

    # --- post_synth: UG949 ch. 5 "Moving Past Synthesis" ---
    if (d / "timing_summary_synth.rpt").exists():
        t_s = parse_timing_summary(_read(d, "timing_summary_synth.rpt"))
        c_s = parse_check_timing(_read(d, "check_timing_synth.rpt"))
        m_s = parse_rule_table(_read(d, "methodology_synth.rpt"))
        d_s = parse_rule_table(_read(d, "drc_synth.rpt"))
        q_s = parse_qor_assessment(_read(d, "qor_assessment_synth.rpt")) if (d / "qor_assessment_synth.rpt").exists() else None
        g = {"post_synth_no_unconstrained_endpoints": all(c_s.get(k, 0) == 0 for k in UNCONSTRAINED_CHECKS),
             "post_synth_methodology_no_critical": _n_sev(m_s, "Critical Warning") == 0,
             "post_synth_drc_clean": _n_sev(d_s, "Error") == 0 and _n_sev(d_s, "Critical Warning") == 0}
        if q_s is not None:
            g["post_synth_qor_assessment"] = q_s["score"] >= QOR_SCORE_MIN
        stages["post_synth"] = {"ran": True, "gates": g, "timing": t_s, "check_timing": c_s,
                                "methodology": _rule_summary(m_s), "drc": _rule_summary(d_s), "qor_assessment": q_s,
                                "utilization": parse_utilization(_read(d, "utilization_synth.rpt"))
                                if (d / "utilization_synth.rpt").exists() else {}}
    else:
        stages["post_synth"] = {"ran": False, "gates": {}}

    # --- post_place: UG949 ch. 6 "Pre- and Post-Placement" ---
    if (d / "timing_summary_place.rpt").exists():
        t_p = parse_timing_summary(_read(d, "timing_summary_place.rpt"))
        whs = t_p["whs_ns"]
        stages["post_place"] = {"ran": True, "gates": {"post_place_hold": whs is None or whs > PLACE_WHS_MIN_NS},
                                "timing": t_p}
    else:
        stages["post_place"] = {"ran": False, "gates": {}}

    # --- post_route: the closure checks (UG949 ch. 6) ---
    timing = parse_timing_summary(_read(d, "timing_summary.rpt"))
    checks = parse_check_timing(_read(d, "check_timing.rpt"))
    util = parse_utilization(_read(d, "utilization.rpt"))
    drc = parse_rule_table(_read(d, "drc.rpt"))
    meth = parse_rule_table(_read(d, "methodology.rpt"))
    cdc = parse_cdc(_read(d, "cdc.rpt"))
    power_text = _read(d, "power.rpt")
    power = parse_report_power(power_text)
    env = parse_power_environment(power_text)
    q_r = parse_qor_assessment(_read(d, "qor_assessment_route.rpt")) if (d / "qor_assessment_route.rpt").exists() else None
    route_gates = {
        "setup": _slack_ok(timing["wns_ns"], timing["tns_ns"]),
        "hold": _slack_ok(timing["whs_ns"], timing["ths_ns"]),
        "pulse_width": _slack_ok(timing["wpws_ns"], timing["tpws_ns"]),
        "no_unconstrained_endpoints": all(checks.get(k, 0) == 0 for k in UNCONSTRAINED_CHECKS),
        # NSTD-1/UCIO-1 are critical warnings in report_drc but errors at write_bitstream
        "drc_clean": _n_sev(drc, "Error") == 0 and _n_sev(drc, "Critical Warning") == 0,
        "methodology_no_critical": _n_sev(meth, "Critical Warning") == 0,
        "cdc_no_critical": sum(r["count"] for r in cdc["rules"] if r["severity"] == "Critical") == 0,
    }
    # UG949 ch. 6 "Power Closure": the junction temperature must fit the thermal budget, computed for the
    # board's own environment (still air, no heat sink: flow/build.tcl applies boards/<board>/board.yaml)
    if (d / "methodology_rtl.rpt").exists():      # a build of this flow version: the environment is set
        route_gates["power_junction_ok"] = (env["airflow_lfm"] == 0 and env["heatsink"] == "none"
                                            and env["junction_c"] is not None and env["junction_c"] <= JUNCTION_MAX_C)
    stages["post_route"] = {"ran": True, "gates": route_gates, "qor_assessment": q_r}

    # --- bitstream ---
    bit = d / f"{top}.bit"
    ltx = d / f"{top}.ltx"
    bit_gates = {"bitstream_present": bit.exists() and bit.stat().st_size > 0}
    if variant == "ila":
        bit_gates["debug_probes_present"] = ltx.exists() and ltx.stat().st_size > 0
    stages["bitstream"] = {"ran": True, "gates": bit_gates}

    gates: dict[str, bool] = {}
    first_failed = None
    for name in STAGES:
        st = stages[name]
        st["pass"] = all(st["gates"].values()) if st["ran"] else None
        gates.update(st["gates"])
        if st["ran"] and not st["pass"] and first_failed is None:
            first_failed = name
    return {
        "build_dir": str(d),
        "top": top,
        "variant": variant,
        "pass": all(gates.values()),
        "first_failed_stage": first_failed,
        "gates": gates,
        "stages": stages,
        "timing": timing,
        "check_timing": checks,
        "utilization": util,
        "drc": _rule_summary(drc),
        "methodology": _rule_summary(meth),
        "cdc": cdc,
        "power": power,
        "power_environment": env,
        "bitstream": {"file": bit.name, "bytes": bit.stat().st_size if bit.exists() else 0},
        "build_stamp": prep.get("build_stamp"),
        "sources_sha256": prep.get("sources_sha256"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("build_dir", type=Path)
    ap.add_argument("--json", type=Path, help="write the result here")
    a = ap.parse_args(argv)
    r = evaluate(a.build_dir)
    if a.json:
        a.json.write_text(json.dumps(r, indent=2) + "\n")
    t, u = r["timing"], r["utilization"]
    print(f"gates: {r['top']} ({r['variant']}): {'PASS' if r['pass'] else 'FAIL'}  "
          f"WNS {t['wns_ns']} ns, TNS {t['tns_ns']}, WHS {t['whs_ns']} ns, THS {t['ths_ns']}; "
          f"LUT {u.get('lut')}, FF {u.get('ff')}, BRAM {u.get('bram_tile')}, DSP {u.get('dsp')}")
    for name in STAGES:
        st = r["stages"][name]
        if not st["ran"]:
            print(f"  {name}: not run (no reports)")
            continue
        print(f"  {name}: {'pass' if st['pass'] else 'FAIL'}")
        for g, ok in st["gates"].items():
            print(f"    {'ok  ' if ok else 'FAIL'} {g}")
    if r["first_failed_stage"]:
        print(f"first failed stage: {r['first_failed_stage']}")
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
