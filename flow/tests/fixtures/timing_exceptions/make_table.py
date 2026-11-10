#!/usr/bin/env python3
"""The step-1 table of brief 20: what Vivado 2025.2 reports for each timing-exception fixture, and what the flow's
checks make of it.

    python3 flow/tests/fixtures/timing_exceptions/make_table.py [--collect <run_all.sh out dir>] [--out results/20_timing_exceptions]

--collect copies the reports the checks read from a run_all.sh output into golden/<fixture>/ (host paths, dates and
command lines removed), so CI evaluates the fixtures without Vivado. The table then reads golden/ only:

    vivado flags  Vivado itself says something about the exception: one of the gate's methodology rules, an ignored
                  exception, zero coverage, or a constraint message in the log (slack aside)
    vivado        methodology rules raised (synthesis, and placement where followup.tcl ran), report_exceptions -ignored
                  statuses, coverage endpoints, WNS/WHS with the exception and with it removed (reset_timing + clocks)
    exceptions    flow/exceptions_check.py (the new gate post_synth_exceptions_clean)
    cdc_structure flow/cdc_structure.py (brief 16's gate)
    xdc_rules     agent/core/constraints.py FDA-CON-5 / FDA-CON-10 (before Vivado)
    timing        setup and hold slack after synthesis (and after routing where it ran) non-negative
    flow flags    any of the above fails
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
from agent.core import constraints as con  # noqa: E402
from flow import cdc_structure, exceptions_check, gates  # noqa: E402

DESCR = {
    "tex_e1": "2-cycle enable multiply, -setup 2 and -hold 1",
    "tex_e2": "same, -setup 2 with no -hold",
    "tex_e3": "multicycle on registers with CE tied high",
    "tex_e4": "false path between two MMCM outputs (synchronous)",
    "tex_e5": "false path over an 8-bit binary bus crossing",
    "tex_e6": "multicycle whose -to has a typo (matches nothing)",
    "tex_e6b": "multicycle between registers with no path",
    "tex_e7": "datapath-only max delay overridden by a clock group",
    "tex_e8": "100 -> 200 MHz multicycle, -setup 2 -end / -hold 1 -end",
    "tex_e8b": "same crossing written with -start",
    "tex_e9": "quasi-static bit, 2-flop sync, commented false path",
    "tex_e10": "slow FSM on 125 MHz, 1-in-8 enable, multicycle 8/7 on tagged registers",
    "tex_e10b": "E10 with the consumer copying every clock (not qualified)",
    "tex_e10c": "E10 with the multicycle on all_registers",
    "tex_e10d": "E10 alternative: FSM on a fabric-divided clock (BUFG), no exception",
}
# what the brief says the right handling is: True = the flow should flag it
EXPECT = {"tex_e1": False, "tex_e2": True, "tex_e3": True, "tex_e4": True, "tex_e5": True, "tex_e6": True, "tex_e6b": True,
          "tex_e7": True, "tex_e8": False, "tex_e8b": True, "tex_e9": False, "tex_e10": False, "tex_e10b": True,
          "tex_e10c": True, "tex_e10d": None}
KEEP = ("timing_summary_synth.rpt", "timing_summary_noexc.rpt", "timing_summary_route.rpt", "methodology_synth.rpt",
        "methodology_route.rpt", "methodology_place.rpt", "exceptions_synth.rpt", "exceptions_ignored_synth.rpt",
        "exceptions_coverage_synth.rpt", "cdc_synth.rpt", "cdc_paths_synth.rpt", "crossing_setup.rpt", "crossing_hold.rpt",
        "utilization_route.rpt", "timing_setup_route.rpt", "mcp_paths_synth.txt", "vivado.log")


def scrub(text: str) -> str:
    text = re.sub(r"^\| (Date|Host|Command)\s*:.*$", r"| \1 : (removed)", text, flags=re.M)
    text = re.sub(r"/\S*?/flow/tests/fixtures/timing_exceptions/", "flow/tests/fixtures/timing_exceptions/", text)
    text = re.sub(r"/tmp/\S+?/(tex_e\w+)/", r"\1/", text)
    return text


def collect(src: Path) -> None:
    for d in sorted(p for p in src.iterdir() if p.is_dir() and p.name.startswith("tex_")):
        dst = HERE / "golden" / d.name
        shutil.rmtree(dst, ignore_errors=True)
        dst.mkdir(parents=True)
        for name in KEEP:
            f = src / f"{d.name}.log" if name == "vivado.log" else d / name
            if f.exists():
                text = f.read_text(errors="replace")
                if name == "vivado.log":        # keep only the constraint messages the gate reads
                    text = "\n".join(l for l in text.splitlines() if re.match(r"(CRITICAL WARNING|ERROR): ", l)) + "\n"
                if name.startswith("timing_summary"):   # the summary tables only; the per-path details are not read
                    text = text.split("\n| Timing Details", 1)[0]
                (dst / name).write_text(scrub(text))


def summary(path: Path) -> dict | None:
    return gates.parse_timing_summary(path.read_text()) if path.exists() else None


def rules(path: Path) -> list[dict]:
    return gates.parse_rule_table(path.read_text()) if path.exists() else []


def fixture(name: str) -> dict:
    g = HERE / "golden" / name
    xdcs = [HERE / "xdc" / f"{name}.clocks.xdc", HERE / "xdc" / f"{name}.xdc"]
    exc = exceptions_check.evaluate(g, "synth", xdcs)
    place = rules(g / "methodology_place.rpt")
    if place:          # followup.tcl: report_methodology after placement, the same rule set
        extra = [r for r in place if r["rule"] in exceptions_check.METHODOLOGY_RULES]
        if extra:
            exc["failures"] += [{"rule": r["rule"], "stage": "place", "count": r["count"]} for r in extra]
            exc["pass"] = False
    cdc = cdc_structure.evaluate(g / "cdc_paths_synth.rpt", g / "cdc_synth.rpt", [])
    xdc_find = [x["rule"] for x in con.check_xdc((HERE / "xdc" / f"{name}.xdc").read_text(), ROOT / "boards" / "nexys_a7_100t")
                if x["rule"] in ("FDA-CON-5", "FDA-CON-10")]
    t_s, t_n, t_r = summary(g / "timing_summary_synth.rpt"), summary(g / "timing_summary_noexc.rpt"), summary(g / "timing_summary_route.rpt")
    t = t_r or t_s
    timing_ok = t is not None and (t["wns_ns"] is None or t["wns_ns"] >= 0) and (t["whs_ns"] is None or t["whs_ns"] >= 0)
    ign = exceptions_check.parse_exceptions((g / "exceptions_ignored_synth.rpt").read_text())
    cov = exceptions_check.parse_coverage((g / "exceptions_coverage_synth.rpt").read_text())
    flags = (not exc["pass"]) or (not cdc["pass"]) or bool(xdc_find) or not timing_ok
    meth = sorted({r["rule"] for r in rules(g / "methodology_synth.rpt")} | {r["rule"] for r in rules(g / "methodology_route.rpt")}
                  | {r["rule"] for r in place})
    return {
        "fixture": name, "what": DESCR.get(name, ""), "expect_flag": EXPECT.get(name),
        "methodology_rules": [m for m in meth if m != "TIMING-18"],
        "methodology_detail": [r for r in rules(g / "methodology_synth.rpt") + place if r["rule"] != "TIMING-18"],
        "ignored": [r.get("Status") for r in ign], "coverage_endpoints": [r["endpoints"] for r in cov],
        "xdc_messages": [f["vivado"]["id"] for f in exc["failures"] if f["rule"] == "EXC-XDC-MSG"],
        "synth": {k: (t_s or {}).get(k) for k in ("wns_ns", "whs_ns", "tns_failing_endpoints", "ths_failing_endpoints")},
        "synth_no_exception": {k: (t_n or {}).get(k) for k in ("wns_ns", "whs_ns", "tns_failing_endpoints", "ths_failing_endpoints")},
        "route": {k: t_r.get(k) for k in ("wns_ns", "whs_ns")} if t_r else None,
        "exceptions_gate": {"pass": exc["pass"], "rules": sorted({f["rule"] for f in exc["failures"]})},
        "cdc_structure": {"pass": cdc["pass"], "summary": cdc["summary"]},
        "vivado_flags": bool(set(meth) & set(exceptions_check.METHODOLOGY_RULES)) or any(ign) or 0 in [r["endpoints"] for r in cov]
                        or any(f["rule"] == "EXC-XDC-MSG" for f in exc["failures"]),
        "xdc_rules": xdc_find, "timing_ok": timing_ok, "flow_flags": flags,
        "as_expected": None if EXPECT.get(name) is None else flags == EXPECT[name],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--collect", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "20_timing_exceptions")
    a = ap.parse_args(argv)
    if a.collect:
        collect(a.collect)
    rows = [fixture(n) for n in DESCR if (HERE / "golden" / n).is_dir()]
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "exceptions_table.json").write_text(json.dumps({"vivado": "2025.2", "part": "xc7a100tcsg324-1",
                                                             "mode": "out_of_context", "rows": rows}, indent=2) + "\n")
    f = lambda v: "-" if v is None else f"{v:+.3f}"
    md = ["| id | what | Vivado rules | ignored / coverage | WNS / WHS after synthesis | without the exception (re-timed after routing where routed) | after routing | flow flags (why) | expected |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        why = r["exceptions_gate"]["rules"] + (["CDC " + ",".join(sorted(r["cdc_structure"]["summary"]))] if not r["cdc_structure"]["pass"] else []) \
            + r["xdc_rules"] + ([] if r["timing_ok"] else ["slack"])
        rt = f"{f(r['route']['wns_ns'])} / {f(r['route']['whs_ns'])}" if r["route"] else "-"
        md.append(f"| {r['fixture'][4:].upper()} | {r['what']} | {', '.join(r['methodology_rules']) or 'none'} | "
                  f"{'; '.join(x for x in r['ignored'] if x) or 'none'} / {r['coverage_endpoints']} | "
                  f"{f(r['synth']['wns_ns'])} / {f(r['synth']['whs_ns'])} | "
                  f"{f(r['synth_no_exception']['wns_ns'])} / {f(r['synth_no_exception']['whs_ns'])} | {rt} | "
                  f"{'**yes**' if r['flow_flags'] else 'no'} ({', '.join(why) or '-'}) | "
                  f"{'-' if r['expect_flag'] is None else ('flag' if r['expect_flag'] else 'clean')} |")
    (a.out / "exceptions_table.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
