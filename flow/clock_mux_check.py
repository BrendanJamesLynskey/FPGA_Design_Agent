#!/usr/bin/env python3
"""The clock-multiplexer check (brief 208): is every clock mux built from a clock buffer, constrained so that the
modes it cannot run at once are not timed together, and constrained so that nothing real is hidden?

    python3 flow/clock_mux_check.py <clock_mux.tsv> [--clock-interaction <report_clock_interaction>] [--family 7|us] [--json]

Inputs (both written in the check suite's one Vivado session, flow/checks/vivado_checks.tcl, or by any build):

    clock_mux.tsv                 flow/clock_mux_dump.tcl: the part, each clock-buffer mux (BUFGMUX, BUFGMUX_CTRL, BUFGCTRL), its
                                  inputs and their clocks, the clocks on its output, its control pins (constant or driven),
                                  the registers it clocks, and the structural paths between those registers and registers on
                                  other clock trees (UG949 Fig. 101: A into the mux fanout, C out of it); and every LUT whose
                                  output reaches a clock pin
    report_clock_interaction      the "Inter-Clock Constraints" column (Timed, Clock Group, Asynchronous Groups, ...)

Rules (codes map to FDA-HDL rule HDL-CLK-03 in flow/hdl_rules.yaml):

    CLKMUX-LUT          (blocking) a LUT output reaches a clock pin: a clock mux or gate built in fabric. Brief 208 c3:
                        an RTL mux glitched on every one of 40 asynchronous select changes in simulation (runt pulses down
                        to 25 ps); Vivado reports TIMING-14 for it. Build it with a BUFGCTRL (BUFGMUX_CTRL) instead.
    CLKMUX-NO-GROUPS    (blocking) two or more clocks reach a mux output and some pair of them is still timed against the
                        other (report_clock_interaction "Timed"): the timer checks paths between modes that cannot exist
                        at the same time in hardware (UG903 ch. 3; UG949 ch. 4 "Constraining Exclusive Clock Groups").
    CLKMUX-SRC-GROUPED  (blocking) the mux's SOURCE clocks are put in clock groups (exclusive or asynchronous) while a
                        register on a source clock's own tree exchanges data with a register on the mux fanout (paths A/C).
                        The group then also removes those real paths from timing and from report_cdc (brief 208 b1/b8).
                        Constrain generated clocks on the mux output instead (UG949 p.174 template).
    CLKMUX-CASE         (advisory) a mux whose select is not a constant in the netlist propagates fewer clocks than it
                        has distinct input clocks: a set_case_analysis (or a missing clock) leaves a mode untimed.
    CLKMUX-CE-SELECT    (advisory) a BUFGMUX (or a BUFGCTRL switched on CE0/CE1): its select must meet setup and hold to
                        both clocks or the output can glitch (UG472 ch. 2). Prefer BUFGMUX_CTRL or a BUFGCTRL switched on S.
    CLKMUX-STOP         (advisory) a mux input comes straight from a device pin (an external clock that can stop) and the
                        buffer has no driven IGNORE pin: if the selected clock stops, the switch never completes (brief
                        208 e2: locked up with the old clock stopped low or high). Use the safe-switch protocol.
    CLKMUX-CASCADE      (blocking) a chain of BUFGCTRLs longer than CASCADE_LIMIT, the dedicated cascade ring (UG472: 16 per
                        device half on 7 series; UG572: 8 on UltraScale): brief 208 d3 measured placement failing (Place
                        30-120, "Sub-optimal placement for a BUFG-BUFG cascade pair") for a chain of 17 on xc7a35t and of 9
                        on xck26, while chains of 7 placed. (advisory) more than two levels for a mux of four inputs or
                        fewer (UG949 ch. 3 "Clock Multiplexing": a balanced two-level tree).

Raw facts only in the messages; the house rule and the fixes live in hdl_rules.yaml and the KB skill.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

CASCADE_LIMIT = {"7": 16, "us": 8}
CONST_REFS = ("VCC", "GND", "-")
GROUPED = ("Clock Group", "Asynchronous Groups", "Exclusive", "Logically Exclusive", "Physically Exclusive")


def parse_dump(text: str) -> dict[str, Any]:
    """clock_mux.tsv -> {"muxes": {cell: {...}}, "luts": [...]}."""
    muxes: dict[str, dict[str, Any]] = {}
    luts: list[dict[str, Any]] = []
    part: dict[str, str] = {}

    def clocks(s: str) -> list[str]:
        return [] if s in ("-", "") else s.split(",")
    for ln in text.splitlines():
        f = ln.rstrip("\n").split("\t")
        if not f or not f[0]:
            continue
        kind = f[0]
        if kind == "PART" and len(f) >= 4:
            part = {"part": f[1], "arch": f[2], "family": f[3]}
        elif kind == "MUX" and len(f) >= 5:
            muxes[f[1]] = {"cell": f[1], "ref": f[2], "orig_ref": f[3], "inputs": [], "out_clocks": [], "ctl": {},
                           "fanout": 0, "inter": {"A": 0, "C": 0}, "inter_example": {}}
        elif kind == "MUXIN" and f[1] in muxes:
            muxes[f[1]]["inputs"].append({"pin": f[2], "driver": f[3], "driver_ref": f[4], "clocks": clocks(f[5])})
        elif kind == "MUXOUT" and f[1] in muxes:
            muxes[f[1]]["out_clocks"] = clocks(f[2])
        elif kind == "MUXCTL" and f[1] in muxes:
            muxes[f[1]]["ctl"][f[2]] = {"const": f[3], "driver": f[4], "driver_ref": f[5]}
        elif kind == "FANOUT" and f[1] in muxes:
            muxes[f[1]]["fanout"] = int(f[2])
        elif kind == "INTER" and f[1] in muxes:
            muxes[f[1]]["inter"][f[2]] = int(f[3])
            muxes[f[1]]["inter_example"][f[2]] = f[4]
        elif kind == "LUTCLK":
            luts.append({"cell": f[1], "ref": f[2], "clock_pins": int(f[3]), "clocks": clocks(f[4])})
    return {"muxes": muxes, "luts": luts, "part": part}


def _pair_constraints(pairs: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    return {(p["from"], p["to"]): p["constraints"] for p in pairs}


def _grouped(c: str) -> bool:
    return any(g.lower() in c.lower() for g in GROUPED)


def _is_buf(ref: str) -> bool:
    return ref.startswith("BUFG")


def _levels(cell: str, muxes: dict[str, Any], seen: frozenset[str] = frozenset()) -> int:
    """BUFGCTRL levels from the deepest input to this mux's output (1 = a single buffer)."""
    if cell in seen:
        return 1
    m = muxes[cell]
    deeper = [_levels(i["driver"], muxes, seen | {cell}) for i in m["inputs"] if i["driver"] in muxes]
    return 1 + (max(deeper) if deeper else 0)


def _leaves(cell: str, muxes: dict[str, Any], seen: frozenset[str] = frozenset()) -> int:
    if cell in seen:
        return 0
    n = 0
    for i in muxes[cell]["inputs"]:
        if i["driver_ref"] in CONST_REFS:
            continue
        n += _leaves(i["driver"], muxes, seen | {cell}) if i["driver"] in muxes else 1
    return n


def findings(dump: dict[str, Any], pairs: list[dict[str, Any]] | None = None, family: str | None = None) -> list[dict[str, Any]]:
    """The findings for one design. ``family`` ("7" or "us") defaults to the dump's PART line, else "7"."""
    family = family or dump.get("part", {}).get("family") or "7"
    out: list[dict[str, Any]] = []
    muxes = dump["muxes"]
    cons = _pair_constraints(pairs or [])

    def add(code: str, where: str, msg: str, blocking: bool) -> None:
        out.append({"code": code, "where": where, "message": msg, "blocking": blocking})

    for lut in dump["luts"]:
        add("CLKMUX-LUT", lut["cell"], f"{lut['ref']} output reaches {lut['clock_pins']} clock pin(s); clocks on it: "
            f"{', '.join(lut['clocks']) or 'none'}", True)

    fed = {i["driver"] for m in muxes.values() for i in m["inputs"]}        # muxes that feed another mux (inner levels)
    for name, m in muxes.items():
        # a BUFGCTRL with one input tied to a constant is a BUFGCE or BUFG preset (7 series retargets BUFGCE to BUFGCTRL with
        # I1 tied to VCC, measured in brief 208 f1): not a mux
        if len([i for i in m["inputs"] if i["driver_ref"] not in CONST_REFS]) < 2:
            continue
        outc = m["out_clocks"]
        inc = sorted({c for i in m["inputs"] for c in i["clocks"]})
        top = name not in fed
        # CLKMUX-NO-GROUPS: pairs of output clocks still timed against each other (only judged at the outermost mux,
        # where every mode meets, and only when the clock-interaction report is given)
        if top and pairs is not None and len(outc) >= 2:
            timed = sorted({f"{a} -> {b}" for (a, b), c in cons.items()
                            if a != b and a in outc and b in outc and not _grouped(c)})
            if timed:
                add("CLKMUX-NO-GROUPS", name, f"clocks {', '.join(outc)} all reach the mux output; still timed against each "
                    f"other: {'; '.join(timed[:6])}", True)
        # CLKMUX-SRC-GROUPED: the source clocks grouped while paths join a source tree and the mux fanout
        nA, nC = m["inter"].get("A", 0), m["inter"].get("C", 0)
        if top and pairs is not None and (nA or nC):
            src = [c for c in inc if c in outc]                 # source clocks that still propagate through the mux
            hit = sorted({f"{a} -> {b} ({c})" for (a, b), c in cons.items()
                          if a != b and a in src and b in src and _grouped(c)})
            if hit:
                ex = m["inter_example"].get("A") if nA else m["inter_example"].get("C")
                add("CLKMUX-SRC-GROUPED", name, f"source clocks grouped: {'; '.join(hit[:4])}; yet {nA} register pair(s) run from "
                    f"other clock trees into the mux fanout and {nC} run out of it (e.g. {ex}); the group removes them from "
                    f"timing and report_cdc", True)
        # CLKMUX-CASE: fewer clocks propagate than come in, with a select that is not constant in the netlist
        sel_pins = {p: v for p, v in m["ctl"].items() if p.startswith(("S", "CE"))}
        driven = any(v["const"] == "-" for v in sel_pins.values())
        if top and driven and len(inc) >= 2 and len([c for c in outc if c in inc]) < len(inc) and \
                not any(c not in inc for c in outc):
            add("CLKMUX-CASE", name, f"input clocks {', '.join(inc)}; only {', '.join(outc) or 'none'} reach the output", False)
        # CLKMUX-CE-SELECT
        ce_driven = any(p.startswith("CE") and v["const"] == "-" for p, v in m["ctl"].items())
        s_driven = any(p.startswith("S") and v["const"] == "-" for p, v in m["ctl"].items())
        if m["orig_ref"] in ("BUFGMUX", "BUFGMUX_1") or m["ref"] in ("BUFGMUX", "BUFGMUX_1") or (ce_driven and not s_driven):
            add("CLKMUX-CE-SELECT", name, f"{m['orig_ref'] if m['orig_ref'] != '-' else m['ref']}: the select drives the CE "
                f"pins", False)
        # CLKMUX-STOP
        from_pin = [i for i in m["inputs"] if i["driver_ref"].startswith("IBUF") or i["driver_ref"] == "PORT"]
        ign = [v for p, v in m["ctl"].items() if p.startswith("IGNORE")]
        if from_pin and not any(v["const"] == "-" for v in ign):
            add("CLKMUX-STOP", name, f"input(s) {', '.join(i['pin'] for i in from_pin)} come from a device pin; IGNORE is "
                f"tied ({', '.join(v['const'] for v in ign) or 'no IGNORE pin'})", False)
        # CLKMUX-CASCADE
        if top:
            lv, nl = _levels(name, muxes), _leaves(name, muxes)
            limit = CASCADE_LIMIT.get(family, 16)
            if lv > limit:
                add("CLKMUX-CASCADE", name, f"{lv} BUFGCTRL levels for {nl} inputs: longer than the cascade ring ({limit} on "
                    f"family {family})", True)
            elif nl <= 4 and lv > 2:
                add("CLKMUX-CASCADE", name, f"{lv} BUFGCTRL levels for {nl} inputs (a balanced tree needs 2)", False)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dump")
    ap.add_argument("--clock-interaction")
    ap.add_argument("--family", default=None, choices=sorted(CASCADE_LIMIT), help="default: the dump's PART line, else 7")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    from flow.constraint_gates import parse_clock_pairs
    dump = parse_dump(Path(a.dump).read_text(errors="replace"))
    pairs = parse_clock_pairs(Path(a.clock_interaction).read_text(errors="replace")) if a.clock_interaction else None
    fs = findings(dump, pairs, a.family)
    if a.json:
        print(json.dumps(fs, indent=1))
    else:
        for f in fs:
            print(f"{'FAIL' if f['blocking'] else 'ADVISORY'} {f['code']} {f['where']}: {f['message']}")
    return 1 if any(f["blocking"] for f in fs) else 0


if __name__ == "__main__":
    sys.exit(main())
