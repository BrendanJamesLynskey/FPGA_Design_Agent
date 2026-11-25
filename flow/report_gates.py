#!/usr/bin/env python3
"""Report-driven checks from the methodology gap study (brief 204a, ranks 1, 2, 5, 11, 12, 13, 14).

Each check reads a report the build already writes (or one the check suite's Vivado session can write from a checkpoint),
through the parsers the flow already has where there is one (``flow.digest.timing.parse_paths`` for timing paths,
``flow.gates.parse_utilization`` and ``parse_timing_summary``), and returns findings in the check suite's shape
(``tool``, ``code``, ``severity``, ``where``, ``key``, ``message``, ``blocking``, ``count``). The registry in
``flow/checks/__init__.py`` wires them in as the checks ``logic_levels``, ``clock_tree``, ``fanout``, ``synth_log``,
``congestion``, ``ip_status`` and (extended) ``control_sets``.

Levels. A **gate** finding is blocking: the check fails. A finding is a gate only where the vendor guide calls it a
requirement or says the design cannot work (control sets above 15 % are "Reduction Required", UG949 p.265; a path that fails
with no net delay cannot close, UG949 p.200; locked or out-of-date IP is a build-time fault, UG949 p.49). Everything else
is an **advisory**: listed, never blocking. The gates are findings of the check suite; they are not (yet) entries of
gates.json, which the stage controller reads.

Thresholds and where they come from (page numbers are the PDF pages of UG949 v2025.2 and UG1292 v2025.1; the vendor text is
summarised, not quoted):

======= ========== ======= ===================================================================================================
id      level      source  rule
======= ========== ======= ===================================================================================================
LL-01   advisory   UG949 p.75, p.234 to 235; UG1292 p.5
                           the logic-level distribution of a clock against its requirement: review at 13 levels or more when
                           the requirement is 8 ns or longer (125 MHz and below), 6 levels or more above 125 MHz (the table
                           in p.75 gives "fewer than 6" for 125 to 250 MHz and asks for "advanced pipelining" above 250 MHz
                           with no figure; we use 6 there too)
LL-02   gate       UG949 p.200
                           a setup path that still violates with its net delay taken out (slack plus the path's net delay,
                           post-synthesis) cannot be closed by placement
CLK-01  advisory   UG949 p.111 to 112, p.139, p.200 to 201
                           a global clock buffer driven by another global buffer (cascaded, not parallel); a clock in the
                           synthesised netlist that no global buffer drives (a local clock)
CLK-02  advisory   UG949 p.232, p.248
                           setup path with clock uncertainty over 100 ps; hold path with uncertainty over 200 ps; hold skew
                           over 300 ps; setup skew with a magnitude over 500 ps on a violated path
FO-01   advisory   UG949 p.73 to 75
                           a non-clock net over 5000 loads (any clock), over 200 loads on a clock above 125 MHz, over 100 loads
                           on a clock above 250 MHz (the three columns of the p.75 table)
LOG-01  advisory   UG949 p.198 (and p.200, "most frequent offenders")
                           synthesis messages that say logic was dropped: removed or unused sequential elements and unconnected
                           internal registers, counted by message id (constant-driven and unconnected ports are left out: on the
                           recorded builds they were the tie-offs of a shared template)
LOG-02  advisory   UG949 p.198
                           a message printed its first 100 times and was then switched off by the tool (the Common 17-14
                           line), so the log under-reports it; ``messaging.defaultLimit`` raises the limit
LOG-03  gate       Synth 8-3301 (brief 203)
                           the build sets a generic or parameter and Vivado warns "Unused top level parameter/generic" for it:
                           the value never reached the design. The flow's own BUILD_STAMP is listed, not gated (it is injected
                           whether or not the top uses it)
CONG-01 advisory   UG949 p.240, p.244; UG1292 p.6
                           placer or router congestion region of 16x16 (level 4) or larger; any region of 32x32 (level 5) or
                           larger "likely degrades QoR"; short-interconnect tile share over 5 %
CONG-02 advisory   UG949 p.273, p.278; UG1292 p.6
                           utilisation: the average of the used LUT, FF, block RAM and DSP percentages above 75 %; LUT above
                           60 % while block RAM or DSP is above 80 %; LUT combining above 40 % in a congested window
IP-01   gate       UG949 p.49
                           ``report_ip_status`` lists an IP as locked, or its status is anything but up to date (an older IP
                           version, a changed requirement)
CS-01   advisory   UG949 p.265
                           control sets between 7.5 % and 15 % of the device's capacity (CLB registers / 8): reduction
                           recommended
CS-02   gate       UG949 p.265
                           control sets above 15 % of the capacity: reduction required
======= ========== ======= ===================================================================================================
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    from flow import gates as G
    from flow.digest import timing as T
except ImportError:      # run as a script: flow/ is on sys.path, not the repo
    import gates as G                      # type: ignore[no-redef]
    from digest import timing as T         # type: ignore[no-redef]

#: id -> (level, source, one line). The registry and the docs read this; the module docstring has the full table.
INFO: dict[str, tuple[str, str, str]] = {
    "RPT-LL-01": ("advisory", "UG949 p.75, p.234-235; UG1292 p.5", "logic levels against the clock requirement"),
    "RPT-LL-02": ("gate", "UG949 p.200", "a setup path that fails even with its net delay taken out cannot close"),
    "RPT-CLK-01": ("advisory", "UG949 p.111-112, p.139, p.200-201", "cascaded global buffers; local (fabric-routed) clocks"),
    "RPT-CLK-02": ("advisory", "UG949 p.232, p.248", "clock uncertainty and skew over the guide's review thresholds"),
    "RPT-FO-01": ("advisory", "UG949 p.73-75", "high-fanout net against the clock frequency (the p.75 table)"),
    "RPT-LOG-01": ("advisory", "UG949 p.198, p.200", "synthesis messages that say logic was dropped"),
    "RPT-LOG-02": ("advisory", "UG949 p.198", "a synthesis message switched off after 100 occurrences"),
    "RPT-LOG-03": ("gate", "UG901 (Synth 8-3301); brief 203", "a generic or parameter the build sets that the top does not have"),
    "RPT-CONG-01": ("advisory", "UG949 p.240, p.244; UG1292 p.6", "placer or router congestion at level 4 or above"),
    "RPT-CONG-02": ("advisory", "UG949 p.273, p.278; UG1292 p.6", "device utilisation high enough to make placement hard"),
    "RPT-IP-01": ("gate", "UG949 p.49", "IP locked or not up to date"),
    "RPT-CS-01": ("advisory", "UG949 p.265", "control sets 7.5 % to 15 % of capacity: reduction recommended"),
    "RPT-CS-02": ("gate", "UG949 p.265", "control sets above 15 % of capacity: reduction required"),
}

# thresholds, named once (each cites its page above)
LL_LOW_FREQ_REQ_NS = 8.0         # requirement at or above this = 125 MHz or slower
LL_REVIEW_LOW = 13               # levels at or above this at <= 125 MHz
LL_REVIEW_HIGH = 6               # levels at or above this above 125 MHz
FO_ANY = 5000                    # loads, any frequency
FO_MEDIUM = 200                  # loads, above 125 MHz
FO_HIGH = 100                    # loads, above 250 MHz
SETUP_UNCERTAINTY_NS = 0.100
HOLD_UNCERTAINTY_NS = 0.200
HOLD_SKEW_NS = 0.300
SETUP_SKEW_NS = 0.500
CONG_LEVEL_REVIEW = 4            # region side 16 (2**4)
CONG_LEVEL_LIKELY = 5            # region side 32
SHORT_TILE_PCT = 5.0
UTIL_AVG_PCT = 75.0
UTIL_LUT_WITH_MACRO_PCT = 60.0
UTIL_MACRO_PCT = 80.0
LUT_COMBINING_PCT = 40.0
CS_RECOMMEND_PCT = 7.5
CS_REQUIRED_PCT = 15.0
LOG_LIMIT = 100                  # the tool's default messaging.defaultLimit

FANOUT_FIX = ("a balanced tree in the RTL with KEEP on the replicas (not DONT_TOUCH), a driver register (FD) for the net, "
              "phys_opt_design -directive Explore for the fine replication, no MAX_FANOUT on a global or clock-enable net, "
              "and no replication of ASYNC_REG registers (add a register after the chain instead)")
CS_FIX = ("opt_design -control_set_merge, a higher synth_design -control_set_opt_threshold (a power cost), the CONTROL_SET_REMAP "
          "property on the cells, fewer clock enables on single registers, and no low-fanout asynchronous set or reset")


def finding(tool: str, code: str, where: str, message: str, *, blocking: bool = False, count: int = 1) -> dict[str, Any]:
    level = INFO[code][0]
    assert not blocking or level == "gate", f"{code}: only a gate blocks"
    return {"tool": tool, "code": code, "severity": "gate" if blocking else "advisory", "where": where,
            "key": f"{tool}:{code} {where}", "message": message[:600], "blocking": blocking, "count": count}


def _num(s: str) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------------------------------------------------
# logic levels (ranks 1)
# ---------------------------------------------------------------------------------------------------------------------
def parse_logic_levels(text: str) -> list[dict[str, Any]]:
    """The Logic Level Distribution table of ``report_design_analysis -logic_level_distribution``: one row per endpoint
    clock, ``{clock, requirement_ns, counts: {level: paths}}``."""
    rows: list[dict[str, Any]] = []
    head: list[str] | None = None
    for line in text.splitlines():
        if not line.startswith("|"):
            if head and rows:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0] == "End Point Clock":
            head = cells
            continue
        if head is None or len(cells) != len(head):
            continue
        req = re.fullmatch(r"(-?[0-9.]+)\s*ns", cells[1])
        if not req:
            continue
        counts = {}
        for h, v in zip(head[2:], cells[2:]):
            if h.isdigit() and v.isdigit():
                counts[int(h)] = int(v)
        rows.append({"clock": cells[0], "requirement_ns": float(req.group(1)), "counts": counts})
    return rows


def logic_level_threshold(requirement_ns: float) -> int:
    return LL_REVIEW_LOW if requirement_ns >= LL_LOW_FREQ_REQ_NS else LL_REVIEW_HIGH


def logic_level_findings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        if r["requirement_ns"] <= 0:
            continue
        thr = logic_level_threshold(r["requirement_ns"])
        over = {lv: n for lv, n in r["counts"].items() if lv >= thr and n}
        if over:
            n = sum(over.values())
            mhz = 1000.0 / r["requirement_ns"]
            out.append(finding("logic_levels", "RPT-LL-01", r["clock"],
                               f"clock {r['clock']} ({r['requirement_ns']:g} ns, {mhz:.0f} MHz): {n} of the worst paths have {thr} or "
                               f"more logic levels (deepest {max(over)}); UG949 asks for fewer than {thr} at this frequency. Pipeline "
                               f"the path or try synthesis -retiming (CARRY and MUXF levels inflate the count and cost little delay, "
                               f"UG1292 p.5)", count=n))
    return out


def zero_net_delay_findings(text: str, where: str = "timing_summary_synth.rpt") -> list[dict[str, Any]]:
    """RPT-LL-02 on the paths of a post-synthesis ``report_timing_summary``/``report_timing``: a setup path with negative slack
    whose slack plus its net delay is still negative cannot be closed by placing it better."""
    out = []
    for p in T.parse_paths(text):
        if p["kind"] != "setup" or p["met"] or p["route_ns"] is None:
            continue
        s0 = round(p["slack_ns"] + p["route_ns"], 3)
        if s0 < 0:
            out.append(finding("logic_levels", "RPT-LL-02", f"{where}:{p['source']}->{p['destination']}",
                               f"setup path {p['source']} to {p['destination']} ({p.get('source_clock')}, requirement "
                               f"{p.get('requirement_ns')} ns) has slack {p['slack_ns']:+.3f} ns with {p['route_ns']:.3f} ns of net delay; "
                               f"with the net delay removed it is still {s0:+.3f} ns, so no placement can close it (UG949 p.200): "
                               f"{p.get('logic_levels')} logic levels, logic delay {p['logic_ns']} ns. Pipeline it or relax the clock",
                               blocking=True))
    # the same net-delay-free path listed in the summary's several groups counts once
    seen, uniq = set(), []
    for f in out:
        if f["key"] not in seen:
            seen.add(f["key"])
            uniq.append(f)
    return uniq


# ---------------------------------------------------------------------------------------------------------------------
# clock tree (rank 2)
# ---------------------------------------------------------------------------------------------------------------------
def _table(text: str, title_re: str) -> tuple[list[str], list[list[str]]]:
    """The first ``|``-table after a section heading matching ``title_re``: (header cells, row cells)."""
    # a report's table of contents repeats each heading; the section itself is the one with a dashed rule under it
    ms = [m for m in re.finditer(title_re, text, re.M)]
    m = next((x for x in ms if re.match(r"[^\n]*\n-{3,}", text[x.start():])), ms[0] if ms else None)
    if m is None:
        return [], []
    head: list[str] = []
    rows: list[list[str]] = []
    started = False
    for line in text[m.end():].splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not head:
                head = cells
            else:
                rows.append(cells)
            started = True
        elif started and line.startswith("+"):
            continue
        elif started and not line.startswith("+"):
            break
    return head, rows


def parse_clock_utilization(text: str) -> dict[str, Any]:
    """``report_clock_utilization``: the global clocks (section 2), the sources that drive them (section 3) and the clock
    primitive counts (section 1)."""
    h1, r1 = _table(text, r"^1\. Clock Primitive Utilization")
    prims = {r[0]: int(r[1]) for r in r1 if len(r) >= 2 and r[1].isdigit()}
    h2, r2 = _table(text, r"^2\. Global Clock Resources")
    glob = [dict(zip(h2, r)) for r in r2 if len(r) == len(h2)]
    h3, r3 = _table(text, r"^3\. Global Clock Source Details")
    src = [dict(zip(h3, r)) for r in r3 if len(r) == len(h3)]
    local = bool(re.search(r"^\d+\.\s+Local Clock", text, re.M))
    return {"primitives": prims, "global_clocks": glob, "sources": src, "has_local_section": local}


_BUF = re.compile(r"^(BUFG|BUFGCE|BUFGCTRL|BUFGMUX|BUFG_GT|BUFGCE_DIV|BUFH|BUFHCE)\b")


def parse_clock_networks(text: str) -> list[dict[str, Any]]:
    """``report_clock_networks``: ``{clock, freq, endpoints, nonclock, tree: [line, ...]}`` per constrained clock."""
    out: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for line in text.splitlines():
        # a constrained clock reads "Clock clk (100MHz)(endpoints: ...)", an unconstrained one (a clock made in fabric) "Clock Q (endpoints: ...)"
        m = re.match(r"^Clock (\S+) (?:\(([^)]*)\))?\(endpoints: (\d+) clock, (\d+) nonclock\)", line)
        if m:
            cur = {"clock": m.group(1), "freq": m.group(2) or "", "endpoints": int(m.group(3)), "nonclock": int(m.group(4)), "tree": []}
            out.append(cur)
        elif cur is not None and line.strip():
            if line.startswith(("Unconstrained", "Constrained", "-----")):
                cur = None
            else:
                cur["tree"].append(line.rstrip())
    return out


def clock_tree_findings(util: dict[str, Any] | None, nets: list[dict[str, Any]] | None = None,
                        where: str = "clock_utilization") -> list[dict[str, Any]]:
    out = []
    if util:
        for s in util["sources"]:
            drv = s.get("Driver Type/Pin", "")
            if _BUF.match(drv):
                out.append(finding("clock_tree", "RPT-CLK-01", f"{where}:{s.get('Global Id', '?')}",
                                   f"global clock {s.get('Global Id')} ({s.get('Source Clock', '')}) is driven by another clock buffer "
                                   f"({drv}, {s.get('Driver Pin', '')}): cascaded buffers do not match insertion delay; use parallel "
                                   f"buffers fed from the same source (UG949 p.111-112)"))
        if util["has_local_section"]:
            out.append(finding("clock_tree", "RPT-CLK-01", f"{where}:local",
                               "the report lists local (fabric-routed) clocks: avoid them, or floorplan the driver and loads "
                               "(UG949 p.139)"))
    for n in nets or []:
        # a constrained clock whose tree passes through a LUT, FF or fabric divider is routed in fabric
        bad = [t for t in n["tree"] if re.search(r"\b(LUT\d|FD[CPRSE]+\w*|CARRY\d|MUXF\d)\b", t)]
        if bad:
            out.append(finding("clock_tree", "RPT-CLK-01", f"clock_networks:{n['clock']}",
                               f"clock {n['clock']} reaches its loads through fabric logic ({bad[0].strip()[:80]}): a local clock; "
                               f"use a clock-enable on the global clock, or a BUFGCE_DIV/MMCM output (UG949 p.139)"))
    return out


def path_clock_findings(paths: list[dict[str, Any]], where: str) -> list[dict[str, Any]]:
    """RPT-CLK-02 from report_timing paths: the thresholds of UG949 p.232 (uncertainty, hold skew) and p.248 (skew)."""
    out = []
    seen: set[str] = set()
    for p in paths:
        u, sk = p.get("uncertainty_ns"), p.get("skew_ns")
        msgs = []
        if p["kind"] == "setup":
            if u is not None and u > SETUP_UNCERTAINTY_NS + 1e-9:
                msgs.append(f"clock uncertainty {u:.3f} ns is over {SETUP_UNCERTAINTY_NS * 1000:.0f} ps (review the clock topology and jitter)")
            if sk is not None and not p["met"] and abs(sk) > SETUP_SKEW_NS + 1e-9:
                msgs.append(f"clock skew {sk:+.3f} ns on a violated path is over {SETUP_SKEW_NS * 1000:.0f} ps")
        else:
            if u is not None and u > HOLD_UNCERTAINTY_NS + 1e-9:
                msgs.append(f"clock uncertainty {u:.3f} ns is over {HOLD_UNCERTAINTY_NS * 1000:.0f} ps on a hold path")
            if sk is not None and sk > HOLD_SKEW_NS + 1e-9:
                msgs.append(f"clock skew {sk:+.3f} ns on a hold path is over {HOLD_SKEW_NS * 1000:.0f} ps")
        for m in msgs:
            f = finding("clock_tree", "RPT-CLK-02", f"{where}:{p['source']}->{p['destination']}",
                        f"{p['kind']} path {p['source']} to {p['destination']}: {m} (UG949 p.232)")
            if f["key"] + m not in seen:
                seen.add(f["key"] + m)
                out.append(f)
    return out


# ---------------------------------------------------------------------------------------------------------------------
# fan-out (rank 5)
# ---------------------------------------------------------------------------------------------------------------------
def parse_clock_summary(text: str) -> list[dict[str, Any]]:
    """The Clock Summary table of report_timing_summary: ``{clock, period_ns, mhz}``."""
    m = re.search(r"^Clock\s+Waveform\(ns\)\s+Period\(ns\)\s+Frequency\(MHz\)\n-+.*?\n(.*?)\n\s*\n", text, re.M | re.S)
    out = []
    for line in (m.group(1).splitlines() if m else []):
        f = line.split()
        if len(f) >= 4 and _num(f[-2]) is not None and _num(f[-1]) is not None:
            out.append({"clock": f[0], "period_ns": float(f[-2]), "mhz": float(f[-1])})
    return out


def parse_high_fanout(text: str) -> list[dict[str, Any]]:
    """The Fanout Summary of ``report_high_fanout_nets -timing -load_types``."""
    head, rows = _table(text, r"^1\. Fanout Summary")
    out = []
    for r in rows:
        if len(r) != len(head):
            continue
        d = dict(zip(head, r))
        try:
            out.append({"net": d["Net Name"], "fanout": int(d["Fanout"]), "driver": d.get("Driver Type", ""),
                        "clock_loads": int(d.get("Clock", "0") or 0), "worst_slack_ns": _num(d.get("Worst Slack(ns)", ""))})
        except (KeyError, ValueError):
            continue
    return out


def fanout_findings(nets: list[dict[str, Any]], clocks: list[dict[str, Any]], where: str = "high_fanout_synth.rpt") -> list[dict[str, Any]]:
    fastest = max((c["mhz"] for c in clocks), default=0.0)
    out = []
    for n in nets:
        if n["clock_loads"] or _BUF.match(n["driver"]):
            continue                     # a clock net: the clock checks own it
        fo = n["fanout"]
        why = None
        if fo > FO_ANY:
            why = f"over {FO_ANY} loads (not recommended at any frequency)"
        elif fo > FO_MEDIUM and fastest > 125.0:
            why = f"over {FO_MEDIUM} loads with a clock at {fastest:.0f} MHz (above 125 MHz)"
        elif fo > FO_HIGH and fastest > 250.0:
            why = f"over {FO_HIGH} loads with a clock at {fastest:.0f} MHz (above 250 MHz)"
        if why:
            out.append(finding("fanout", "RPT-FO-01", f"{where}:{n['net']}",
                               f"net {n['net']} ({n['driver']}) drives {fo} loads: {why} (UG949 p.75 table). Fix with {FANOUT_FIX}",
                               count=fo))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# synthesis log (rank 11)
# ---------------------------------------------------------------------------------------------------------------------
#: message id -> what it says about the design (all are Warnings in the log; counted per id)
DROPPED_LOGIC = {
    "Synth 8-3332": "sequential element removed (unused or constant)",
    "Synth 8-6014": "unused sequential element removed",
    "Synth 8-3936": "unconnected internal register removed",
}
# not counted (measured on 65 recorded builds, results/204a_report_gates): "port driven by a constant" (Synth 8-3917) fired on 27 of
# them and "unconnected or no load" ports (8-3331, 8-7129) on most; all were intended tie-offs of a shared register-block template.
_MSG = re.compile(r"^(?P<sev>CRITICAL WARNING|WARNING|INFO|ERROR): \[(?P<id>[A-Za-z]+ \d+-\d+)\]\s*(?P<text>.*)$", re.M)
_LIMIT = re.compile(r"^INFO: \[Common 17-14\] Message '(?P<id>[A-Za-z]+ \d+-\d+)' appears (?P<n>\d+) times", re.M)


def parse_log(text: str) -> dict[str, Any]:
    """Counts of messages by id and severity, and the ids the tool switched off at the limit."""
    counts: dict[str, dict[str, int]] = {}
    for m in _MSG.finditer(text):
        counts.setdefault(m.group("id"), {}).setdefault(m.group("sev"), 0)
        counts[m.group("id")][m.group("sev")] += 1
    limited = {m.group("id"): int(m.group("n")) for m in _LIMIT.finditer(text)}
    return {"counts": counts, "limited": limited}


_UNUSED_GENERIC = re.compile(r"^WARNING: \[Synth 8-3301\] Unused top level parameter/generic (\S+)", re.M)
FLOW_GENERICS = ("BUILD_STAMP",)


def build_generics(inputs_tcl: str) -> list[str]:
    """The generic names a build sets (``set generics [list {A=1} {B=2}]`` in the build's inputs.tcl)."""
    m = re.search(r"^set generics \[list (.*)\]\s*$", inputs_tcl, re.M)
    return re.findall(r"\{([A-Za-z_]\w*)=", m.group(1)) if m else []


def log_findings(text: str, where: str = "vivado.log", generics: list[str] | None = None) -> list[dict[str, Any]]:
    p = parse_log(text)
    out = []
    # a generic the build sets that the top does not have: the value never reached the core (brief 203: EARLY_MAC and FAST_PRE on a top
    # without them; Vivado only warned). Gate for every generic the build set except the flow's own stamp, which is listed.
    for name in sorted(set(_UNUSED_GENERIC.findall(text))):
        if generics is not None and name not in generics:
            continue
        flow_own = name in FLOW_GENERICS
        out.append(finding("synth_log", "RPT-LOG-03", f"{where}:{name}",
                           f"the build sets generic {name} but the top has no such parameter ([Synth 8-3301] Unused top level "
                           f"parameter/generic): its value never reached the design" +
                           (" (the flow's own build stamp: listed, not gated)" if flow_own else ". Fix the name in build.yaml or the top"),
                           blocking=not flow_own))
    dropped = {i: sum(c.values()) for i, c in p["counts"].items() if i in DROPPED_LOGIC and not set(c) <= {"INFO"}}
    for i, n in sorted(dropped.items(), key=lambda kv: -kv[1]):
        out.append(finding("synth_log", "RPT-LOG-01", f"{where}:{i}",
                           f"[{i}] {DROPPED_LOGIC[i]}: {n} message(s) in the log; check that each is intended (UG949 p.198)", count=n))
    for i, n in sorted(p["limited"].items()):
        out.append(finding("synth_log", "RPT-LOG-02", f"{where}:{i}",
                           f"[{i}] was printed {n} times and then switched off by the tool: the log under-reports it. Set "
                           f"`set_param messaging.defaultLimit` higher before the run (UG949 p.198)", count=n))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# congestion and utilisation (rank 12)
# ---------------------------------------------------------------------------------------------------------------------
def _region(s: str) -> int:
    m = re.fullmatch(r"(\d+)x\1", s.strip())
    return int(m.group(1)) if m else 0


def region_level(side: int) -> int:
    """The congestion level of a window of ``side`` x ``side`` tiles (UG949 p.240, Table 11: 2x2 is level 1, 4x4 level 2,
    ... 32x32 level 5)."""
    return max(side, 1).bit_length() - 1


def parse_placer_congestion(text: str) -> list[dict[str, Any]]:
    """The estimated-congestion tables the placer and router print in the log: ``{stage, direction, kind, side, level}``.
    The table has a Direction column and one Region Size column per kind (Global, Short, and sometimes Long)."""
    out = []
    for m in re.finditer(r"INFO: \[(?:Place|Route) [\d-]+\] ([^\n]*Estimated Congestion[^\n]*)\n(.*?)(?=\n(?![ |])|\Z)", text, re.S):
        stage, body = m.group(1).strip(), m.group(2)
        kinds: list[str] = []
        for line in body.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and cells[0] == "" and all(c.endswith("Congestion") for c in cells[1:]):
                kinds = [c.replace(" Congestion", "") for c in cells[1:]]
            elif kinds and len(cells) == len(kinds) + 1 and cells[0] in ("North", "South", "East", "West"):
                for k, c in zip(kinds, cells[1:]):
                    side = _region(c)
                    if side:
                        out.append({"stage": stage, "direction": cells[0], "kind": k, "side": side, "level": region_level(side)})
    return out


def parse_congestion_report(text: str) -> list[dict[str, Any]]:
    """The windows of ``report_design_analysis -congestion``: ``{stage, direction, type, level, share, combined_luts, muxf, ...}``.
    The placer table has a Congestion column; the router table a Percentage Tiles column. An empty table gives nothing."""
    out = []
    for stage, title in (("placer", r"^1\. Placer Final Level Congestion"), ("router", r"^2\. Initial Estimated Router Congestion")):
        head, rows = _table(text, title)
        for r in rows:
            if len(r) != len(head):
                continue
            d = dict(zip(head, r))
            lvl = _num(d.get("Level", ""))
            if lvl is None:
                continue
            share = _num(d.get("Percentage Tiles", d.get("Congestion", "")))
            out.append({"stage": stage, "direction": d.get("Direction"), "type": d.get("Type"), "level": int(lvl), "share": share,
                        "combined_luts": _num(d.get("Combined LUTs", "")), "lut": _num(d.get("LUT", "")),
                        "muxf": _num(d.get("MUXF", "")), "window": d.get("Window")})
    return out


def congestion_findings(log_tables: list[dict[str, Any]], windows: list[dict[str, Any]],
                        where: str = "vivado.log") -> list[dict[str, Any]]:
    out = []
    seen: set[str] = set()
    for t in log_tables:
        if t["level"] >= CONG_LEVEL_REVIEW:
            k = f"{t['stage']}:{t['direction']}:{t['kind']}"
            if k in seen:
                continue
            seen.add(k)
            sev = ("likely degrades QoR (UG949 p.244)" if t["level"] >= CONG_LEVEL_LIKELY else "small QoR variability (UG1292 p.6)")
            out.append(finding("congestion", "RPT-CONG-01", f"{where}:{t['direction']} {t['kind']}",
                               f"{t['stage']}: {t['direction']} {t['kind']} congestion window {t['side']}x{t['side']} (level {t['level']}): {sev}. "
                               f"Reduce utilisation, try a spreading placer directive, or remove MAX_FANOUT (UG1292 p.6)"))
    for w in windows:
        if w["level"] >= CONG_LEVEL_REVIEW:
            out.append(finding("congestion", "RPT-CONG-01", f"congestion:{w['stage']} {w['direction']} {w['type']}",
                               f"{w['stage']} congestion window, {w['direction']} {w['type']}, level {w['level']}"
                               + (f", {w['share']:g} % of tiles" if w["share"] is not None else "") + " (UG949 p.240, p.244)"))
        if (w["type"] or "").lower().startswith("short") and w["stage"] == "router" and (w["share"] or 0) > SHORT_TILE_PCT:
            out.append(finding("congestion", "RPT-CONG-01", f"congestion:{w['direction']} short share",
                               f"short-interconnect congestion covers {w['share']:g} % of tiles, over {SHORT_TILE_PCT:g} % (UG949 p.244)"))
        if w["combined_luts"] is not None and w["lut"]:
            pct = 100.0 * w["combined_luts"] / w["lut"] if w["lut"] else 0.0
            if w["level"] >= CONG_LEVEL_REVIEW and pct > LUT_COMBINING_PCT:
                out.append(finding("congestion", "RPT-CONG-02", f"congestion:{w['direction']} lut combining",
                                   f"{pct:.0f} % of the LUTs in a congested window are combined, over {LUT_COMBINING_PCT:g} %: try a "
                                   f"synthesis strategy without LUT combining (UG949 p.278)"))
    # one finding per distinct key
    uniq, keys = [], set()
    for f in out:
        if f["key"] not in keys:
            keys.add(f["key"])
            uniq.append(f)
    return uniq


def utilization_findings(util: dict[str, Any], where: str = "utilization") -> list[dict[str, Any]]:
    """RPT-CONG-02 from ``flow.gates.parse_utilization``."""
    pct = {}
    for k, label in (("lut", "LUT"), ("ff", "FF"), ("bram_tile", "block RAM"), ("dsp", "DSP")):
        used, avail = util.get(k), util.get(f"{k}_available")
        if used is not None and avail:
            pct[label] = 100.0 * used / avail
    out = []
    used_pct = [v for v in pct.values() if v > 0]
    if used_pct:
        avg = sum(used_pct) / len(used_pct)
        if avg > UTIL_AVG_PCT:
            out.append(finding("congestion", "RPT-CONG-02", f"{where}:average",
                               f"the used fabric resources average {avg:.0f} % ({', '.join(f'{k} {v:.0f}' for k, v in pct.items() if v > 0)}), "
                               f"over {UTIL_AVG_PCT:g} %: placement becomes hard (UG949 p.273)"))
    macro = max(pct.get("block RAM", 0.0), pct.get("DSP", 0.0))
    if pct.get("LUT", 0.0) > UTIL_LUT_WITH_MACRO_PCT and macro > UTIL_MACRO_PCT:
        out.append(finding("congestion", "RPT-CONG-02", f"{where}:lut+macro",
                           f"LUT {pct['LUT']:.0f} % with block RAM or DSP at {macro:.0f} %: keep LUT below {UTIL_LUT_WITH_MACRO_PCT:g} % "
                           f"when the macro primitives are over {UTIL_MACRO_PCT:g} % (UG1292 p.6)"))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# IP status (rank 13)
# ---------------------------------------------------------------------------------------------------------------------
def parse_ip_status(text: str) -> list[dict[str, Any]]:
    """``report_ip_status``: one row per IP instance, ``{ip, source, status, ...}`` (the IP Status table)."""
    head, rows = _table(text, r"^Project IP Instances")
    out = []
    for r in rows:
        if len(r) == len(head) and r[0]:          # a wrapped cell continues on the next row with an empty instance name
            out.append(dict(zip(head, r)))
    return out


def ip_status_findings(rows: list[dict[str, Any]], where: str = "ip_status.rpt") -> list[dict[str, Any]]:
    out = []
    for r in rows:
        name = r.get("Instance Name") or next(iter(r.values()), "?")
        status = r.get("Status", "").strip()
        locked = any("lock" in str(v).lower() for v in r.values())
        ok = status.lower() in ("up-to-date", "up to date")
        if locked or not ok:
            out.append(finding("ip_status", "RPT-IP-01", f"{where}:{name}",
                               f"IP {name}: {status or 'locked'}{' (locked)' if locked else ''}: upgrade it or regenerate its output products "
                               f"before the build (UG949 p.49)", blocking=True))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# control sets (rank 14)
# ---------------------------------------------------------------------------------------------------------------------
def parse_control_sets(text: str) -> int | None:
    m = re.search(r"Total control sets\s*\|\s*(\d+)", text) or re.search(r"Number of unique control sets\s*\|\s*(\d+)", text)
    return int(m.group(1)) if m else None


def control_set_findings(sets: int | None, ff_available: int | None, where: str = "control_sets") -> list[dict[str, Any]]:
    """The three bands of UG949 Table 17 (p.265). Capacity is the device's CLB registers divided by 8."""
    if not sets or not ff_available:
        return []
    capacity = ff_available / 8.0
    pct = 100.0 * sets / capacity
    if pct > CS_REQUIRED_PCT:
        return [finding("control_sets", "RPT-CS-02", where,
                        f"{sets} control sets are {pct:.1f} % of the device's {capacity:.0f}: over {CS_REQUIRED_PCT:g} %, reduction "
                        f"required (UG949 p.265). Options: {CS_FIX}", blocking=True, count=sets)]
    if pct >= CS_RECOMMEND_PCT:
        return [finding("control_sets", "RPT-CS-01", where,
                        f"{sets} control sets are {pct:.1f} % of the device's {capacity:.0f}: between {CS_RECOMMEND_PCT:g} % and "
                        f"{CS_REQUIRED_PCT:g} %, reduction recommended (UG949 p.265). Options: {CS_FIX}", count=sets)]
    return []


def read(p: Path | None) -> str:
    return p.read_text(errors="replace") if p is not None and p.is_file() else ""
