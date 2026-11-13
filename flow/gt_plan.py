"""Link planner (brief 56A): from a spec.yaml ``link:`` section and a board's ``gt:`` section to a GT Wizard configuration, the
reference-clock and lane constraints, the user-clock frequencies, and every reason the link cannot be built.

    python3 flow/gt_plan.py <spec.yaml> <boards/<board>/board.yaml> [--part xck26-sfvc784-2LV-c]

``spec.yaml`` ``link:`` (all keys optional except protocol, line_rate_gbps and lanes):

    link:
      protocol: raw            # raw | aurora_64b66b | aurora_8b10b | ethernet_10g   (raw: our own link layer on the Wizard)
      line_rate_gbps: 10.3125
      lanes: 1
      refclk_mhz: 156.25       # must be what the board provides (board.yaml gt.<port>.refclk.mhz)
      pll: auto                # auto | cpll | qpll0 | qpll1
      port: sfp                # which board.yaml gt: entry

The result is data only: the agent (and a person) read it, write the RTL around the Wizard and the XDC, and the GT gates
(flow/gt_gates.py) check what was built. The planner never creates IP: AMD IP Tcl is the maintainers' reviewed file
(flow/ip_tcl_allow.yaml), see docs/gt_links.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    from flow import gt_data
except ImportError:
    import gt_data

PROTOCOLS = {"raw": "gtwizard_ultrascale", "aurora_64b66b": "aurora_64b66b", "aurora_8b10b": "aurora_8b10b",
             "ethernet_10g": "xxv_ethernet"}
#: line rates the protocol itself fixes (Gb/s); None: any rate the Wizard accepts
FIXED_RATE = {"ethernet_10g": (10.3125,)}
#: what the 2026.1 Basic licence allowed in brief 56A's probe (results/56a_serdes/licences.md); updated by that file's probe
LICENCE = {"gtwizard_ultrascale": "to be measured", "aurora_64b66b": "to be measured", "aurora_8b10b": "to be measured",
           "xxv_ethernet": "to be measured"}


def link_errors(link: Any) -> list[str]:
    """Shape errors of a spec.yaml ``link:`` section (used by agent.graph.spec_schema.validate)."""
    if not isinstance(link, dict):
        return ["'link' must be a mapping"]
    errs: list[str] = []
    for k in ("protocol", "line_rate_gbps", "lanes"):
        if k not in link:
            errs.append(f"link has no {k!r}")
    p = link.get("protocol")
    if p is not None and p not in PROTOCOLS:
        errs.append(f"link.protocol must be one of {', '.join(PROTOCOLS)}, not {p!r}")
    r = link.get("line_rate_gbps")
    if r is not None and (isinstance(r, bool) or not isinstance(r, (int, float)) or not gt_data.FGTHMIN <= r <= max(gt_data.FGTHMAX.values())):
        errs.append(f"link.line_rate_gbps must be a number from {gt_data.FGTHMIN} to {max(gt_data.FGTHMAX.values())}, not {r!r}")
    n = link.get("lanes")
    if n is not None and (isinstance(n, bool) or not isinstance(n, int) or n < 1):
        errs.append(f"link.lanes must be an integer of at least 1, not {n!r}")
    f = link.get("refclk_mhz")
    if f is not None and (isinstance(f, bool) or not isinstance(f, (int, float)) or not gt_data.REFCLK_RANGE_MHZ[0] <= f <= gt_data.REFCLK_RANGE_MHZ[1]):
        errs.append(f"link.refclk_mhz must be a number from {gt_data.REFCLK_RANGE_MHZ[0]} to {gt_data.REFCLK_RANGE_MHZ[1]}, not {f!r}")
    if link.get("pll", "auto") not in ("auto", "cpll", "qpll0", "qpll1"):
        errs.append(f"link.pll must be auto, cpll, qpll0 or qpll1, not {link.get('pll')!r}")
    return errs


def _pick_pll(rate: float, grade: str, want: str) -> tuple[str | None, str]:
    order = ["QPLL0", "CPLL", "QPLL1"] if want == "auto" else [want.upper()]
    for pll in order:
        for d, (lo, hi) in sorted(gt_data.windows(pll, grade).items()):
            if lo <= rate <= hi:
                return pll, f"{pll} with output divider {d} ({lo}-{hi} Gb/s at -{grade})"
    return None, f"{rate} Gb/s is in no {', '.join(order)} divider window at -{grade}"


def plan(link: dict[str, Any], board: dict[str, Any], part: str | None = None) -> dict[str, Any]:
    part = part or board.get("part", "")
    problems = list(link_errors(link))
    out: dict[str, Any] = {"ok": False, "problems": problems, "notes": [], "wizard": {}, "xdc": "", "ip": PROTOCOLS.get(link.get("protocol"))}
    if problems:
        return out
    port = link.get("port", "sfp")
    gt = (board.get("gt") or {}).get(port)
    if not gt:
        problems.append(f"the board has no gt.{port} entry: it has no transceiver port by that name")
        return out
    grade = gt_data.speed_grade(part)
    if grade is None:
        problems.append(f"the part {part!r} has no GTH speed-grade column (DS925 table 99) in flow/gt_data.py")
        return out
    rate, lanes = float(link["line_rate_gbps"]), link["lanes"]
    if lanes > gt["lanes"]:
        problems.append(f"{lanes} lanes asked, the board's {port} port has {gt['lanes']}: multi-lane work (bonding, deskew) is simulation only here")
    fixed = FIXED_RATE.get(link["protocol"])
    if fixed and rate not in fixed:
        problems.append(f"{link['protocol']} runs at {', '.join(map(str, fixed))} Gb/s only, not {rate}")
    ref = gt["refclk"]
    if link.get("refclk_mhz") not in (None, ref["mhz"]):
        problems.append(f"the board's reference clock is {ref['mhz']} MHz ({ref['status']}), not {link['refclk_mhz']} MHz")
    pll, why = _pick_pll(rate, grade, link.get("pll", "auto"))
    if pll is None:
        problems.append(why)
    int_w = 32
    ext_w = 64 if rate >= 6.0 else 32
    f2 = rate * 1000.0 / ext_w
    lim = gt_data.usrclk2_max(int_w, ext_w, grade)
    if lim is not None and f2 > lim:
        problems.append(f"user clock {f2:.3f} MHz exceeds the {lim} MHz limit for widths {int_w}/{ext_w} at -{grade}")
    out["user_clock_mhz"] = round(f2, 3)
    out["pll"] = why
    if link["protocol"] == "raw":
        out["wizard"] = {"CHANNEL_ENABLE": gt["channel"], "TX_MASTER_CHANNEL": gt["channel"], "RX_MASTER_CHANNEL": gt["channel"],
                         "TX_LINE_RATE": rate, "RX_LINE_RATE": rate, "TX_REFCLK_FREQUENCY": ref["mhz"], "RX_REFCLK_FREQUENCY": ref["mhz"],
                         "TX_PLL_TYPE": pll, "RX_PLL_TYPE": pll, "TX_DATA_ENCODING": "RAW", "RX_DATA_DECODING": "RAW",
                         "TX_USER_DATA_WIDTH": ext_w, "TX_INT_DATA_WIDTH": int_w, "RX_USER_DATA_WIDTH": ext_w, "RX_INT_DATA_WIDTH": int_w,
                         "TX_REFCLK_SOURCE": ref["source"], "RX_REFCLK_SOURCE": ref["source"],
                         "LOCATE_TX_USER_CLOCKING": "CORE", "LOCATE_RX_USER_CLOCKING": "CORE"}
        out["notes"].append("a 64-bit internal width is refused by the Wizard for this set-up; use a 32-bit internal width (brief 56A)")
    else:
        out["notes"].append(f"{link['protocol']}: use the AMD {PROTOCOLS[link['protocol']]} IP; its own GT subcore carries the line rate and reference clock")
    st = LICENCE.get(out["ip"], "unknown")
    out["licence_2026_1_basic"] = st
    xdc = [f"set_property PACKAGE_PIN {ref['p']} [get_ports <refclk_p>]", f"set_property PACKAGE_PIN {ref['n']} [get_ports <refclk_n>]",
           f"create_clock -name <refclk> -period {1000.0 / ref['mhz']:.3f} [get_ports <refclk_p>]"]
    for k in ("rx", "tx"):
        xdc += [f"set_property PACKAGE_PIN {gt[k]['p']} [get_ports <{k}_p>]", f"set_property PACKAGE_PIN {gt[k]['n']} [get_ports <{k}_n>]"]
    out["xdc"] = "\n".join(xdc)
    out["ok"] = not problems
    out["notes"].append("reference frequency and source are unconfirmed against the carrier schematic" if "unconfirmed" in ref["status"] else "")
    out["notes"] = [n for n in out["notes"] if n]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec", type=Path)
    ap.add_argument("board", type=Path)
    ap.add_argument("--part")
    a = ap.parse_args(argv)
    spec = yaml.safe_load(a.spec.read_text()) or {}
    if "link" not in spec:
        print("no link: section in the spec")
        return 1
    r = plan(spec["link"], yaml.safe_load(a.board.read_text()), a.part)
    print(json.dumps(r, indent=2))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
