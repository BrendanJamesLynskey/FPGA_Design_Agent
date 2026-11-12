#!/usr/bin/env python3
"""Parse a build directory's Vivado reports into one JSON, and pass or fail the build, stage by stage.

    python3 flow/gates.py designs/<name>/build/<variant> [--json gates.json]

Exit status 0 = every gate passed. The checks are grouped by UltraFast stage
(docs/methodology.md; AMD UG949 v2026.1), and the JSON names the first stage
that failed:

    rtl         report_methodology on the elaborated RTL: no critical warnings
    post_synth  check_timing all zero, methodology and DRC clean (no critical
                warnings, no DRC errors); post-synthesis WNS and the
                post-synthesis report_qor_assessment score are recorded (the
                score as a warning when below 4), not gated
    post_place  WHS > -0.5 ns after placement (large hold violations must be
                fixed before routing); WNS recorded
    post_route  setup, hold and pulse-width slack non-negative with zero totals;
                report_qor_assessment score >= 4 (the QoR gate, after routing);
                no unconstrained endpoints; no DRC errors or critical warnings;
                no critical methodology violations; no critical CDC violations;
                (post_synth also: the structural CDC check, brief 16: no unsafe crossing)
                the exception check (brief 20, flow/exceptions_check.py) after
                synthesis and after routing: no exception ignored or covering no
                path, no XDC message dropping one, no TIMING-29/-46/-47
                the I/O check (brief 20 part B, flow/io_check.py) after synthesis and
                after routing: no invented delay on a slow port, synchronous
                interfaces (io_interfaces) with -min and -max from the data sheet,
                relative to the right clock, IOB-packed; I/O setup and hold slack,
                the worst paths' uncertainty breakdown and corner, and the
                implementation-only timing margin (timing_margin_ns) recorded
                report_power run for the board's thermal environment with the
                junction at or below 85 C
    bitstream   the bitstream (and, for an ILA build, the .ltx) present

QoR gate (brief 05g): ``post_route_qor_assessment`` (score >= 4 in qor_assessment_route.rpt) is the gate.
The post-synthesis score is a recorded warning (``stages.post_synth.warnings`` and the top-level ``warnings``
list), not a gate: on small designs Vivado's post-synthesis predicted-congestion item reads 3 while the routed
score is 5 (benchmark 06a: 11 of 24 reference designs, all at most 1.2 % of the device, with timing met).

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

try:
    from flow import version_pin
except ImportError:      # run as a script: flow/ is on sys.path, not the repo
    import version_pin

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


def parse_check_timing_ports(text: str) -> dict[str, list[str]]:
    """The names check_timing -verbose lists under each non-empty check (``no_input_delay``: the input ports,
    ``no_output_delay``: the output ports, ...), from the detail sections (the ones with a dashed rule under the
    heading). Checks whose detail lists no names (a count of pins, say) are left out."""
    out: dict[str, list[str]] = {}
    heads = list(re.finditer(r"^\d+\.\s+checking\s+(\w+)\s+\((\d+)\)\n-+\n", text, re.M))
    for i, m in enumerate(heads):
        if int(m.group(2)) == 0:
            continue
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        names = [ln.strip() for ln in text[m.end():end].splitlines() if ln and not ln[0].isspace() and ln.strip()]
        if names:
            out[m.group(1)] = names
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
    # Summary rows (2025.2 and 2026.1 alike):  CDC-1  Critical      2  1-bit unknown CDC circuitry
    # (the per-crossing detail rows start with a row number, so they do not match)
    for rule, sev, n, desc in re.findall(r"^(CDC-\d+)\s+(Critical|Warning|Info)\s+(\d+)\s+(.*?)\s*$", text, re.M):
        out["rules"].append({"rule": rule, "severity": sev, "count": int(n), "description": desc})
    return out


HUB_OK = ("Max Delay Datapath Only", "Asynchronous Groups", "User Ignored")


def parse_clock_interaction(text: str) -> list[dict[str, str]]:
    """report_clock_interaction rows: {from, to, classification, constraints} (the table is column-aligned, two or more spaces apart)."""
    rows = []
    for line in text.splitlines():
        f = re.split(r"\s{2,}", line.strip())
        if len(f) >= 4 and f[0] and not set(f[0]) <= {"-"} and f[0] != "From Clock" and f[-2] != "Clock-Pair":
            rows.append({"from": f[0], "to": f[1], "classification": f[-2], "constraints": f[-1]})
    return rows


def hub_crossings(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Brief 48. Every clock pair between the debug hub's JTAG clock (a name with dbg_hub and TCK) and another clock must be
    constrained as asynchronous: Max Delay Datapath Only, Asynchronous Groups or User Ignored (plain False Path is accepted too;
    a Partial False Path is not, nor is Timed). Measured on the T1 ILA build, Vivado 2026.1: TCK to sys_clk_pin and back are
    Ignored / Max Delay Datapath Only (WNS +31.34 and +8.63 ns); the build without the hub's properties timed the crossing
    as synchronous (WNS -2.993 ns inside dbg_hub)."""
    def is_hub(n: str) -> bool:
        return "dbg_hub" in n and "TCK" in n
    pairs = [r for r in rows if (is_hub(r["from"]) or is_hub(r["to"])) and r["from"] != r["to"]]
    bad = [r for r in pairs if not (r["constraints"] in ("False Path",) or any(o in r["constraints"] for o in HUB_OK))]
    return {"pairs": len(pairs), "ok": bool(pairs) and not bad, "timed_as_synchronous": [f"{r['from']} -> {r['to']}: {r['constraints']}" for r in bad]}


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
QOR_SCORE_MIN = 4          # the post-route gate (brief 05g) and the post-synthesis warning. UG949 ch. 5 "Assessing Post-Synthesis Quality of Results": "Scores of 1 and 2 have no chance
                           # of meeting timing closure and a score of 3 is unlikely to close"; 4 = likely, 5 = will
PLACE_WHS_MIN_NS = -0.5    # UG949 ch. 6 "Pre- and Post-Placement": hold violations of -0.500 ns or more must be fixed
JUNCTION_MAX_C = 85.0      # commercial grade; the power gate flow/hw.py uses the same limit


def forwarded_clock_ports(d: Path, stage: str) -> set[str]:
    """Brief 20 part B: output ports that carry a generated (forwarded) clock, from flow/io_paths.tcl's dump. check_timing
    lists such a port under no_output_delay (fixture I7: an ODDR-forwarded clock with create_generated_clock on the port),
    but a clock output takes no output delay: the outputs are timed against the clock it carries."""
    f = d / f"io_paths_{stage}.txt"
    return forwarded_clock_ports_text(f.read_text(errors="replace")) if f.exists() else set()


def forwarded_clock_ports_text(dump: str) -> set[str]:
    """The ports of a flow/io_paths.tcl dump that are the source of a generated clock."""
    out = set()
    for line in dump.splitlines():
        x = line.split("|")
        if x[0] == "CLOCK" and len(x) >= 7 and x[5] == "1":
            out |= set(x[6].split())
    return out & {x.split("|")[1] for x in dump.splitlines() if x.startswith("PORT|")}


def unconstrained_ok(counts: dict[str, int], ports: dict[str, list[str]], fwd: set[str]) -> bool:
    """Every check_timing unconstrained count is zero, except no_output_delay entries that are forwarded-clock ports."""
    for k in UNCONSTRAINED_CHECKS:
        n = counts.get(k, 0)
        if k == "no_output_delay" and n and fwd:
            n = len([p for p in ports.get(k, []) if p not in fwd]) if ports.get(k) else n
        if n:
            return False
    return True


def unconstrained_text(ports: dict[str, list[str]], limit: int = 40) -> str:
    """The ports check_timing lists, one clause per check, in plain form (raw names, no advice)."""
    what = {"no_input_delay": "input ports with no input delay", "no_output_delay": "output ports with no output delay",
            "no_clock": "register pins with no clock", "unconstrained_internal_endpoints": "unconstrained internal endpoints"}
    return "; ".join(f"{what.get(k, k)} ({len(v)}): " + ", ".join(v[:limit]) + (f", ... {len(v) - limit} more" if len(v) > limit else "")
                     for k, v in ports.items())


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


def _architecture_for(d: Path, architecture: Path | None) -> dict[str, Any] | None:
    """The design's architecture.yaml (``build/<variant>`` -> the design directory), or None for a build that has
    none (a milestone before 05d): the resource gate is then not applied."""
    import yaml
    p = architecture or d.parent.parent / "architecture.yaml"
    try:
        data = yaml.safe_load(p.read_text()) if p.is_file() else None
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) and isinstance(data.get("predicted_resources"), dict) else None


def _cdc_structure(d: Path, architecture: Path | None) -> dict[str, Any]:
    """flow/cdc_structure.py on the build's cdc_paths_synth.rpt and cdc_synth.rpt; the design's architecture.yaml
    ``cdc_waivers`` (each ``{cell: <regex>, reason: <text>}``, a reason required) excuse named crossings."""
    import yaml
    try:
        from flow import cdc_structure
    except ImportError:      # run as a script: flow/ is on sys.path, not the repo
        import cdc_structure
    waivers: list[dict[str, str]] = []
    p = architecture or d.parent.parent / "architecture.yaml"
    try:
        data = yaml.safe_load(p.read_text()) if p.is_file() else None
        if isinstance(data, dict):
            waivers = [w for w in (data.get("cdc_waivers") or []) if isinstance(w, dict)]
    except yaml.YAMLError:
        pass
    return cdc_structure.evaluate(d / "cdc_paths_synth.rpt", d / "cdc_synth.rpt", waivers)


def _exceptions(d: Path, stage: str, strict: bool, g: dict[str, bool], name: str) -> dict[str, Any] | None:
    """Brief 20: flow/exceptions_check.py for one stage (``synth`` or ``route``) into gate ``name``. A build of this flow
    version (``strict``) that lacks the reports fails it; an older build without them skips it."""
    try:
        from flow import exceptions_check
    except ImportError:      # run as a script: flow/ is on sys.path, not the repo
        import exceptions_check
    if not (d / f"exceptions_{stage}.rpt").exists():
        if strict:
            g[name] = False
            return {"pass": False, "missing_report": f"exceptions_{stage}.rpt"}
        return None
    try:
        r = exceptions_check.evaluate(d, stage)
    except (OSError, ValueError) as e:
        g[name] = False
        return {"pass": False, "error": f"{type(e).__name__}: {e}"}
    g[name] = r["pass"]
    return r


def _io(d: Path, stage: str, strict: bool, g: dict[str, bool], name: str) -> dict[str, Any] | None:
    """Brief 20 part B: flow/io_check.py for one stage (``synth`` or ``route``) into gate ``name``. The interfaces come
    from the design's spec.yaml / build.yaml ``io_interfaces``, the slow ports from the board's ``slow_ports``. A build
    of this flow version (``strict``) without the dump fails the gate; an older build skips it."""
    try:
        from flow import io_check
    except ImportError:      # run as a script: flow/ is on sys.path, not the repo
        import io_check
    import yaml
    if not (d / f"io_paths_{stage}.txt").exists():
        if strict and (d / f"exceptions_{stage}.rpt").exists():
            g[name] = False
            return {"pass": False, "missing_report": f"io_paths_{stage}.txt"}
        return None
    prep = json.loads((d / "prepare.json").read_text()) if (d / "prepare.json").exists() else {}
    root = Path(__file__).resolve().parents[1]
    design = root / prep["design"] if prep.get("design") else d.parent.parent
    ifs, asy, errs = io_check.load_interfaces(design / "spec.yaml", design / "build.yaml")
    slow = None
    board = prep.get("board")
    bdata: dict[str, Any] = {}
    if board and (root / "boards" / board / "board.yaml").is_file():
        bdata = yaml.safe_load((root / "boards" / board / "board.yaml").read_text()) or {}
        slow = bdata.get("slow_ports")
    try:
        r = io_check.evaluate(d, stage, None, ifs, asy, slow)
    except (OSError, ValueError) as e:
        g[name] = False
        return {"pass": False, "error": f"{type(e).__name__}: {e}"}
    for e in errs:
        r["failures"].append({"rule": "IO-INTERFACES", "file": None, "line": None, "text": None, "message": e})
        r["pass"] = False
    # a published input jitter for the board clock and no set_input_jitter: a warning (never a made-up number)
    ij = (bdata.get("clock") or {}).get("input_jitter_ns")
    if ij is not None and stage == "route":
        bc = [c for c, v in (r.get("clocks") or {}).items() if (bdata.get("clock") or {}).get("port") in (v.get("source") or "")]
        if bc and not any((r["clocks"][c].get("input_jitter") or 0) > 0 for c in bc):
            r.setdefault("warnings", []).append({"name": "board_clock_input_jitter", "stage": "post_route",
                                                 "clock": bc[0], "published_ns": ij,
                                                 "note": "the board's oscillator jitter is published; no set_input_jitter"})
    g[name] = r["pass"]
    return r


def _margin(d: Path) -> dict[str, Any] | None:
    """Brief 20 part B: the implementation-only setup margin (timing_margin.txt from flow/build.tcl) and the placed WNS
    with and without it. Sign-off (timing_summary.rpt) is after its removal."""
    f = d / "timing_margin.txt"
    if not f.exists():
        return None
    kv = dict(line.split(" ", 1) for line in f.read_text().splitlines() if " " in line)
    out: dict[str, Any] = {"margin_ns": float(kv.get("margin_ns", 0)), "clocks": kv.get("clocks", "").split()}
    for k, n in (("place_wns_with_margin_ns", "timing_summary_place.rpt"),
                 ("place_wns_without_margin_ns", "timing_summary_place_nomargin.rpt")):
        if (d / n).exists():
            try:
                out[k] = parse_timing_summary(_read(d, n))["wns_ns"]
            except ValueError:
                out[k] = None
    return out


def evaluate(build_dir: Path, architecture: Path | None = None) -> dict[str, Any]:
    d = build_dir
    prep = json.loads((d / "prepare.json").read_text()) if (d / "prepare.json").exists() else {}
    top = prep.get("top") or next((p.stem for p in d.glob("*.bit")), "")
    variant = prep.get("variant", "base")
    stages: dict[str, dict[str, Any]] = {}
    # QR1: a build made by this flow (run_vivado.sh writes run.json before the gates run) always writes the reports below;
    # for such a build a missing one FAILS its gate instead of skipping it (a deleted report was a gate that vanished).
    # A directory without run.json (an older build, a hand-made fixture) keeps the old "absent = not run" behaviour.
    strict = (d / "run.json").exists()

    # --- rtl: methodology DRCs on the elaborated design (UG949 ch. 3 "Running RTL DRCs") ---
    if (d / "methodology_rtl.rpt").exists():
        meth_rtl = parse_rule_table(_read(d, "methodology_rtl.rpt"))
        stages["rtl"] = {"ran": True, "gates": {"rtl_methodology_no_critical": _n_sev(meth_rtl, "Critical Warning") == 0},
                         "methodology": _rule_summary(meth_rtl)}
    elif strict and (d / "timing_summary_synth.rpt").exists():
        stages["rtl"] = {"ran": True, "gates": {"rtl_methodology_no_critical": False}, "missing_report": "methodology_rtl.rpt"}
    else:
        stages["rtl"] = {"ran": False, "gates": {}}

    # --- post_synth: UG949 ch. 5 "Moving Past Synthesis" ---
    if (d / "timing_summary_synth.rpt").exists():
        t_s = parse_timing_summary(_read(d, "timing_summary_synth.rpt"))
        c_s_text = _read(d, "check_timing_synth.rpt")
        c_s = parse_check_timing(c_s_text)
        m_s = parse_rule_table(_read(d, "methodology_synth.rpt"))
        d_s = parse_rule_table(_read(d, "drc_synth.rpt"))
        q_s = parse_qor_assessment(_read(d, "qor_assessment_synth.rpt")) if (d / "qor_assessment_synth.rpt").exists() else None
        g = {"post_synth_no_unconstrained_endpoints": unconstrained_ok(c_s, parse_check_timing_ports(c_s_text),
                                                                       forwarded_clock_ports(d, "synth")),
             "post_synth_methodology_no_critical": _n_sev(m_s, "Critical Warning") == 0,
             "post_synth_drc_clean": _n_sev(d_s, "Error") == 0 and _n_sev(d_s, "Critical Warning") == 0}
        warn: list[dict[str, Any]] = []
        if q_s is not None and q_s["score"] < QOR_SCORE_MIN:      # a warning, not a gate (docstring: QoR gate)
            warn.append({"name": "post_synth_qor_assessment", "stage": "post_synth", "score": q_s["score"], "min": QOR_SCORE_MIN,
                         "meaning": q_s["meaning"],
                         "note": "post-synthesis score is a prediction; the gate is the post-route score"})
        cdc_s = parse_cdc(_read(d, "cdc_synth.rpt")) if (d / "cdc_synth.rpt").exists() else None
        if cdc_s is None and strict:
            g["post_synth_cdc_no_critical"] = False
        if cdc_s is not None:              # design standard STD-CDC-02 (brief 05d): report_cdc at post-synthesis
            g["post_synth_cdc_no_critical"] = sum(r["count"] for r in cdc_s["rules"] if r["severity"] == "Critical") == 0
        # brief 16: the structural CDC check (flow/cdc_structure.py) on every asynchronous crossing of the netlist, of every
        # severity; report_cdc alone passes a bus crossed bit by bit, reconverging synchronisers and a bit sampled twice
        cdc_struct = None
        if (d / "cdc_paths_synth.rpt").exists():
            try:
                cdc_struct = _cdc_structure(d, architecture)
                g["post_synth_cdc_structure_clean"] = cdc_struct["pass"]
            except ValueError:
                g["post_synth_cdc_structure_clean"] = False
        elif strict:
            g["post_synth_cdc_structure_clean"] = False
        exc_s = _exceptions(d, "synth", strict, g, "post_synth_exceptions_clean")
        io_s = _io(d, "synth", strict, g, "post_synth_io_constraints_clean")
        util_s = parse_utilization(_read(d, "utilization_synth.rpt")) if (d / "utilization_synth.rpt").exists() else {}
        arch = _architecture_for(d, architecture)
        sanity = None
        if arch is not None and util_s:    # resource sanity gate (brief 05d, Taylor addition 4)
            try:
                from flow.architecture import resource_check
            except ImportError:      # run as a script: flow/ is on sys.path, not the repo
                from architecture import resource_check
            sanity = resource_check(util_s, arch)
            g["post_synth_resources_in_range"] = sanity["pass"]
        stages["post_synth"] = {"ran": True, "gates": g, "warnings": warn, "timing": t_s, "check_timing": c_s,
                                "unconstrained_ports": parse_check_timing_ports(c_s_text),
                                "methodology": _rule_summary(m_s), "drc": _rule_summary(d_s), "qor_assessment": q_s,
                                "cdc": cdc_s, "cdc_structure": cdc_struct, "exceptions": exc_s, "io_timing": io_s,
                                "resource_sanity": sanity,
                                "utilization": util_s}
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

    # --- post_route and bitstream: only if the flow got that far (a stage-limited build, brief 05a, stops earlier) ---
    routed = (d / "timing_summary.rpt").exists()
    timing = checks = util = power = env = None
    drc = meth = []
    cdc = None
    if not routed:
        stages["post_route"] = {"ran": False, "gates": {}}
        stages["bitstream"] = {"ran": False, "gates": {}}
    else:
        # --- post_route: the closure checks (UG949 ch. 6) ---
        timing = parse_timing_summary(_read(d, "timing_summary.rpt"))
        checks_text = _read(d, "check_timing.rpt")
        checks = parse_check_timing(checks_text)
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
            "no_unconstrained_endpoints": unconstrained_ok(checks, parse_check_timing_ports(checks_text),
                                                           forwarded_clock_ports(d, "route")),
            # NSTD-1/UCIO-1 are critical warnings in report_drc but errors at write_bitstream
            "drc_clean": _n_sev(drc, "Error") == 0 and _n_sev(drc, "Critical Warning") == 0,
            "methodology_no_critical": _n_sev(meth, "Critical Warning") == 0,
            "cdc_no_critical": sum(r["count"] for r in cdc["rules"] if r["severity"] == "Critical") == 0,
        }
        qor_na = (d / "qor_unavailable_route.txt").exists()   # brief 48: Vivado 2026.1 on the Basic licence tier cannot run it
        if q_r is not None:        # the QoR gate (brief 05g): judged after routing, from qor_assessment_route.rpt
            route_gates["post_route_qor_assessment"] = q_r["score"] >= QOR_SCORE_MIN
        elif qor_na:
            q_r = {"available": False, "reason": "report_qor_assessment needs a licence tier above Basic (Implflow 47-2944); "
                                                 "the QoR gate is not judged"}
        elif strict:
            route_gates["post_route_qor_assessment"] = False
        # UG949 ch. 6 "Power Closure": the junction temperature must fit the thermal budget, computed for the
        # board's own environment (still air, no heat sink: flow/build.tcl applies boards/<board>/board.yaml)
        if (d / "methodology_rtl.rpt").exists() or strict:      # a build of this flow version: the environment is set
            route_gates["power_junction_ok"] = (env["airflow_lfm"] == 0 and env["heatsink"] == "none"
                                                and env["junction_c"] is not None and env["junction_c"] <= JUNCTION_MAX_C)
        ci = d / "clock_interaction_route.rpt"
        if (d / "probe_nets.txt").exists():      # an ILA that is an IP (brief 48): the hub's JTAG crossing must be constrained as asynchronous
            hub = hub_crossings(parse_clock_interaction(_read(d, "clock_interaction_route.rpt")) if ci.exists() else [])
            route_gates["ila_hub_crossing_async"] = hub["ok"]
            hub_info = hub
        else:
            hub_info = None
        exc_r = _exceptions(d, "route", strict, route_gates, "exceptions_clean")
        io_r = _io(d, "route", strict, route_gates, "io_timing_clean")
        stages["post_route"] = {"ran": True, "gates": route_gates, "qor_assessment": q_r, "exceptions": exc_r,
                                "io_timing": io_r, "timing_margin": _margin(d), "ila_hub_crossing": hub_info,
                                "warnings": (io_r or {}).get("warnings", []),
                                "unconstrained_ports": parse_check_timing_ports(checks_text)}

        # --- bitstream ---
        bit = d / f"{top}.bit"
        ltx = d / f"{top}.ltx"
        bit_gates = {"bitstream_present": bit.exists() and bit.stat().st_size > 0}
        if variant == "ila":
            bit_gates["debug_probes_present"] = ltx.exists() and ltx.stat().st_size > 0
        stages["bitstream"] = {"ran": True, "gates": bit_gates}

    gates: dict[str, bool] = {}
    warnings: list[dict[str, Any]] = []
    first_failed = None
    for name in STAGES:
        st = stages[name]
        warnings.extend(st.get("warnings", []))
        st["pass"] = all(st["gates"].values()) if st["ran"] else None
        gates.update(st["gates"])
        if st["ran"] and not st["pass"] and first_failed is None:
            first_failed = name
    return {
        "build_dir": str(d),
        **version_pin.record(d, json.loads((d / "run.json").read_text()) if strict else None),
        "top": top,
        "variant": variant,
        "pass": bool(gates) and all(gates.values()),   # nothing ran is not a pass
        "first_failed_stage": first_failed,
        "gates": gates,
        "warnings": warnings,
        "stages": stages,
        "timing": timing,
        "check_timing": checks,
        "utilization": util,
        "drc": _rule_summary(drc) if routed else None,
        "methodology": _rule_summary(meth) if routed else None,
        "cdc": cdc,
        "power": power,
        "power_environment": env,
        "bitstream": {"file": bit.name, "bytes": bit.stat().st_size if bit.exists() else 0} if routed else None,
        "build_stamp": prep.get("build_stamp"),
        "sources_sha256": prep.get("sources_sha256"),
        **_xprobe_evidence(d),
    }


def _xprobe_evidence(d: Path) -> dict[str, Any]:
    """Evidence only (brief 18): the cross-probe summary when the build ran with FDA_XPROBE=1; no gate reads it, and a
    build without xprobe.json gets no extra key (so the results and the golden requests do not change)."""
    f = d / "xprobe.json"
    if not f.is_file():
        return {}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import xprobe
        return {"xprobe": xprobe.summary(json.loads(f.read_text()))}
    except (OSError, ValueError, KeyError, ImportError) as e:
        return {"xprobe": {"error": f"{type(e).__name__}: {e}"}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("build_dir", type=Path)
    ap.add_argument("--json", type=Path, help="write the result here")
    ap.add_argument("--architecture", type=Path, help="architecture.yaml (default: the design's, two levels up)")
    a = ap.parse_args(argv)
    try:
        r = evaluate(a.build_dir, a.architecture)
    except (OSError, KeyError, ValueError, TypeError) as e:       # no reports to read: a failed gate, not a traceback
        print(f"gates: {a.build_dir.name}: FAIL: no usable build reports ({type(e).__name__}: {e}); the build did not "
              f"complete, read the build output")
        if a.json:
            a.json.parent.mkdir(parents=True, exist_ok=True)
            a.json.write_text(json.dumps({"pass": False, "stages": {}, "first_failed_stage": None,
                                          "error": f"{type(e).__name__}: {e}"}, indent=2) + "\n")
        return 1
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(r, indent=2) + "\n")
    t, u = r["timing"] or {}, r["utilization"] or {}
    if (n := version_pin.note(r)):
        print(f"gates: {n}")
    print(f"gates: {r['top']} ({r['variant']}): {'PASS' if r['pass'] else 'FAIL'}  "
          f"WNS {t.get('wns_ns')} ns, TNS {t.get('tns_ns')}, WHS {t.get('whs_ns')} ns, THS {t.get('ths_ns')}; "
          f"LUT {u.get('lut')}, FF {u.get('ff')}, BRAM {u.get('bram_tile')}, DSP {u.get('dsp')}")
    for name in STAGES:
        st = r["stages"][name]
        if not st["ran"]:
            print(f"  {name}: not run (no reports)")
            continue
        print(f"  {name}: {'pass' if st['pass'] else 'FAIL'}")
        for g, ok in st["gates"].items():
            ex = st.get("exceptions") or {}
            if ok and g.endswith("exceptions_clean") and ex.get("waived"):      # a waiver is reported, never as a plain pass
                print(f"    waiv {g}: {ex['waived']} {'/'.join(ex.get('waived_rules') or [])} (waivers.yaml)")
                continue
            print(f"    {'ok  ' if ok else 'FAIL'} {g}")
            if not ok and "unconstrained" in g and st.get("unconstrained_ports"):
                print(f"         check_timing: {unconstrained_text(st['unconstrained_ports'])}")
        for w in st.get("warnings", []):
            print(f"    warn {w['name']}: " + (f"score {w['score']} < {w['min']}" if "score" in w else w.get("note", ""))
                  + " (recorded, not a gate)")
    if r["first_failed_stage"]:
        print(f"first failed stage: {r['first_failed_stage']}")
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
