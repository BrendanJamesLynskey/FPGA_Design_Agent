#!/usr/bin/env python3
"""The off-chip I/O choice check (brief 155): standard, DRIVE, SLEW and termination from the load and the line.

    python3 flow/offchip_check.py --spec spec.yaml --xdc design.xdc [--xdc more.xdc] [--family artix7] [--part P] [--bank-type HR] [--no-propose]

Family, part and bank type come from the command line, else from the spec's own ``family:`` / ``part:`` / ``bank_type:`` keys (brief 164).
Two answers per output group (owner decision 30): the best DRIVE/SLEW for the board as built and the optimal setup if the series resistor can change
(``board_fixed: true`` in a group says only the first applies).

Advisory until the owner approves it (planner-delegated approval is fine, decision 23): every finding says ``advisory``.

The spec holds one ``off_chip:`` entry per port group (see ``GROUP_KEYS`` and docs/offchip_io.md)::

    off_chip:
      - name: rgmii_tx
        ports: [a_txd[*], a_tx_ctl, a_txc]    # names or globs
        direction: output                     # output | input | inout
        iostandard: LVCMOS18                  # what the XDC should have; the check reads the XDC too
        vcco: 1.8                             # the bank supply (V); defaults to the standard's
        bank: 66                              # optional: groups that name the same bank must agree on VCCO
        bank_type: HP                         # HR | HP | HD (defaults from the board)
        line: {z0_ohm: 50, length_in: 3.0}    # or  line: short   (a lumped load, no transmission line)
        load: {c_pf: 5.0, receiver_std: LVCMOS18, vil_v: 0.63, vih_v: 1.17}   # receiver pin + stub capacitance, thresholds
        external: {series_ohm: 22}            # parts already on the board: series_ohm, parallel_gnd_ohm, thevenin_ohm, ac_ohm
        priority: edge_rate                   # edge_rate | emi | balanced  (which matters more)
        ui_ns: 8.0                            # unit interval (for the overshoot-duration limit); default 10 ns, assumed
        max_rise_ns: 1.5                      # the receiver needs its 20-80 % time at the weak corner at most this long (default 0.25 UI)
        min_drive_ma: 4                       # the DC current the output must source or sink (an LED); proposals never go below it

For each group the check (a) reads DRIVE, SLEW and IOSTANDARD from the XDC (a missing DRIVE or SLEW is the tool default, 12 mA and
SLOW: UG471 Table 1-8 and the SLEW text, UG571 Table 1-12), (b) simulates the configuration over the IBIS typ, weak and strong
corners with ``flow/offchip_model.py``, and (c) raises:

    OFFCHIP-OVERSHOOT   the receiver sees more than VCCO+0.2 V (or less than -0.2 V): the recommended-operating limit of DS181 Table 2 /
                        DS925 Table 2. Above that the data sheet's duration table applies (DS181 Table 4, DS925 Tables 6 and 7: allowed
                        share of the unit interval); a peak beyond the table, or beyond the absolute maximum, is ``contradicts-model``.
    OFFCHIP-FIRST-WAVE  on a line long enough to carry waves, the receiver's first-incident level misses VIH (rising) or VIL (falling) at some
                        corner: the receiver waits for a reflection. The model's levels are in the message.
    OFFCHIP-RINGBACK    the edge crosses the threshold and then rings back through it (a double clock edge, a glitch).
    OFFCHIP-DRIVE-MATCH the output resistance plus series resistor is far from Z0 (more than 50 % at the typical corner, or the pull-up and
                        the pull-down differ by more than 40 %) on a line that is electrically long.
    OFFCHIP-NO-TERM     a long, unterminated line whose receiver ringing exceeds a quarter of VCCO.
    OFFCHIP-VCCO        the IOSTANDARD's supply conflicts with the group's ``vcco``, with another group of the same bank, with the receiver's
                        standard (an output above the receiver's VCCO+0.55 V absolute maximum), or the standard does not exist in the bank type.
    OFFCHIP-DRIVE-ILLEGAL  a DRIVE or SLEW the bank type does not allow (UG471 Table 1-8; UG571 Tables 1-12 and 3-2).
    OFFCHIP-NO-LOAD-DATA   a port that sets DRIVE or SLEW in the XDC, or is an output, and no group names it.
    OFFCHIP-DIFF-TERM   a differential input standard with no on-chip or declared termination (property by family: DIFF_TERM on 7 series,
                        DIFF_TERM_ADV on UltraScale+).

``propose`` returns, per group, the IOSTANDARD, DRIVE, SLEW and series resistor that satisfy every limit at every corner, with the
margins, ranked by the group's ``priority``. Raw findings carry the numbers and the source of the driver data (IBIS file, revision, model).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import math
import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

try:
    from flow import offchip_model as M
except ImportError:                      # run as a script: flow/ is on sys.path
    import offchip_model as M

GROUP_KEYS = ("name", "ports", "direction", "iostandard", "vcco", "bank", "bank_type", "line", "load", "external", "priority", "ui_ns", "max_rise_ns", "min_drive_ma",
              "board_fixed")
#: a proposal needs this much first-incident margin (V) over VIH/VIL at the worst corner, and a receiver 20-80 % time at the weak corner no longer than
#: this share of the unit interval unless the group gives ``max_rise_ns`` (both are house assumptions, written here so they can be changed in one place)
FIRST_WAVE_GUARD_V = 0.10
RISE_FRACTION_OF_UI = 0.25
DIRECTIONS = ("output", "input", "inout")
PRIORITIES = ("edge_rate", "emi", "balanced")
STD_VCCO = {"LVCMOS33": 3.3, "LVTTL": 3.3, "LVCMOS25": 2.5, "LVCMOS18": 1.8, "LVCMOS15": 1.5, "LVCMOS12": 1.2}
DIFF_STD = {"LVDS", "LVDS_25", "MINI_LVDS_25", "PPDS_25", "RSDS_25", "SUB_LVDS", "BLVDS_25", "TMDS_33"}
DEFAULT_DRIVE, DEFAULT_SLEW = 12, "SLOW"          # UG471 (Output Drive Strength / Output Slew Rate Attributes), UG571 (same sections)
#: allowed DRIVE (mA) by (family class, bank type) and standard. UG471 Table 1-8 (7 series); UG571 Table 1-12 (US+ HP) and Table 3-2 (HD)
ALLOWED_DRIVE: dict[tuple[str, str], dict[str, tuple[int, ...]]] = {
    ("7series", "HR"): {"LVCMOS12": (4, 8, 12), "LVCMOS15": (4, 8, 12, 16), "LVCMOS18": (4, 8, 12, 16, 24), "LVCMOS25": (4, 8, 12, 16),
                        "LVCMOS33": (4, 8, 12, 16), "LVTTL": (4, 8, 12, 16, 24)},
    ("7series", "HP"): {"LVCMOS12": (2, 4, 6, 8), "LVCMOS15": (2, 4, 6, 8, 12, 16), "LVCMOS18": (2, 4, 6, 8, 12, 16)},
    ("ultrascale_plus", "HP"): {"LVCMOS12": (2, 4, 6, 8), "LVCMOS15": (2, 4, 6, 8, 12), "LVCMOS18": (2, 4, 6, 8, 12)},
    ("ultrascale_plus", "HD"): {"LVCMOS12": (4, 8, 12), "LVCMOS15": (4, 8, 12, 16), "LVCMOS18": (4, 8, 12, 16), "LVCMOS25": (4, 8, 12, 16),
                                "LVCMOS33": (4, 8, 12, 16), "LVTTL": (4, 8, 12, 16)},
}
ALLOWED_SLEW = {("7series", "HR"): ("SLOW", "FAST"), ("7series", "HP"): ("SLOW", "FAST"),
                ("ultrascale_plus", "HP"): ("SLOW", "MEDIUM", "FAST"), ("ultrascale_plus", "HD"): ("SLOW", "FAST")}
#: allowed overshoot / undershoot duration (percent of a UI) against peak (V beyond VCCO or below GND). DS181 Table 4 and DS187 Table 4
#: (7 series HR), DS925 Table 7 (US+ HP) and Table 6 (HD). Overshoot is measured above VCCO, undershoot below 0 V.
_T4_OVER = [(0.55, 100.0), (0.60, 46.6), (0.65, 21.2), (0.70, 9.75), (0.75, 4.55), (0.80, 2.15), (0.85, 1.02), (0.90, 0.49), (0.95, 0.24)]
_T4_UNDER = [(0.40, 100.0), (0.45, 61.7), (0.50, 25.8), (0.55, 11.0), (0.60, 4.77), (0.65, 2.10), (0.70, 0.94), (0.75, 0.43), (0.80, 0.20),
             (0.85, 0.09), (0.90, 0.04), (0.95, 0.02)]
_T7 = [(0.30, 100.0), (0.35, 100.0), (0.40, 92.0), (0.45, 50.0), (0.50, 20.0), (0.55, 10.0), (0.60, 6.0), (0.65, 2.0), (0.70, 2.0)]
_T6_OVER = [(0.30, 100.0), (0.35, 100.0), (0.40, 100.0), (0.45, 100.0), (0.50, 100.0), (0.55, 100.0), (0.60, 100.0), (0.65, 100.0), (0.70, 92.0),
            (0.75, 92.0), (0.80, 92.0), (0.85, 92.0), (0.90, 92.0), (0.95, 92.0)]
_T6_UNDER = [(0.30, 100.0), (0.35, 90.0), (0.40, 78.0), (0.45, 40.0), (0.50, 24.0), (0.55, 18.0), (0.60, 13.0), (0.65, 10.8), (0.70, 9.0),
             (0.75, 7.0), (0.80, 6.0), (0.85, 5.0), (0.90, 4.0), (0.95, 2.5)]
LIMIT_SOURCE = {("7series", "HR"): "DS181 v1.27.1 Tables 1, 2, 4 (HR banks); DS187 Table 4 gives the same overshoot table for Zynq-7000 HR",
                ("7series", "HP"): "DS182/DS183 are not in the local library: the HR table is used, an assumption",
                ("ultrascale_plus", "HP"): "DS925 v1.30 Tables 1, 2 and 7 (HP banks)", ("ultrascale_plus", "HD"): "DS925 v1.30 Tables 1, 2 and 6 (HD banks)"}
E_SERIES_RS = (0.0, 10.0, 15.0, 22.0, 27.0, 33.0, 47.0)
TERMS = {   # name -> (series ohm, load kwargs as fractions of z0) ; used by the study and the proposals
    "none": (0.0, {}), "series_10": (10.0, {}), "series_15": (15.0, {}), "series_22": (22.0, {}), "series_33": (33.0, {}), "series_47": (47.0, {}),
    "parallel_gnd": (0.0, {"r_gnd": 1.0}), "parallel_vtt": (0.0, {"r_vtt": 1.0}), "thevenin": (0.0, {"r_gnd": 2.0, "r_vcc": 2.0}),
    "ac": (0.0, {"ac_r": 1.0}),
}


def family_class(family: str = "", part: str = "") -> str:
    f = (family or "").lower().replace("-", "").replace(" ", "")
    p = (part or "").lower()
    if any(x in f for x in ("ultrascale", "zynqmp", "zynquplus", "kria")) or re.match(r"xc(zu|ku\d+p|vu\d+p|k26)|xck26", p):
        return "ultrascale_plus"
    return "7series"


def model_family(fc: str, bank_type: str) -> str:
    return "zynquplus" if fc == "ultrascale_plus" else ("zynq" if bank_type == "HP" else "artix7")


def _interp(table: list[tuple[float, float]], x: float) -> float:
    """Allowed share of a UI at a peak of ``x`` V beyond the rail: the table's next-lower row (the data sheet lists steps)."""
    if x < table[0][0]:
        return 100.0
    best = table[0][1]
    for v, p in table:
        if x + 1e-9 >= v:
            best = p
    return best


def rx_limits(fc: str, bank_type: str) -> dict[str, Any]:
    over, under = {("7series", "HR"): (_T4_OVER, _T4_UNDER), ("7series", "HP"): (_T4_OVER, _T4_UNDER),
                   ("ultrascale_plus", "HP"): (_T7, _T7), ("ultrascale_plus", "HD"): (_T6_OVER, _T6_UNDER)}[(fc, bank_type)]
    return {"roc_over": 0.20, "roc_under": 0.20, "abs_over": 0.55, "abs_under": 0.40 if fc == "7series" else 0.55, "over_table": over,
            "under_table": under, "source": LIMIT_SOURCE[(fc, bank_type)]}


# --- the spec section ------------------------------------------------------------------------------------------------------------

def off_chip_errors(groups: Any) -> list[str]:
    """Shape errors of a spec's ``off_chip:`` list (the clarify gate calls this; empty list: valid)."""
    if groups is None:
        return []
    if not isinstance(groups, list) or not groups:
        return ["'off_chip' must be a non-empty list of port groups"]
    errs: list[str] = []
    names: set[str] = set()
    for i, g in enumerate(groups):
        w = f"off_chip[{i}]"
        if not isinstance(g, dict):
            errs.append(f"{w} must be a mapping")
            continue
        w = f"off_chip[{g.get('name', i)}]"
        for k in g:
            if k not in GROUP_KEYS:
                errs.append(f"{w}: unknown key {k!r} (allowed: {', '.join(GROUP_KEYS)})")
        if not g.get("name"):
            errs.append(f"{w}: 'name' is required")
        elif g["name"] in names:
            errs.append(f"{w}: duplicate group name")
        names.add(str(g.get("name")))
        p = g.get("ports")
        if not (isinstance(p, list) and p and all(isinstance(x, str) for x in p)):
            errs.append(f"{w}: 'ports' must be a non-empty list of port names or globs")
        if g.get("direction", "output") not in DIRECTIONS:
            errs.append(f"{w}: 'direction' must be one of {', '.join(DIRECTIONS)}")
        if g.get("priority", "balanced") not in PRIORITIES:
            errs.append(f"{w}: 'priority' must be one of {', '.join(PRIORITIES)}")
        line = g.get("line", "short")
        if line != "short":
            if not isinstance(line, dict) or not isinstance(line.get("length_in"), (int, float)) or line["length_in"] <= 0:
                errs.append(f"{w}: 'line' must be 'short' or a mapping with a positive length_in (z0_ohm defaults to 50)")
            elif "z0_ohm" in line and not (isinstance(line["z0_ohm"], (int, float)) and 20 <= line["z0_ohm"] <= 150):
                errs.append(f"{w}: line.z0_ohm must be a number between 20 and 150")
        load = g.get("load")
        if g.get("direction", "output") != "input":
            if not isinstance(load, dict) or not isinstance(load.get("c_pf"), (int, float)) or load["c_pf"] < 0:
                errs.append(f"{w}: an output needs load.c_pf (receiver pin and stub capacitance, pF) so the model has something to drive")
        for k in ("ui_ns", "max_rise_ns", "min_drive_ma"):
            if k in g and not (isinstance(g[k], (int, float)) and g[k] > 0):
                errs.append(f"{w}: {k} must be a positive number")
        if "board_fixed" in g and not isinstance(g["board_fixed"], bool):
            errs.append(f"{w}: board_fixed must be true or false")
        if "bank_type" in g and g["bank_type"] not in ("HR", "HP", "HD"):
            errs.append(f"{w}: bank_type must be HR, HP or HD")
        ext = g.get("external")
        if ext is not None and not (isinstance(ext, dict) and all(k in ("series_ohm", "parallel_gnd_ohm", "thevenin_ohm", "ac_ohm") for k in ext)):
            errs.append(f"{w}: 'external' keys must be series_ohm, parallel_gnd_ohm, thevenin_ohm or ac_ohm")
    return errs


# --- the XDC -----------------------------------------------------------------------------------------------------------------------

_SET = re.compile(r"^\s*set_property\s+(.*?)\s*\[\s*get_ports\s+(.*)\]\s*;?\s*$", re.I)


def parse_xdc(text: str) -> dict[str, dict[str, str]]:
    """port -> properties, from ``set_property -dict {K V ...} [get_ports p]`` and ``set_property K V [get_ports p]`` (comments skipped)."""
    out: dict[str, dict[str, str]] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0] if not raw.lstrip().startswith("#") else ""
        m = _SET.match(line)
        if not m:
            continue
        body, ports = m.group(1), m.group(2).strip().strip("{}").strip()
        if body.startswith("-dict"):
            kv = re.findall(r"(\w+)\s+([^\s}]+)", body[len("-dict"):].replace("{", " ").replace("}", " "))
        else:
            t = body.split()
            kv = [(t[0], t[1])] if len(t) >= 2 else []
        for p in ports.split():
            p = p.strip("{}")
            for k, v in kv:
                out.setdefault(p, {})[k.upper()] = v
    return out


def _port_re(pat: str) -> re.Pattern[str]:
    return re.compile("^" + "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pat) + "$")


def ports_of(group: dict[str, Any], names: list[str]) -> list[str]:
    pats = [_port_re(p) for p in group["ports"]]
    base = {p: p.split("[")[0] for p in names}
    return [n for n in names if any(r.match(n) or r.match(base[n]) for r in pats)]


# --- evaluation ---------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    std: str
    drive: int
    slew: str
    rs: float = 0.0
    term: str = "none"            # key of TERMS' load part (parallel_gnd, ...)


def _load_for(term: str, z0: float, c_pf: float, ext: dict[str, Any] | None) -> M.Load:
    kw = dict(TERMS.get(term, (0.0, {}))[1])
    load = M.Load(c_pf=c_pf)
    for k, f in kw.items():
        if k == "ac_r":
            load.ac_r = f * z0
        else:
            setattr(load, k, f * z0)
    if ext:
        if ext.get("parallel_gnd_ohm"):
            load.r_gnd = float(ext["parallel_gnd_ohm"])
        if ext.get("thevenin_ohm"):
            load.r_gnd = load.r_vcc = float(ext["thevenin_ohm"])
        if ext.get("ac_ohm"):
            load.ac_r = float(ext["ac_ohm"])
    return load


@lru_cache(maxsize=4096)
def evaluate_cached(model_fam: str, bank_type: str, std: str, drive: int, slew: str, rs: float, term: str, z0: float,
                    length_in: float, c_pf: float, er_eff: float, ext: tuple, vil: float | None, vih: float | None) -> dict[str, Any]:
    return evaluate(model_fam, bank_type, std, drive, slew, rs, term, z0, length_in, c_pf, er_eff, dict(ext) if ext else None, vil, vih)


def evaluate(model_fam: str, bank_type: str, std: str, drive: int, slew: str, rs: float, term: str, z0: float, length_in: float,
             c_pf: float, er_eff: float = 3.2, ext: dict | None = None, vil: float | None = None, vih: float | None = None) -> dict[str, Any]:
    """All corners, both edges, for one configuration. ``length_in`` 0 or small: a lumped load (the line is made 0.3 in long)."""
    key = M.model_key(model_fam, std, drive, slew, bank_type if model_fam != "artix7" else "")
    if key is None:
        return {"error": f"no IBIS model for {std} DRIVE {drive} SLEW {slew} in {model_fam} {bank_type} banks"}
    line = M.Line(z0, max(length_in, 0.3), er_eff)
    load = _load_for(term, z0, c_pf, ext)
    corners: dict[str, Any] = {}
    for c in M.CORNERS:
        d = M.get_driver(key, c)
        if vil is not None:
            d.vinl = vil
        if vih is not None:
            d.vinh = vih
        res = M.both_edges(d, line, load, rs)
        for e in ("r", "f"):
            fi = M.first_incident(d, line, load, rs, e)
            m = res[e].metrics
            m["first_incident_always_v"], m["first_incident_margin_always_v"] = fi["v_first_incident"], fi["margin_v"]
            m["first_incident_margin_v"] = None if m["lumped"] else fi["margin_v"]     # visible only when the edge is shorter than the round trip
        rl = M.r_launch(d, z0 + rs)
        corners[c] = {"vcc": d.vcc, "r_pu": rl["r_pu"], "r_pd": rl["r_pd"], "r_small_pu": rl["r_small_pu"], "r_small_pd": rl["r_small_pd"],
                      "rise": res["r"].metrics, "fall": res["f"].metrics}
    allm = [corners[c][e] for c in corners for e in ("rise", "fall")]
    fi = [m["first_incident_margin_v"] for m in allm if m["first_incident_margin_v"] is not None]
    rb = [m["ringback_margin_v"] for m in allm if m["ringback_margin_v"] is not None]
    t_over = max(m["t_over_roc_ns"] for m in allm)
    t_under = max(m["t_under_roc_ns"] for m in allm)
    fa = [m["first_incident_margin_always_v"] for m in allm]
    return {"key": key, "source": M.source_for(key), "corners": corners, "min_first_incident_margin_always_v": min(fa),
            "worst_over_vcco_v": max(m["over_vcco_v"] for m in allm), "worst_under_gnd_v": max(m["under_gnd_v"] for m in allm),
            "t_over_roc_ns": t_over, "t_under_roc_ns": t_under,
            "min_first_incident_margin_v": min(fi) if fi else None, "min_ringback_margin_v": min(rb) if rb else None,
            "max_settle_ns": max(m["settle_ns"] for m in allm), "max_ring_pp_v": max((m["ring_pp_v"] or 0.0) for m in allm),
            "rx_rise_2080_ns": {c: corners[c]["rise"]["rise_2080_ns"] for c in corners},
            "lumped": all(m["lumped"] for m in allm), "t_edge_ns": {c: corners[c]["rise"]["t_edge_ns"] for c in corners},
            "z0": z0, "rs": rs, "term": term, "length_in": length_in, "c_pf": c_pf, "vcco": corners["typ"]["vcc"]}


@dataclass
class Finding:
    code: str
    severity: str          # 'advisory' (the whole check is advisory), 'contradicts-model' for an XDC value the model says breaks a data-sheet limit
    group: str
    text: str
    numbers: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "severity": self.severity, "group": self.group, "text": self.text, "numbers": self.numbers}


def judge(ev: dict[str, Any], limits: dict[str, Any], line_is_long: bool, ui_ns: float) -> list[tuple[str, str, str]]:
    """(code, severity, text) for one evaluation against the receiver limits. No flags: the configuration is clean at every corner."""
    out: list[tuple[str, str, str]] = []
    vcco = ev["vcco"]
    over, under = ev["worst_over_vcco_v"], ev["worst_under_gnd_v"]
    for name, val, tab, tdur in (("overshoot", over, limits["over_table"], ev["t_over_roc_ns"]), ("undershoot", under, limits["under_table"], ev["t_under_roc_ns"])):
        if val > limits["roc_over"]:
            allowed = _interp(tab, val)
            share = 100.0 * tdur / ui_ns
            bad = share > allowed
            out.append(("OFFCHIP-OVERSHOOT", "contradicts-model" if bad else "advisory",
                        f"receiver {name} {val:+.2f} V beyond the rail at the worst IBIS corner (recommended limit 0.20 V); it spends {tdur:.2f} ns beyond "
                        f"0.20 V ({share:.1f} % of a {ui_ns:g} ns UI) against {allowed:g} % allowed at that peak ({limits['source']})"))
    if line_is_long and ev["min_first_incident_margin_v"] is not None and ev["min_first_incident_margin_v"] < 0:
        out.append(("OFFCHIP-FIRST-WAVE", "contradicts-model",
                    f"first incident wave misses the receiver threshold by {-ev['min_first_incident_margin_v']:.2f} V at the worst corner: the receiver "
                    "waits for a reflection (output resistance plus series resistor above Z0)"))
    if ev["min_ringback_margin_v"] is not None and ev["min_ringback_margin_v"] < 0:
        out.append(("OFFCHIP-RINGBACK", "contradicts-model",
                    f"the edge rings back through the receiver threshold by {-ev['min_ringback_margin_v']:.2f} V (a double edge or glitch on a clock or strobe)"))
    return out


# --- proposal ----------------------------------------------------------------------------------------------------------------------------

def _mismatch(ev: dict[str, Any]) -> float:
    """Worst relative distance of (R_launch + Rs) from Z0 over corners and halves."""
    z0, rs = ev["z0"], ev["rs"]
    return max(abs(ev["corners"][c][k] + rs - z0) / z0 for c in ev["corners"] for k in ("r_pu", "r_pd"))


def candidates(fc: str, bank_type: str, std: str, priority: str, min_drive: float = 0.0) -> list[tuple[int, str]]:
    drives = tuple(d for d in ALLOWED_DRIVE.get((fc, bank_type), {}).get(std, ()) if d >= min_drive)
    slews = ALLOWED_SLEW[(fc, bank_type)]
    return [(d, s) for d in drives for s in slews]


def propose(group: dict[str, Any], fc: str, bank_type: str, std: str | None = None, max_sims: int = 14, mode: str = "auto") -> dict[str, Any]:
    """The configuration to put in the XDC (and on the board) for one output group, or the reason there is none.

    Shortlist by the static match (output resistance plus series resistor against Z0 at all corners), simulate the best ``max_sims`` and
    keep those that pass every limit at every corner; rank by priority: ``edge_rate`` prefers the fastest receiver edge, a lumped load (``line: short``) the gentlest output (SLOW, lowest DRIVE), ``emi`` the
    slowest strong-corner edge among those whose weak-corner receiver 20-80 % time meets ``max_rise_ns`` (default a quarter of the UI), ``balanced`` the smallest
    worst-case mismatch; a proposal needs a first-incident margin of at least ``FIRST_WAVE_GUARD_V`` at every corner; ties go to no series
    resistor, then the lower DRIVE.

    ``mode`` (brief 164, owner decision 30): ``auto`` keeps the older rule (``external.series_ohm`` fixes the resistor, otherwise it is chosen);
    ``as_built`` always keeps the board's resistor (``external.series_ohm``, 0 ohm if none) and tries every allowed DRIVE and SLEW; ``free`` chooses the
    resistor too (the E-series values, 0 ohm allowed) and ignores ``external.series_ohm``. When nothing passes, ``least_bad`` names the setting with the
    smallest worst overshoot or undershoot and its margin to the 0.2 V limit (negative: beyond it)."""
    assert mode in ("auto", "as_built", "free"), mode
    std = std or group.get("iostandard") or "LVCMOS33"
    line = group.get("line", "short")
    short = line == "short"
    z0 = 50.0 if short else float(line.get("z0_ohm", 50.0))
    length = 0.3 if short else float(line["length_in"])
    c_pf = float((group.get("load") or {}).get("c_pf", 5.0))
    ext = group.get("external") or {}
    ui = float(group.get("ui_ns", 10.0))
    max_rise = float(group.get("max_rise_ns", RISE_FRACTION_OF_UI * ui))
    limits = rx_limits(fc, bank_type)
    mfam = model_family(fc, bank_type)
    fixed_rs = float(ext["series_ohm"]) if ext.get("series_ohm") is not None else None
    if mode == "as_built":
        fixed_rs = fixed_rs if fixed_rs is not None else 0.0
    elif mode == "free":
        fixed_rs = None
    ext_t = tuple(sorted((k, v) for k, v in ext.items() if k != "series_ohm"))
    term = "none"
    shortlist = []
    for drive, slew in candidates(fc, bank_type, std, group.get("priority", "balanced"), float(group.get("min_drive_ma", 0))):
        # a lumped load has no line to match: a series resistor only slows the edge, so it is not offered unless the spec fixes one
        for rs in ([fixed_rs] if fixed_rs is not None else ([0.0] if short else list(E_SERIES_RS))):
            shortlist.append((drive, slew, rs))
    # static prefilter using the typical corner chord resistance only (cheap): keep the closest matches
    scored = []
    for drive, slew, rs in shortlist:
        key = M.model_key(mfam, std, drive, slew, bank_type if mfam != "artix7" else "")
        if key is None:
            continue
        mm = 0.0
        for c in M.CORNERS:
            rl = M.r_launch(M.get_driver(key, c), z0 + rs)
            mm = max(mm, abs(rl["r_pu"] + rs - z0) / z0, abs(rl["r_pd"] + rs - z0) / z0)
        scored.append((mm, drive, slew, rs))
    scored.sort(key=lambda x: (x[0], x[3], x[1]))
    if short or mode == "as_built":
        max_sims = len(scored)                  # every allowed DRIVE and SLEW: few, and the static match means nothing without a line
    # the shortlist must include every slew of the best drive/Rs pairs, so take the best by mismatch but keep distinct (drive, rs) pairs
    results = []
    for mm, drive, slew, rs in scored[:max_sims]:
        ev = evaluate_cached(mfam, bank_type, std, drive, slew, rs, term, z0, length, c_pf, 3.2, ext_t, (group.get("load") or {}).get("vil_v"),
                             (group.get("load") or {}).get("vih_v"))
        flags = judge(ev, limits, not short and not ev["lumped"], ui)
        rise_weak = ev["rx_rise_2080_ns"]["min"]
        ok = (not flags and (short or ev["min_first_incident_margin_always_v"] >= FIRST_WAVE_GUARD_V)
              and (rise_weak is None or rise_weak <= max_rise))
        fi_short = (not short) and ev["min_first_incident_margin_always_v"] < FIRST_WAVE_GUARD_V
        edge_excess = max(0.0, (rise_weak or 0.0) - max_rise)
        why = ([] if not flags else sorted({f[0] for f in flags})) + (["first-incident margin under the guard"] if fi_short and not flags else []) \
            + ([f"weak-corner edge {rise_weak:.2f} ns over the {max_rise:g} ns allowed"] if edge_excess > 0 else [])
        results.append({"drive": drive, "slew": slew, "rs_ohm": rs, "static_mismatch": round(mm, 3), "pass": ok, "flags": [f[0] for f in flags],
                        "fails": why, "edge_excess_ns": round(edge_excess, 3), "max_rise_ns": max_rise,
                        "worst_over_v": round(ev["worst_over_vcco_v"], 3), "worst_under_v": round(ev["worst_under_gnd_v"], 3),
                        "first_incident_margin_v": ev["min_first_incident_margin_v"], "ringback_margin_v": ev["min_ringback_margin_v"],
                        "settle_ns": round(ev["max_settle_ns"], 2), "rx_rise_2080_ns": ev["rx_rise_2080_ns"], "source": ev["source"]})
    good = [r for r in results if r["pass"]]
    pri = group.get("priority", "balanced")
    if pri == "edge_rate":
        good.sort(key=lambda r: (r["rx_rise_2080_ns"]["min"] or 9e9, r["rs_ohm"] > 0, r["drive"]))
    elif short:
        good.sort(key=lambda r: (r["slew"] != "SLOW", r["drive"]))      # a lumped load: the gentlest output that passes (SLOW, then the lowest DRIVE)
    elif pri == "emi":
        good.sort(key=lambda r: (-(r["rx_rise_2080_ns"]["max"] or 0), r["rs_ohm"] > 0, r["drive"]))
    else:
        good.sort(key=lambda r: (r["static_mismatch"], r["rs_ohm"] > 0, r["drive"]))
    least_bad = None
    if not good and results:
        def _bad(r):      # data-sheet overshoot first, then the other flags, then the edge-time shortfall (house assumption)
            ds = max(r["worst_over_v"], r["worst_under_v"]) - limits["roc_over"]
            return (ds > 0, max(ds, 0.0), len([f for f in r["flags"] if f != "OFFCHIP-OVERSHOOT"]), r["edge_excess_ns"], r["rs_ohm"], r["drive"])
        lb = min(results, key=_bad)
        least_bad = dict(lb, margin_to_limit_v=round(limits["roc_over"] - max(lb["worst_over_v"], lb["worst_under_v"]), 3),
                         meets_data_sheet_overshoot=max(lb["worst_over_v"], lb["worst_under_v"]) <= limits["roc_over"])
    return {"group": group.get("name"), "iostandard": std, "z0_ohm": z0, "length_in": None if short else length, "c_pf": c_pf,
            "priority": pri, "mode": mode, "best": good[0] if good else None, "all_passing": good, "simulated": results, "least_bad": least_bad,
            "reason": None if good else "no allowed DRIVE/SLEW/series-resistor combination passes every limit at every corner: terminate the line "
                                        "(parallel, Thevenin or AC at the receiver), shorten it, or use a different standard"}


# --- the check ----------------------------------------------------------------------------------------------------------------------

def check(spec: dict[str, Any], xdc_text: str, fc: str, bank_type: str = "HR", default_vcco: dict[str, float] | None = None) -> dict[str, Any]:
    """Findings for a design: every ``off_chip`` group against the XDC."""
    props = parse_xdc(xdc_text)
    names = sorted(props)
    groups = spec.get("off_chip") or []
    findings: list[Finding] = []
    covered: set[str] = set()
    bank_vcco: dict[Any, tuple[float, str]] = {}
    mfam_cache = {}
    for g in groups:
        gname = g["name"]
        btype = g.get("bank_type", bank_type)
        ports = ports_of(g, names)
        covered.update(ports)
        if not ports:
            findings.append(Finding("OFFCHIP-NO-LOAD-DATA", "advisory", gname, "no XDC port matches this group's ports (nothing to check)"))
            continue
        # one evaluation per distinct (std, drive, slew) among the group's ports
        combos: dict[tuple[str, int, str], list[str]] = {}
        for p in ports:
            pr = props[p]
            std = pr.get("IOSTANDARD", g.get("iostandard", ""))
            drive = int(pr.get("DRIVE", DEFAULT_DRIVE))
            slew = pr.get("SLEW", DEFAULT_SLEW).upper()
            combos.setdefault((std, drive, slew), []).append(p)
        direction = g.get("direction", "output")
        line = g.get("line", "short")
        short = line == "short"
        z0 = 50.0 if short else float(line.get("z0_ohm", 50.0))
        length = 0.3 if short else float(line["length_in"])
        ext = g.get("external") or {}
        c_pf = float((g.get("load") or {}).get("c_pf", 5.0))
        ui = float(g.get("ui_ns", 10.0))
        limits = rx_limits(fc, btype)
        mfam = model_family(fc, btype)
        for (std, drive, slew), plist in combos.items():
            where = f"{gname}: {', '.join(plist[:3])}{'...' if len(plist) > 3 else ''} ({std} DRIVE {drive} SLEW {slew})"
            defaulted = [p for p in plist if "DRIVE" not in props[p] or "SLEW" not in props[p]]
            # bank and standard consistency
            vstd = STD_VCCO.get(std)
            vgrp = g.get("vcco")
            if vstd is not None and vgrp is not None and abs(vstd - float(vgrp)) > 0.05:
                findings.append(Finding("OFFCHIP-VCCO", "advisory", gname, f"{where}: {std} needs VCCO {vstd} V but the group says the bank is at {vgrp} V"))
            vc = float(vgrp) if vgrp is not None else vstd
            if g.get("bank") is not None and vc is not None:
                prev = bank_vcco.get(g["bank"])
                if prev and abs(prev[0] - vc) > 0.05:
                    findings.append(Finding("OFFCHIP-VCCO", "advisory", gname, f"bank {g['bank']} is at {vc} V here but {prev[0]} V in group {prev[1]}: one VCCO per bank"))
                bank_vcco.setdefault(g["bank"], (vc, gname))
            if std in STD_VCCO and std not in ALLOWED_DRIVE.get((fc, btype), {}) and direction != "input":
                findings.append(Finding("OFFCHIP-VCCO", "advisory", gname, f"{where}: {std} outputs do not exist in {btype} banks of this family class ({fc})"))
                continue
            if direction != "input" and std in STD_VCCO:
                if drive not in ALLOWED_DRIVE[(fc, btype)].get(std, ()):
                    findings.append(Finding("OFFCHIP-DRIVE-ILLEGAL", "advisory", gname,
                                            f"{where}: DRIVE {drive} is not allowed for {std} in {btype} banks (allowed {ALLOWED_DRIVE[(fc, btype)].get(std)})"))
                if slew not in ALLOWED_SLEW[(fc, btype)]:
                    findings.append(Finding("OFFCHIP-DRIVE-ILLEGAL", "advisory", gname, f"{where}: SLEW {slew} is not allowed in {btype} banks (allowed {ALLOWED_SLEW[(fc, btype)]})"))
            rstd = (g.get("load") or {}).get("receiver_std")
            if direction != "input" and rstd in STD_VCCO and vc is not None and STD_VCCO[rstd] + limits["abs_over"] < vc - 0.0:
                findings.append(Finding("OFFCHIP-VCCO", "contradicts-model", gname,
                                        f"{where}: the driver swings to {vc} V but the receiver ({rstd}, VCCO {STD_VCCO[rstd]} V) tolerates at most "
                                        f"{STD_VCCO[rstd] + limits['abs_over']:.2f} V: a level translator is needed"))
            if direction == "input" and std in DIFF_STD:
                term_prop = "DIFF_TERM_ADV" if fc == "ultrascale_plus" else "DIFF_TERM"
                if not any(str(props[p].get(term_prop, "")).upper() in ("TRUE", "TERM_100") for p in plist) and not ext.get("parallel_gnd_ohm") and not (g.get("load") or {}).get("diff_term_external"):
                    findings.append(Finding("OFFCHIP-DIFF-TERM", "advisory", gname,
                                            f"{where}: differential input with no termination: set {term_prop} ({'TRUE' if term_prop == 'DIFF_TERM' else 'TERM_100'}) or declare an external 100 ohm "
                                            f"(load.diff_term_external: true)"))
            if direction == "input" or std not in STD_VCCO:
                continue
            rs = float(ext.get("series_ohm", 0.0))
            ev = evaluate_cached(mfam, btype, std, drive, slew, rs, "none", z0, length, c_pf, 3.2,
                                 tuple(sorted((k, v) for k, v in ext.items() if k != "series_ohm")), (g.get("load") or {}).get("vil_v"), (g.get("load") or {}).get("vih_v"))
            if "error" in ev:
                findings.append(Finding("OFFCHIP-DRIVE-ILLEGAL", "advisory", gname, f"{where}: {ev['error']}"))
                continue
            long_line = (not short) and not ev["lumped"]
            nums = {"source": ev["source"], "worst_over_v": round(ev["worst_over_vcco_v"], 3), "worst_under_v": round(ev["worst_under_gnd_v"], 3),
                    "first_incident_margin_v": ev["min_first_incident_margin_v"], "ringback_margin_v": ev["min_ringback_margin_v"],
                    "r_pu_ohm": {c: round(ev["corners"][c]["r_pu"], 1) for c in ev["corners"]}, "r_pd_ohm": {c: round(ev["corners"][c]["r_pd"], 1) for c in ev["corners"]},
                    "defaulted_ports": defaulted}
            for code, sev, text in judge(ev, limits, long_line, ui):
                findings.append(Finding(code, sev, gname, f"{where}: {text}", nums))
            if long_line:
                mm = _mismatch(ev)
                asym = max(abs(ev["corners"]["typ"]["r_pu"] - ev["corners"]["typ"]["r_pd"]) / z0, 0)
                if abs(ev["corners"]["typ"]["r_pu"] + rs - z0) / z0 > 0.5 or abs(ev["corners"]["typ"]["r_pd"] + rs - z0) / z0 > 0.5:
                    findings.append(Finding("OFFCHIP-DRIVE-MATCH", "advisory", gname,
                                            f"{where}: output resistance plus series resistor is "
                                            f"{ev['corners']['typ']['r_pu'] + rs:.0f} ohm (pull-up) and {ev['corners']['typ']['r_pd'] + rs:.0f} ohm (pull-down) against Z0 {z0:g} ohm "
                                            f"(typical corner; worst corner mismatch {mm * 100:.0f} %)", nums))
                unterminated = not (ext.get("parallel_gnd_ohm") or ext.get("thevenin_ohm") or ext.get("ac_ohm")) and rs == 0.0
                if unterminated and ev["max_ring_pp_v"] > 0.25 * ev["vcco"]:
                    findings.append(Finding("OFFCHIP-NO-TERM", "advisory", gname,
                                            f"{where}: unterminated line {length:g} in long; receiver ringing {ev['max_ring_pp_v']:.2f} V peak to peak "
                                            f"(> a quarter of VCCO {ev['vcco']:g} V): add a series resistor at the source or a termination at the receiver", nums))
    # ports with no load data
    for p in names:
        if p in covered:
            continue
        pr = props[p]
        if "DRIVE" in pr or "SLEW" in pr:
            findings.append(Finding("OFFCHIP-NO-LOAD-DATA", "advisory", "-", f"{p}: the XDC sets DRIVE/SLEW ({pr.get('DRIVE', '-')}/{pr.get('SLEW', '-')}) but no off_chip group gives the "
                                    "load, so the value is not checked"))
    return {"findings": [f.as_dict() for f in findings], "groups": len(groups), "ports_checked": len(covered), "advisory": True}


DCI_NOTE = ("DCI and OUTPUT_IMPEDANCE are not offered: LVCMOS outputs only. Calibrated drivers (LVDCI, SSTL/HSTL/POD with OUTPUT_IMPEDANCE) are reported "
            "in docs/offchip_io.md section 1 but not simulated in the time domain.")


def propose_two(group: dict[str, Any], fc: str, bank_type: str, std: str | None = None) -> dict[str, Any]:
    """Two answers for one output group (owner decision 30): ``as_built`` (the best DRIVE/SLEW with the board's own series resistor,
    ``external.series_ohm``, 0 ohm if none) and ``optimal`` (the best series resistor with its DRIVE/SLEW, if the resistor can change).
    ``applies`` says which one the spec means: ``as_built`` when the group says ``board_fixed: true``, otherwise ``both``."""
    asb = propose(group, fc, bank_type, std, mode="as_built")
    opt = propose(group, fc, bank_type, std, mode="free")
    return {"group": group.get("name"), "board_fixed": bool(group.get("board_fixed", False)),
            "applies": "as_built" if group.get("board_fixed") else "both",
            "board_series_ohm": float((group.get("external") or {}).get("series_ohm") or 0.0),
            "as_built": asb, "optimal": opt, "dci": DCI_NOTE}


def propose_all(spec: dict[str, Any], fc: str, bank_type: str = "HR") -> list[dict[str, Any]]:
    """One older-style proposal per output group (kept for the 155 tools); the two-answer form is ``propose_two_all``."""
    return [propose(g, fc, g.get("bank_type", bank_type)) for g in (spec.get("off_chip") or []) if g.get("direction", "output") != "input"]


def propose_two_all(spec: dict[str, Any], fc: str, bank_type: str = "HR") -> list[dict[str, Any]]:
    return [propose_two(g, fc, g.get("bank_type", bank_type)) for g in (spec.get("off_chip") or []) if g.get("direction", "output") != "input"]


def _one(p: dict[str, Any] | None) -> str:
    if not p:
        return "none"
    r = f"DRIVE {p['drive']} SLEW {p['slew']}, series {p['rs_ohm']:g} ohm"
    return (f"{r} (overshoot {p['worst_over_v']:+.2f} V, undershoot {p['worst_under_v']:+.2f} V beyond the rail, "
            f"edge {p['rx_rise_2080_ns']['min']:.2f} ns at the weak corner)")


def proposal_text(t: dict[str, Any]) -> list[str]:
    """Plain lines for one ``propose_two`` result: the as-built answer, then the optimal one, then which applies."""
    lines = []
    for key, label in (("as_built", f"best for the board as built (series {t['board_series_ohm']:g} ohm, not changed)"),
                       ("optimal", "optimal if the series resistor can be changed")):
        p = t[key]
        if p["best"]:
            lines.append(f"OFFCHIP-PROPOSAL [advisory] {t['group']}: {label}: {_one(p['best'])}; {len(p['all_passing'])} passing combination(s).")
        elif p["least_bad"]:
            lb = p["least_bad"]
            lines.append(f"OFFCHIP-PROPOSAL [advisory] {t['group']}: {label}: NO setting meets every limit. Least bad: {_one(lb)}; margin to the 0.2 V "
                         f"over/undershoot limit {lb['margin_to_limit_v']:+.2f} V ({'met' if lb['meets_data_sheet_overshoot'] else 'exceeded'}); "
                         f"it fails: {'; '.join(lb['fails']) or 'a first-incident or ringback test'}.")
        else:
            lines.append(f"OFFCHIP-PROPOSAL [advisory] {t['group']}: {label}: no allowed setting could be simulated.")
    lines.append(f"OFFCHIP-PROPOSAL [advisory] {t['group']}: " + ("the spec says the board is fixed: the as-built answer applies." if t["board_fixed"]
                 else "the spec does not say the board is fixed: both answers are offered; the first needs no board change."))
    return lines


def resolve_target(spec: dict[str, Any], family: str | None, part: str | None, bank_type: str | None) -> tuple[str, str, str]:
    """Family, part and bank type: a command-line value wins, then the spec's own ``family:``, ``part:`` and ``bank_type:`` keys, then the old
    defaults (artix7, no part, HR). Before brief 164 the spec's keys were ignored, so a K26 spec was judged with Zynq-7000 models."""
    return (family or spec.get("family") or "artix7", part or spec.get("part") or "", bank_type or spec.get("bank_type") or "HR")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spec", required=True)
    ap.add_argument("--xdc", action="append", default=[])
    ap.add_argument("--family", default=None, help="default: the spec's `family:` key, else artix7")
    ap.add_argument("--part", default=None, help="default: the spec's `part:` key")
    ap.add_argument("--bank-type", default=None, help="default: the spec's `bank_type:` key, else HR")
    ap.add_argument("--propose", action="store_true", help="(default on) two answers per output port group: as built and optimal")
    ap.add_argument("--no-propose", action="store_true", help="findings only")
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    spec = yaml.safe_load(Path(a.spec).read_text()) or {}
    errs = off_chip_errors(spec.get("off_chip"))
    if errs:
        print("\n".join(errs))
        return 2
    family, part, bank_type = resolve_target(spec, a.family, a.part, a.bank_type)
    fc = family_class(family, part)
    text = "\n".join(Path(x).read_text() for x in a.xdc)
    res = check(spec, text, fc, bank_type)
    out: dict[str, Any] = {"check": res, "target": {"family": family, "part": part, "bank_type": bank_type, "family_class": fc}}
    if not a.no_propose:
        out["proposals"] = propose_two_all(spec, fc, bank_type)
    for f in res["findings"]:
        print(f"{f['code']} [{f['severity']}] {f['text']}")
    if not res["findings"]:
        print("OFFCHIP: no findings (advisory)")
    for t in out.get("proposals", []):
        print("\n".join(proposal_text(t)))
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
