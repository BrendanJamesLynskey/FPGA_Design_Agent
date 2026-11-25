#!/usr/bin/env python3
"""Clock-crossing margin checks (brief 207): is each crossing's timing intent constrained, and is it met?

    python3 flow/cdc_margin.py <build dir> [--json out.json]

The method is in docs/cdc_margin_method.md: each asynchronous crossing has a latency bound, a skew bound (multi-bit) and an
MTBF target, expressed as `set_max_delay -datapath_only` and `set_bus_skew` in Vivado (`set_data_delay` / `set_max_delay`,
`set_net_delay` and `set_max_skew` in Quartus). Margin is never a user clock uncertainty (measured: results/207_cdc_margin).

Reads, from a build directory written by flow/build.tcl:

    bus_skew_route.rpt     report_bus_skew after routing               (brief 207 adds it to build.tcl)
    exceptions_route.rpt   report_exceptions after routing              (Setup column: max_dpo=<ns>)
    mtbf_route.rpt         report_synchronizer_mtbf (UltraScale+ only)  (brief 207 adds it to build.tcl)
    methodology.rpt        report_methodology after routing             (TIMING-44/45 user uncertainty)
    cdc_paths_synth.rpt, cdc_synth.rpt   flow/cdc_structure.py's inputs (which crossings exist, their clocks and width)

Findings (``level`` gate = fails the gate ``post_route_bus_skew_met``; advisory = a warning, never blocks):

    CDCM-SKEW-VIOL     gate      a set_bus_skew constraint has negative slack after routing (UG906 v2025.2 p. 162: no bus-skew
                                 violation may remain)
    CDCM-SKEW-MISSING  advisory  a hand-built multi-bit crossing (cdc_structure class gray / handshake, not an XPM macro; a FIFO memory read
                                 needs only its latency bound) whose
                                 capture registers no set_bus_skew constraint names (survey rank 1; UG903 v2025.2 p. 142-144)
    CDCM-DPO-LOOSE     advisory  a max_dpo value above the crossing's latency bound (survey rank 2; AMD's XPM templates, Vivado
                                 2026.1): a declared crossing's own bound (bounds()); otherwise by structural class: Gray bus and FIFO
                                 the source period, handshake data path 4 x the destination period, single-bit synchroniser the larger
                                 period
    CDCM-MTBF-MISSING  advisory  UltraScale+: no MTBF report, or fewer chains in it than the netlist's synchroniser chain endpoints
                                 (cdc_structure classes synchroniser and gray)
    CDCM-MTBF-LOW      advisory  UltraScale+: a chain or the overall MTBF below the target (default 1e9 years; architecture
                                 ``mtbf_target_years``) or UNDEFINED (UG835 v2025.2 p. 1529)
    CDCM-UNC-HIGH      advisory  TIMING-44/45: a user clock uncertainty that Vivado calls unreasonable (UG949 p. 283: never beyond
                                 0.5 ns); on a crossing it adds no margin to a datapath-only bound or a bus skew (207 E1, E2)

Absent reports mean "not evaluated" (an older build): the check then reports ``evaluated: false`` and passes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MTBF_TARGET_YEARS = 1e9

# ---------------------------------------------------------------- the method: bounds from a crossing record

#: crossing type -> (latency kind, skew kind); kinds: src = source period, dst = destination period, min = the smaller,
#: dstN = sync_stages x destination period, None = no bound of that kind
BOUNDS = {"level": ("dst", None), "pulse": ("dst", None), "gray": ("src", "min"), "handshake": ("dstN", "dstN"),
          "ce": ("dstN", "dstN"), "fifo": ("src", None), "reset": (None, None), "static": (None, None)}


def bounds(cr: dict[str, Any], src_period: float, dst_period: float, u_pair: float = 0.0, vendor: str = "amd") -> dict[str, Any]:
    """The latency bound L and skew bound S (ns) for one crossing record (docs/cdc_margin_method.md 3.1, 3.3). ``u_pair`` is the
    tool's computed clock uncertainty for the pair: taken off both bounds for Vivado (its bus skew excludes uncertainty), never
    for Quartus (its max skew includes it)."""
    t = cr.get("type")
    if t not in BOUNDS:
        raise ValueError(f"crossing type {t!r} is not one of {sorted(BOUNDS)}")
    n = int(cr.get("sync_stages", 2))
    m = u_pair if vendor == "amd" else 0.0

    def val(kind: str | None) -> float | None:
        if kind is None:
            return None
        v = {"src": src_period, "dst": dst_period, "min": min(src_period, dst_period), "dstN": n * dst_period}[kind]
        return round(v - m, 3)
    lk, sk = BOUNDS[t]
    return {"L": val(lk), "S": val(sk), "margin": m}


def constraint_lines(cr: dict[str, Any], src_period: float, dst_period: float, u_pair: float = 0.0, vendor: str = "amd") -> list[str]:
    """XDC (vendor "amd") or SDC (vendor "altera", Quartus Prime Standard) lines for one crossing record with ``from`` and ``to``
    object expressions (``[get_cells ...]`` / ``[get_keepers ...]``). Never a clock group, a false path over the pair or a clock
    uncertainty."""
    b = bounds(cr, src_period, dst_period, u_pair, vendor)
    f, t = cr["from"], cr["to_obj"] if "to_obj" in cr else cr["to"]
    out: list[str] = []
    if cr.get("type") == "static":
        return [f"# {cr.get('name', t)}: quasi-static, waived ({cr.get('reason', 'reason required')})"]
    if cr.get("type") == "reset":
        return [f"# {cr.get('name', t)}: reset release: assertion is asynchronous; the release is timed by recovery/removal"]
    if b["L"] is not None:
        if vendor == "amd":
            out.append(f"set_max_delay -datapath_only -from {f} -to {t} {b['L']:.3f}")
        else:
            out += [f"set_max_delay -from {f} -to {t} {b['L']:.3f}", f"set_min_delay -from {f} -to {t} {-b['L']:.3f}",
                    f"set_net_delay -max -from {f} -to {t} {b['L']:.3f}"]
    if b["S"] is not None:
        out.append(f"{'set_bus_skew' if vendor == 'amd' else 'set_max_skew'} -from {f} -to {t} {b['S']:.3f}")
    return out


# ---------------------------------------------------------------- Vivado parsers


def parse_bus_skew(text: str) -> list[dict[str, Any]]:
    """report_bus_skew: one dict per constraint (summary row + the endpoint names of its per-constraint section).
    "No bus skew constraints" or an empty summary gives []."""
    out: list[dict[str, Any]] = []
    if "Bus Skew Report Summary" not in text:
        return out
    # the section titles also appear in the table of contents: take the text after the LAST occurrence
    summ = text.rsplit("Bus Skew Report Summary", 1)[1].split("Bus Skew Report Per Constraint", 1)[0]
    # a row may wrap: long -from/-to object lists put the corner and numbers on a later line
    start = re.compile(r"^(\d+)\s+(\d+)\s+(.*)$")
    tail = re.compile(r"(?:^|\s)(Slow|Fast)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*$")
    cur: dict[str, Any] | None = None
    for line in summ.splitlines():
        t = line.strip()
        m = start.match(t)
        if m and cur is None:
            cur = {"id": int(m.group(1)), "position": int(m.group(2)), "from_to": m.group(3), "endpoints": [], "uncertainty": None,
                   "command": ""}
            rest = m.group(3)
        elif cur is not None:
            cur["from_to"] += " " + t
            rest = t
        else:
            continue
        k = tail.search(rest)
        if k:
            cur["from_to"] = cur["from_to"][: len(cur["from_to"]) - len(k.group(0))].strip()
            cur.update(corner=k.group(1), requirement=float(k.group(2)), actual=float(k.group(3)), slack=float(k.group(4)))
            out.append(cur)
            cur = None
    by_id = {c["id"]: c for c in out}
    if "Bus Skew Report Per Constraint" in text:
        per = text.rsplit("Bus Skew Report Per Constraint", 1)[1]
        for blk in re.split(r"\n(?=Id: \d+\n)", per):
            m = re.match(r"\s*-*\s*Id: (\d+)", blk) or re.search(r"^Id: (\d+)", blk, re.M)
            if not m or int(m.group(1)) not in by_id:
                continue
            c = by_id[int(m.group(1))]
            cmd = re.search(r"^(set_bus_skew .*)$", blk, re.M)
            c["command"] = cmd.group(1) if cmd else ""
            c["endpoints"] = sorted(set(re.findall(r"^\S+\s+\S+\s+(\S+)/D\s+\S+/D\s", blk, re.M)))
            u = re.findall(r"Clock Uncertainty:\s+([\d.]+)ns", blk)
            c["uncertainty"] = max(map(float, u)) if u else None
    return out


def parse_exceptions_dpo(text: str) -> list[dict[str, Any]]:
    """report_exceptions: the rows whose Setup column is max_dpo=<ns> (set_max_delay -datapath_only)."""
    rows = []
    for line in text.splitlines():
        m = re.search(r"max_dpo=(-?[\d.]+)", line)
        p = re.match(r"\s*(\d+)\s", line)
        if m and p:
            rows.append({"position": int(p.group(1)), "value": float(m.group(1)), "text": line.strip()})
    return rows


def _years(s: str) -> float | None:
    m = re.match(r"\s*([\d.eE+-]+)\s*(year|day|hour|min|sec|s\b)", s)
    if not m:
        return None
    v = float(m.group(1))
    scale = {"year": 1.0, "day": 1 / 365.25, "hour": 1 / 8766.0, "min": 1 / 525960.0, "sec": 1 / 31557600.0, "s": 1 / 31557600.0}
    return v * scale[m.group(2)]


def parse_mtbf(text: str) -> dict[str, Any]:
    """report_synchronizer_mtbf: the overall synchroniser MTBF and one dict per chain (MTBF in years, None if UNDEFINED)."""
    res: dict[str, Any] = {"overall_years": None, "overall_text": "", "n_sync": 0, "chains": []}
    m = re.search(r"\|\s*Synchronizers\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|", text)
    if m:
        res["n_sync"] = int(m.group(1))
        res["overall_text"] = m.group(2)
        res["overall_years"] = _years(m.group(2))
    if "Synchronizer Chain Summary" in text:
        body = text.rsplit("Synchronizer Chain Summary", 1)[1]
        for line in body.splitlines():
            f = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(f) >= 9 and f[0].isdigit():
                res["chains"].append({"path": int(f[0]), "mtbf_text": f[1], "mtbf_years": _years(f[1]),
                                      "toggle_mtrs": f[2], "sample_mhz": f[3], "settling_ns": f[4],
                                      "src_clock": f[5], "dst_clock": f[6], "stages": f[7], "net": f[8]})
            elif "Hard FIFO Summary" in line:
                break
    return res


def methodology_rules(text: str, ids: tuple[str, ...]) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if any(re.match(rf"\s*{i}\s", ln) or f" {i} " in ln for i in ids)]


# ---------------------------------------------------------------- Quartus parsers (no Quartus flow in the agent yet: used on records)


def parse_quartus_max_skew(text: str) -> dict[str, Any]:
    """Quartus report_max_skew (text file): the summary line and one dict per set_max_skew constraint (slack, required, actual,
    from, to). A report of a design with no set_max_skew has no "Found N paths" line: ``paths`` is then 0."""
    res: dict[str, Any] = {"paths": 0, "violated": 0, "worst_slack": None, "constraints": []}
    m = re.search(r"Found (\d+) paths \((\d+) violated\)\. Worst case slack is (-?[\d.]+)", text)
    if m:
        res.update(paths=int(m.group(1)), violated=int(m.group(2)), worst_slack=float(m.group(3)))
    for line in text.splitlines():
        f = [x.strip() for x in line.strip().strip(";").split(";")]
        if len(f) > 5 and f[0] == "set_max_skew":
            res["constraints"].append({"slack": float(f[1]), "required": float(f[2]), "actual": float(f[3]), "from": f[4], "to": f[5]})
    return res


def parse_quartus_metastability(text: str) -> dict[str, Any]:
    """Quartus report_metastability (text file): the design MTBF lines, the chain count, the shortest chain, the worst settling
    time and each chain's source, synchronisation node and MTBF text ("Greater than 1 Billion" is the report's own cap)."""
    res: dict[str, Any] = {"worst_mtbf": None, "typical_mtbf": None, "n_chains": None, "shortest": None, "settling_ns": None,
                           "chains": []}
    for key, pat in (("worst_mtbf", r"Worst-Case MTBF of Design is ([^\n]+?)\.\n"), ("typical_mtbf", r"Typical MTBF of Design is ([^\n]+?)\.\n"),
                     ("n_chains", r"Number of Synchronizer Chains Found: (\d+)"), ("shortest", r"Shortest Synchronizer Chain: (\d+) Register"),
                     ("settling_ns", r"Worst Case Available Settling Time: (-?[\d.]+) ns")):
        m = re.search(pat, text)
        if m:
            res[key] = int(m.group(1)) if key in ("n_chains", "shortest") else (float(m.group(1)) if key == "settling_ns" else m.group(1))
    if "Synchronizer Summary" in text:
        body = text.split("Synchronizer Summary", 1)[1].split("Synchronizer Chain #", 1)[0]
        for line in body.splitlines():
            f = [x.strip() for x in line.strip().strip(";").split(";")]
            if len(f) == 5 and f[0] and f[0] != "Source Node":
                res["chains"].append({"source": f[0], "sync": f[1], "worst_mtbf": f[2], "typical_mtbf": f[3], "included": f[4]})
    return res


def evaluate_quartus(rep_dir: Path, corner: str, mtbf_target_years: float | None = None) -> dict[str, Any]:
    """The same step for a Quartus Timing Analyzer record (no Quartus flow in the agent yet: brief 207 records only):
    QCDCM-SKEW-VIOL (gate) a set_max_skew violated; QCDCM-SKEW-NONE (advisory) no set_max_skew path analysed (none set, or a clock group
    or false path cut it: Quartus help, set_max_skew); QCDCM-CHAIN-SHORT (advisory) a synchroniser chain shorter than 2 registers;
    QCDCM-MTBF-LOW (advisory) design MTBF below the target. Reads max_skew_<corner>.rpt and metastability_<corner>.rpt."""
    d = Path(rep_dir)
    target = mtbf_target_years or MTBF_TARGET_YEARS
    findings: list[dict[str, Any]] = []
    sk = parse_quartus_max_skew((d / f"max_skew_{corner}.rpt").read_text(errors="replace")) if (d / f"max_skew_{corner}.rpt").exists() else None
    if sk is not None:
        for c in sk["constraints"]:
            if c["slack"] < 0:
                findings.append({"code": "QCDCM-SKEW-VIOL", "level": "gate", "text": f"set_max_skew {c['from']} -> {c['to']}: slack {c['slack']}"})
        if sk["paths"] == 0:
            findings.append({"code": "QCDCM-SKEW-NONE", "level": "advisory", "text": "report_max_skew analysed no path"})
    mt = parse_quartus_metastability((d / f"metastability_{corner}.rpt").read_text(errors="replace")) if (d / f"metastability_{corner}.rpt").exists() else None
    if mt is not None:
        if mt["shortest"] is not None and mt["shortest"] < 2:
            findings.append({"code": "QCDCM-CHAIN-SHORT", "level": "advisory", "text": f"shortest synchroniser chain {mt['shortest']} register(s)"})
        y = _years(mt["worst_mtbf"] or "")
        if y is not None and y < target:
            findings.append({"code": "QCDCM-MTBF-LOW", "level": "advisory", "text": f"worst-case design MTBF {mt['worst_mtbf']}"})
    return {"evaluated": sk is not None or mt is not None, "pass": not any(f["level"] == "gate" for f in findings), "findings": findings,
            "max_skew": sk, "metastability": mt}


# ---------------------------------------------------------------- evaluation


def _base(name: str) -> str:
    name = re.sub(r"/(?:D|C|CE|R|S|CLR|PRE|Q)$", "", name)
    return re.sub(r"\[[\d:]+\]$", "", name)


def evaluate(build_dir: Path, crossings: list[dict[str, Any]] | None = None, mtbf_target_years: float | None = None,
             part: str = "") -> dict[str, Any]:
    """Run the checks on one build directory. ``crossings`` is the architecture's declared crossing list (each a dict with
    ``to`` (a capture register base name or regex), ``type`` (level, pulse, gray, handshake, ce, fifo, reset, static) and,
    for handshake/ce, ``sync_stages``)."""
    d = Path(build_dir)
    target = mtbf_target_years or MTBF_TARGET_YEARS
    findings: list[dict[str, Any]] = []
    bs_file = d / "bus_skew_route.rpt"
    if not bs_file.exists():
        return {"evaluated": False, "pass": True, "findings": [], "note": "no bus_skew_route.rpt: a build from before brief 207"}
    skews = parse_bus_skew(bs_file.read_text(errors="replace"))
    for c in skews:
        if c["slack"] < 0:
            findings.append({"code": "CDCM-SKEW-VIOL", "level": "gate", "id": c["id"], "requirement": c["requirement"],
                             "actual": c["actual"], "slack": c["slack"], "text": c["command"] or c["from_to"]})
    covered = " ".join(c["command"] + " " + c["from_to"] + " " + " ".join(c["endpoints"]) for c in skews)

    struct = None
    clocks: dict[str, float] = {}
    if (d / "cdc_paths_synth.rpt").exists():
        try:
            from flow import cdc_structure
        except ImportError:          # run as a script: flow/ is on sys.path
            import cdc_structure
        struct = cdc_structure.evaluate(d / "cdc_paths_synth.rpt", d / "cdc_synth.rpt")
        clocks = {k: v["period"] for k, v in struct["clocks"].items()}
    decl = crossings or []

    def declared(cell: str) -> dict[str, Any] | None:
        return next((x for x in decl if re.search(str(x.get("to", "^$")), cell)), None)

    if struct is not None:
        buses: dict[str, dict[str, Any]] = {}
        for x in struct["crossings"]:
            if x["class"] in ("gray", "handshake") and not (x.get("why", "").startswith("xpm") or "xpm_" in x.get("why", "")):
                b = _base(x["cell"])
                e = buses.setdefault(b, {"cell": b, "src_clock": x["src_clock"], "dst_clock": x["dst_clock"], "n": 0})
                e["n"] += 1
        for b, e in sorted(buses.items()):
            if e["n"] < 2:
                continue
            short = b.split("/")[-1]
            if short not in covered and b not in covered:
                findings.append({"code": "CDCM-SKEW-MISSING", "level": "advisory", "cell": b, "bits": e["n"],
                                 "clocks": f"{e['src_clock']} -> {e['dst_clock']}",
                                 "text": "hand-built multi-bit crossing with no set_bus_skew on its capture registers"})

    ex_file = d / "exceptions_route.rpt"
    if ex_file.exists() and struct is not None:
        pairs = {}
        for x in struct["crossings"]:
            pairs.setdefault(_base(x["cell"]).split("/")[-1], (x["src_clock"], x["dst_clock"], x["cell"], x["class"]))
        for r in parse_exceptions_dpo(ex_file.read_text(errors="replace")):
            hit = next(((k, v) for k, v in pairs.items() if k and k in r["text"]), None)
            if hit is None:
                continue
            src, dst, cell, cls = hit[1]
            ps, pd = clocks.get(src), clocks.get(dst)
            if ps is None or pd is None:
                continue
            dc = declared(cell)
            if dc and dc.get("type") in BOUNDS:
                b = bounds(dc, ps, pd)
                if b["L"] is None:
                    continue
                bound, why = b["L"], f"the declared {dc['type']} bound"
            elif cls == "handshake":           # CE-captured data path: undeclared, allow XPM's default 4 request stages
                bound, why = 4 * pd, "4 x destination period (handshake data path, sync_stages not declared)"
            elif cls == "synchroniser":        # a single-bit synchroniser needs no bound for correctness (AMD's XPM sets none)
                bound, why = max(ps, pd), "the larger period (single-bit synchroniser)"
            else:
                bound, why = ps, "source period"
            if r["value"] > bound + 1e-6:
                findings.append({"code": "CDCM-DPO-LOOSE", "level": "advisory", "position": r["position"], "value": r["value"],
                                 "bound": round(bound, 3), "text": f"max_dpo {r['value']} above the {why} ({bound:.3f} ns) for {hit[0]}"})

    usplus = part.startswith(("xck", "xczu", "xcvu", "xcku", "xcau")) or (d / "mtbf_route.rpt").exists()
    mtbf = None
    if usplus:
        mf = d / "mtbf_route.rpt"
        if not mf.exists():
            findings.append({"code": "CDCM-MTBF-MISSING", "level": "advisory", "text": "UltraScale+ build without mtbf_route.rpt"})
        else:
            mtbf = parse_mtbf(mf.read_text(errors="replace"))
            if struct is not None:
                # the report names each chain by the net it samples (often a wire alias, measured: wsend_a[7] for wq1_b_reg[7]), not by a
                # register, so chains are compared by count: every ASYNC_REG chain endpoint the structural check found (classes synchroniser
                # and gray, hand-built or XPM single; reset bridges are on CLR pins and are not in the report) must be counted in it
                want = sum(1 for x in struct["crossings"] if x["class"] in ("synchroniser", "gray") and x["pin"] == "D")
                have = len(mtbf["chains"])
                if have < want:
                    findings.append({"code": "CDCM-MTBF-MISSING", "level": "advisory", "chains_reported": have, "chains_found": want,
                                     "text": f"report_synchronizer_mtbf lists {have} chains, the netlist has {want} synchroniser chain endpoints "
                                             "(ASYNC_REG on every stage?)"})
            low = [c for c in mtbf["chains"] if c["mtbf_years"] is None or c["mtbf_years"] < target]
            for c in low:
                findings.append({"code": "CDCM-MTBF-LOW", "level": "advisory", "net": c["net"], "mtbf": c["mtbf_text"],
                                 "target_years": target})
            if mtbf["overall_years"] is not None and mtbf["overall_years"] < target:
                findings.append({"code": "CDCM-MTBF-LOW", "level": "advisory", "net": "overall", "mtbf": mtbf["overall_text"],
                                 "target_years": target})

    mf = d / "methodology.rpt"
    if mf.exists():
        for ln in methodology_rules(mf.read_text(errors="replace"), ("TIMING-44", "TIMING-45")):
            findings.append({"code": "CDCM-UNC-HIGH", "level": "advisory", "text": ln[:200]})

    gate_fail = any(f["level"] == "gate" for f in findings)
    return {"evaluated": True, "pass": not gate_fail, "findings": findings, "bus_skew": skews, "mtbf": mtbf,
            "mtbf_target_years": target}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("build_dir")
    ap.add_argument("--part", default="")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    rep = evaluate(Path(a.build_dir), part=a.part)
    for f in rep["findings"]:
        print(f"{f['level']:8s} {f['code']}: {f.get('text', '')}")
    print("PASS" if rep["pass"] else "FAIL", "(not evaluated)" if not rep["evaluated"] else "")
    if a.json:
        Path(a.json).write_text(json.dumps(rep, indent=2, default=str) + "\n")
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
