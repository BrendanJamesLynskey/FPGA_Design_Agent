"""GT gates (brief 56A): checks on a design that uses the AMD UltraScale FPGAs Transceivers Wizard (gtwizard_ultrascale).

    python3 flow/gt_gates.py <build dir> [--json out.json]

Each gate is a pure function of three inputs the flow already has: the Wizard's configuration (the generated ``.xci`` in
``<build>/ip/<name>/``), the design's XDC and RTL (the file list in ``<build>/prepare.json``), and the synthesis reports. The
data they are checked against is flow/gt_data.py (DS925 v1.30 tables 99 and 104, UG576, Vivado 2026.1 pin and site queries).
flow/gates.py calls :func:`evaluate` after synthesis and adds the gates below to the ``post_synth`` stage; a build with no Wizard
gets no GT gates, and a part or speed grade with no data gets a stated ``not applicable`` finding, never a pass.

  post_synth_gt_refclk_pin_quad   the reference-clock port sits on the MGTREFCLK pins of the channel's quad, at the Wizard's frequency
  post_synth_gt_lane_pins         every GT pin assigned in the XDC belongs to an enabled channel, and each enabled channel has its four pins
  post_synth_gt_rate_in_window    the line rate lies in a PLL/divider window of the part's speed grade (DS925 table 99)
  post_synth_gt_user_clock_limit  the user clocks (line rate / width) are within the speed grade's maximum (DS925 table 104)
  post_synth_gt_reset_sequence    the RTL drives the Wizard's reset-all input from logic (not a constant) and uses both done outputs
  post_synth_gt_user_clocks_timed the synthesised design carries timed clocks at the user-clock frequencies (the Wizard's constraints applied)
  post_synth_gt_drc_clean         no report_drc or report_methodology row mentions a transceiver at Warning or above
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from flow import gt_data
except ImportError:          # run as a script: flow/ is on sys.path, not the repo
    import gt_data

ROOT = Path(__file__).resolve().parents[1]
GATES = ("post_synth_gt_refclk_pin_quad", "post_synth_gt_lane_pins", "post_synth_gt_rate_in_window",
         "post_synth_gt_user_clock_limit", "post_synth_gt_reset_sequence", "post_synth_gt_user_clocks_timed",
         "post_synth_gt_drc_clean")
_PARAM = re.compile(r'"([A-Z][A-Z0-9_]*)":\s*\[\s*\{\s*"value":\s*"([^"]*)"')


def find_wizard(build: Path) -> Path | None:
    """The generated .xci of a gtwizard_ultrascale core under <build>/ip, or None."""
    for x in sorted((build / "ip").glob("*/*.xci")) if (build / "ip").is_dir() else []:
        if "gtwizard_ultrascale" in x.read_text(errors="replace")[:20000]:
            return x
    return None


def read_cfg(xci_text: str) -> dict[str, str]:
    """User-visible parameters of the core (name without the C_ prefix, first occurrence wins)."""
    cfg: dict[str, str] = {}
    for k, v in _PARAM.findall(xci_text):
        if not k.startswith("C_") and k not in cfg:
            cfg[k] = v
    return cfg


def xdc_facts(xdc_text: str) -> tuple[dict[str, str], dict[str, float]]:
    """({port: package pin}, {port: clock period ns}) from XDC text (set_property PACKAGE_PIN / -dict, create_clock on a port)."""
    pins: dict[str, str] = {}
    clocks: dict[str, float] = {}
    for line in xdc_text.splitlines():
        line = line.split("#")[0]
        m = re.search(r"PACKAGE_PIN\s+(\w+)", line)
        p = re.search(r"get_ports\s+\{?\s*([^\]\}\s]+)", line)
        if m and p and line.lstrip().startswith("set_property"):
            pins[p.group(1)] = m.group(1)
        c = re.search(r"create_clock\b.*-period\s+([\d.]+).*get_ports\s+\{?\s*([^\]\}\s]+)", line)
        if c:
            clocks[c.group(2)] = float(c.group(1))
    return pins, clocks


def _num(cfg: dict[str, str], key: str) -> float | None:
    try:
        return float(cfg[key])
    except (KeyError, ValueError):
        return None


def check_rate(cfg: dict[str, str], grade: str | None) -> dict[str, Any]:
    if grade is None:
        return {"ok": None, "why": "not applicable: the part's speed grade has no GTH column in DS925 table 99"}
    bad: list[str] = []
    for d, rate_k, pll_k in (("TX", "TX_LINE_RATE", "TX_PLL_TYPE"), ("RX", "RX_LINE_RATE", "RX_PLL_TYPE")):
        rate, pll = _num(cfg, rate_k), cfg.get(pll_k, "")
        if rate is None or pll not in ("CPLL", "QPLL0", "QPLL1"):
            bad.append(f"{d}: line rate or PLL type unreadable ({rate_k}={cfg.get(rate_k)!r}, {pll_k}={pll!r})")
            continue
        if not gt_data.FGTHMIN <= rate <= gt_data.FGTHMAX[grade]:
            bad.append(f"{d}: {rate} Gb/s is outside {gt_data.FGTHMIN}-{gt_data.FGTHMAX[grade]} Gb/s (grade -{grade})")
            continue
        wins = gt_data.windows(pll, grade)
        if not any(lo <= rate <= hi for lo, hi in wins.values()):
            bad.append(f"{d}: {rate} Gb/s is in no {pll} divider window at grade -{grade}: "
                       + ", ".join(f"D={k}: {lo}-{hi}" for k, (lo, hi) in sorted(wins.items())))
    return {"ok": not bad, "why": "; ".join(bad)}


def check_user_clocks(cfg: dict[str, str], grade: str | None) -> dict[str, Any]:
    if grade is None:
        return {"ok": None, "why": "not applicable: no speed-grade column", "expect_mhz": []}
    bad: list[str] = []
    expect: list[float] = []
    for d in ("TX", "RX"):
        rate = _num(cfg, f"{d}_LINE_RATE")
        iw, ew = _num(cfg, f"{d}_INT_DATA_WIDTH"), _num(cfg, f"{d}_USER_DATA_WIDTH")
        if rate is None or iw is None or ew is None:
            bad.append(f"{d}: rate or widths unreadable")
            continue
        iw, ew = int(iw), int(ew)
        f2, f1 = rate * 1000.0 / ew, rate * 1000.0 / iw
        expect.append(round(f2, 3))
        m2, m1 = gt_data.usrclk2_max(iw, ew, grade), gt_data.usrclk_max(iw, grade)
        if m2 is None or m1 is None:
            bad.append(f"{d}: width pair {iw}/{ew} is not in DS925 table 104")
            continue
        if f2 > m2:
            bad.append(f"{d}: user clock 2 {f2:.3f} MHz exceeds {m2} MHz for widths {iw}/{ew} at grade -{grade}")
        if f1 > m1:
            bad.append(f"{d}: user clock {f1:.3f} MHz exceeds {m1} MHz for internal width {iw} at grade -{grade}")
    return {"ok": not bad, "why": "; ".join(bad), "expect_mhz": expect}


def check_refclk_and_lanes(cfg: dict[str, str], part_data: dict | None, pins: dict[str, str], clocks: dict[str, float]) -> dict[str, Any]:
    """The two pin gates. Returns {'refclk': {ok, why}, 'lanes': {ok, why}}."""
    na = {"ok": None, "why": "not applicable: no pin table for this part (flow/gt_parts)"}
    if part_data is None:
        return {"refclk": na, "lanes": na}
    table = part_data["pins"]
    chans = [c for c in cfg.get("CHANNEL_ENABLE", "").split() if re.fullmatch(r"X\d+Y\d+", c)]
    sites = {f"GTHE4_CHANNEL_{c}" for c in chans}
    # lanes
    bad: list[str] = []
    mgt = {port: pin for port, pin in pins.items() if pin in table and re.match(r"MGTH[RT]X[PN]\d", table[pin]["func"])}
    for port, pin in sorted(mgt.items()):
        if table[pin]["site"] not in sites:
            bad.append(f"{port} on {pin} ({table[pin]['func']}) is site {table[pin]['site']}, not an enabled channel {sorted(chans)}")
    have = {pin for pin in mgt.values()}
    for c in chans:
        want = {p for p, v in table.items() if v["site"] == f"GTHE4_CHANNEL_{c}" and re.match(r"MGTH[RT]X[PN]\d", v["func"])}
        if want - have:
            bad.append(f"channel {c}: pins not assigned in the XDC: {sorted(want - have)}")
    lanes = {"ok": not bad and bool(chans), "why": "; ".join(bad) or ("" if chans else "CHANNEL_ENABLE unreadable")}
    # refclk
    src = cfg.get("TX_REFCLK_SOURCE", "")
    m = re.fullmatch(r"(X\d+Y\d+)\s+clk([01])", src.strip())
    if not m:
        return {"refclk": {"ok": None, "why": f"not applicable: reference source {src!r} is not a local MGTREFCLK0/1"}, "lanes": lanes}
    quad, n = gt_data.quad_of_channel(m.group(1)), m.group(2)
    want = {p: v for p, v in table.items() if v["site"] == quad and re.match(rf"MGTREFCLK{n}[PN]_", v["func"])}
    pp = [p for p, v in want.items() if v["func"].startswith(f"MGTREFCLK{n}P")]
    pn = [p for p, v in want.items() if v["func"].startswith(f"MGTREFCLK{n}N")]
    ports = [port for port, pin in pins.items() if pin in pp]
    ref = _num(cfg, "TX_REFCLK_FREQUENCY")
    msgs: list[str] = []
    if not ports:
        msgs.append(f"no port is assigned to MGTREFCLK{n}P of {quad} (pin {pp})")
    if not any(pins.get(p) in pn for p in pins):
        msgs.append(f"the MGTREFCLK{n}N pin {pn} of {quad} is not assigned")
    for port in ports:
        per = clocks.get(port)
        if per is None:
            msgs.append(f"no create_clock on {port}")
        elif ref and abs(per - 1000.0 / ref) > 0.002:
            msgs.append(f"create_clock period {per} ns on {port} is not the Wizard's {ref} MHz ({1000.0 / ref:.3f} ns)")
    lo, hi = gt_data.REFCLK_RANGE_MHZ
    if ref is not None and not lo <= ref <= hi:
        msgs.append(f"reference {ref} MHz is outside {lo}-{hi} MHz")
    return {"refclk": {"ok": not msgs, "why": "; ".join(msgs)}, "lanes": lanes}


def check_reset_sequence(rtl_text: str, module: str) -> dict[str, Any]:
    """The RTL instantiates the core, drives gtwiz_reset_all_in from an expression that is not a constant, and connects both done outputs."""
    m = re.search(rf"\b{re.escape(module)}\s+(?:#\([^;]*?\)\s*)?\w+\s*\((.*?)\)\s*;", rtl_text, re.S)
    if not m:
        return {"ok": False, "why": f"no instance of {module} in the RTL"}
    body = m.group(1)

    def conn(port: str) -> str | None:
        c = re.search(rf"\.{port}\s*\(((?:[^()]|\([^()]*\))*)\)", body)
        return c.group(1).strip() if c else None

    ra = conn("gtwiz_reset_all_in")
    if ra is None or re.fullmatch(r"\d*'?[bdh]?[01]|'[01]", ra.replace(" ", "")) or not ra:
        return {"ok": False, "why": f"gtwiz_reset_all_in is {'unconnected' if ra is None else 'a constant'} ({ra!r}): the link is never reset after power-up"}
    miss = [p for p in ("gtwiz_reset_tx_done_out", "gtwiz_reset_rx_done_out") if not (conn(p) or "").strip()]
    if miss:
        return {"ok": False, "why": f"done outputs not used: {miss}: the datapath is not held until reset is done"}
    return {"ok": True, "why": ""}


def _clock_rows(timing_text: str) -> list[tuple[str, float]]:
    """(clock name, MHz) rows of the Clock Summary table of report_timing_summary."""
    rows: list[tuple[str, float]] = []
    on = False
    for line in timing_text.splitlines():
        if line.startswith("| Clock Summary"):
            on = True
            continue
        if not on:
            continue
        m = re.match(r"\s*(\S+)\s+\{[^}]*\}\s+([\d.]+)\s+([\d.]+)\s*$", line)
        if m:
            rows.append((m.group(1), float(m.group(3))))
        elif rows and line.startswith("| "):
            break
    return rows


def check_clocks_timed(timing_text: str, expect_mhz: list[float]) -> dict[str, Any]:
    rows = _clock_rows(timing_text)
    miss = [f"{f} MHz" for f in expect_mhz if not any(abs(mhz - f) <= 0.01 * f for _, mhz in rows)]
    return {"ok": not miss and bool(expect_mhz), "why": ("no timed clock at " + ", ".join(miss)) if miss else ("" if expect_mhz else "no expected user clock"),
            "clocks": [{"name": n, "mhz": f} for n, f in rows]}


def check_drc_rows(drc_text: str, meth_text: str) -> dict[str, Any]:
    """Rows of report_drc / report_methodology naming a transceiver at Warning or above. The summary table rows look like
    ``| REQP-1839 | Warning | description | 1 |``; the detail blocks like ``REQP-1839#1 Warning`` with the description on the next line."""
    hits: list[str] = []
    gt = re.compile(r"transceiver|\bGT[HYXPE]?\d?\b|MGT|GTHE4", re.I)
    for src, text in (("report_drc", drc_text), ("report_methodology", meth_text)):
        lines = text.splitlines()
        for i, line in enumerate(lines):
            m = re.match(r"\s*\|?\s*([A-Z][A-Z0-9]+-\d+)\s*(?:\||#\d+)?\s*\|?\s*(Warning|Critical Warning|Error|Advisory)\b(.*)$", line)
            if not m:
                continue
            body = m.group(3) + " " + (lines[i + 1] if i + 1 < len(lines) and not line.lstrip().startswith("|") else "")
            if gt.search(body):
                hits.append(f"{src}: {' '.join(line.split())}")
    return {"ok": not hits, "why": "; ".join(hits[:5])}


def evaluate(build: Path) -> dict[str, Any] | None:
    """The GT gates of one build directory, or None when the design has no GT Wizard core."""
    build = Path(build)
    xci = find_wizard(build)
    if xci is None:
        return None
    cfg = read_cfg(xci.read_text(errors="replace"))
    prep = json.loads((build / "prepare.json").read_text()) if (build / "prepare.json").exists() else {}
    part = prep.get("part", "")
    files = [ROOT / f for f in prep.get("files") or []]
    xdc_text = "\n".join(f.read_text(errors="replace") for f in files if f.suffix == ".xdc" and f.exists())
    rtl_text = "\n".join(f.read_text(errors="replace") for f in files if f.suffix in (".sv", ".v", ".vhd") and f.exists())
    pins, clocks = xdc_facts(xdc_text)
    grade = gt_data.speed_grade(part)
    pd = gt_data.load_part(part)
    r = {"wizard": xci.name, "part": part, "speed_grade": grade, "config": {k: cfg.get(k) for k in (
        "CHANNEL_ENABLE", "TX_LINE_RATE", "RX_LINE_RATE", "TX_PLL_TYPE", "RX_PLL_TYPE", "TX_REFCLK_FREQUENCY", "TX_REFCLK_SOURCE",
        "TX_INT_DATA_WIDTH", "TX_USER_DATA_WIDTH", "RX_INT_DATA_WIDTH", "RX_USER_DATA_WIDTH", "TX_DATA_ENCODING", "RX_DATA_DECODING")}}
    pin_r = check_refclk_and_lanes(cfg, pd, pins, clocks)
    uc = check_user_clocks(cfg, grade)
    ts = build / "timing_summary_synth.rpt"
    res = {
        "post_synth_gt_refclk_pin_quad": pin_r["refclk"],
        "post_synth_gt_lane_pins": pin_r["lanes"],
        "post_synth_gt_rate_in_window": check_rate(cfg, grade),
        "post_synth_gt_user_clock_limit": uc,
        "post_synth_gt_reset_sequence": check_reset_sequence(rtl_text, xci.stem),
        "post_synth_gt_user_clocks_timed": check_clocks_timed(ts.read_text(errors="replace"), uc["expect_mhz"]) if ts.exists()
        else {"ok": False, "why": "timing_summary_synth.rpt missing"},
        "post_synth_gt_drc_clean": check_drc_rows((build / "drc_synth.rpt").read_text(errors="replace") if (build / "drc_synth.rpt").exists() else "",
                                                  (build / "methodology_synth.rpt").read_text(errors="replace") if (build / "methodology_synth.rpt").exists() else ""),
    }
    r["checks"] = res
    # a gate with ok None (not applicable) is reported, not counted as a pass or a fail
    r["gates"] = {k: v["ok"] for k, v in res.items() if v["ok"] is not None}
    r["not_applicable"] = {k: v["why"] for k, v in res.items() if v["ok"] is None}
    r["pass"] = all(r["gates"].values())
    return r


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("build_dir", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    r = evaluate(a.build_dir)
    if r is None:
        print("gt gates: no gtwizard_ultrascale core in this build")
        return 0
    for k, v in r["checks"].items():
        print(f"  {'ok  ' if v['ok'] else ('n/a ' if v['ok'] is None else 'FAIL')} {k}" + (f": {v['why']}" if v["why"] else ""))
    if a.json:
        a.json.write_text(json.dumps(r, indent=2) + "\n")
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
