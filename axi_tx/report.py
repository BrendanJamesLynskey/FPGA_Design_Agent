#!/usr/bin/env python3
"""Brief 59A results: collect the raw records into results/59a_axi_tx/ and write its README and the showcase page data.

    python3 axi_tx/report.py collect      # copy build/59a records (formal, simulation, AMD IP probe, resources) into results/
    python3 axi_tx/report.py write        # results/59a_axi_tx/README.md and site/data/showcase_59a_axi_tx.json
    python3 axi_tx/report.py check        # both written files equal what `write` would produce now (CI)

Every number in the README and in the page data comes from a JSON file in results/59a_axi_tx/.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results" / "59a_axi_tx"
BUILD = ROOT / "build" / "59a"
SITE = ROOT / "site" / "data" / "showcase_59a_axi_tx.json"
sys.path.insert(0, str(ROOT))

from axi_tx.host import regs  # noqa: E402


def collect() -> None:
    RES.mkdir(parents=True, exist_ok=True)
    (RES / "sim").mkdir(exist_ok=True)
    shutil.copy(BUILD / "formal.json", RES / "formal.json")
    for f in sorted((BUILD / "sim").glob("*.json")):
        d = json.loads(f.read_text())
        (RES / "sim" / f.name).write_text(json.dumps(d, indent=1) + "\n")
    probe = {"tool": None, "cores": {}}
    for line in (BUILD / "ipprobe" / "vivado.log").read_text().splitlines():
        if not line.startswith("FDA-IP ") or line.split()[1] == "DONE":
            continue
        w = line.split()
        if w[1] == "VIVADO":
            probe["tool"] = {"vivado": w[2], "tier": w[4]}
        elif w[2] == "CATALOGUE":
            probe["cores"].setdefault(w[1], {})["vlnv"] = w[3]
            probe["cores"][w[1]]["requires_license"] = int(w[5])
        elif w[2] == "BUILD":
            c = probe["cores"].setdefault(w[1], {})
            c["build"] = w[3]
            m = re.search(r"seconds (\d+) LUT (\d+) FF (\d+)", line)
            if m:
                c["synth_ip_seconds"], c["lut"], c["ff"] = (int(x) for x in m.groups())
            rpt = BUILD / "ipprobe" / f"{w[1]}_util.rpt"
            if rpt.is_file():
                b = re.search(r"\|\s*Block RAM Tile\s*\|\s*([0-9.]+)", rpt.read_text())
                c["bram_tiles"] = float(b.group(1)) if b else None
    (RES / "amd_ip_probe.json").write_text(json.dumps(probe, indent=1) + "\n")
    rows, excluded = [], None
    for line in (BUILD / "resources" / "vivado.log").read_text().splitlines():
        m = re.match(r"FDA-RES (\S+) top (\S+) generics \{(.*)\} LUT (\d+) FF (\d+) BRAM ([0-9.]+) seconds (\d+)", line)
        if m and m.group(1) == "core_full_s64":
            excluded = {"config": m.group(1), "lut": int(m.group(4)), "ff": int(m.group(5)), "bram_tiles": float(m.group(6)),
                        "why": "synthesis trimmed the sequencer at SDATA_W = 64 (not root-caused); 59A's core is 32-bit only"}
        elif m:
            rows.append({"config": m.group(1), "top": m.group(2), "generics": m.group(3), "lut": int(m.group(4)),
                         "ff": int(m.group(5)), "bram_tiles": float(m.group(6))})
    (RES / "resources.json").write_text(json.dumps({"part": "xc7a100tcsg324-1", "mode": "synth_design -mode out_of_context",
                                                     "rows": rows, "excluded": excluded}, indent=1) + "\n")


def _load(name: str) -> Any:
    f = RES / name
    return json.loads(f.read_text()) if f.is_file() else None


def page_data() -> dict[str, Any]:
    board = _load("board_run.json")
    formal = _load("formal.json")
    resources = _load("resources.json")
    probe = _load("amd_ip_probe.json")
    impl = _load("board_build.json")
    d: dict[str, Any] = {"brief": "59A", "board": "Nexys A7-100T", "part": "xc7a100tcsg324-1", "vivado": "2026.1",
                         "sources": ["results/59a_axi_tx/board_run.json", "results/59a_axi_tx/formal.json",
                                     "results/59a_axi_tx/resources.json", "results/59a_axi_tx/amd_ip_probe.json",
                                     "results/59a_axi_tx/board_build.json"]}
    if formal:
        d["formal"] = {u: v["summary"] for u, v in formal["units"].items()} | {"depth": formal["depth"]}
    if resources:
        d["resources"] = resources["rows"]
    if probe:
        d["amd_ip"] = {k: {x: v.get(x) for x in ("vlnv", "requires_license", "build", "lut", "ff", "bram_tiles")}
                       for k, v in probe["cores"].items()} | {"tier": probe["tool"]["tier"]}
    if impl:
        d["implementation"] = impl
    if board:
        runs = board["runs"]
        d["board_runs"] = [{"tag": r["tag"], "repeat": r["repeat"], "pass": r["pass"], "seconds": r["seconds"],
                            "n_txn": r["summary"]["n_txn"], "digest": f"{r['summary']['digest']:08x}",
                            "lite_rules": {k: v for k, v in r["lite_rules"]["counts"].items() if v},
                            "stream_rules": {k: v for k, v in r["stream_rules"]["counts"].items() if v},
                            "first_rule": r["lite_rules"]["first"] or r["stream_rules"]["first"],
                            "first_rule_cycle": (r["lite_rules"]["first_time"] if r["lite_rules"]["first"]
                                                 else r["stream_rules"]["first_time"] if r["stream_rules"]["first"] else None),
                            "sb_checked": r["summary"]["sb_checked"], "sb_mism": r["summary"]["sb_mism"],
                            "sink": r["summary"]["sink"], "amd_pc_asserted": r.get("amd_pc_asserted"),
                            "sim_equal": None if "sim_compare" not in r else {
                                k: r["sim_compare"][k]["equal"] for k in ("digest", "cycles", "n_txn")},
                            "sim_log": (r.get("sim_compare") or {}).get("log"),
                            "target": "periph" if r["tag"].startswith(("periph", "master", "stream")) else "bram",
                            "model_match": r["model_compare"]["match"]} for r in runs]
        d["conditions"] = {"inside_roc": board["inside_roc"], "jtag": board["conditions_jtag"],
                           "fabric": board["conditions_fabric"], "limits": board["roc_limits"], "note": board["note"]}
        d["build_id"] = board.get("build_id")
        d["build_stamp"] = board.get("build_stamp")
        # the hero: the capture around the first seeded protocol bug caught on the board (B_EARLY)
        hero = next((r for r in runs if r["tag"] == "periph_regs_b_early"), None)
        if hero and hero["capture"].get("triggered"):
            cap = hero["capture"]
            lo = max(0, cap["trigger_index"] - 24)
            d["hero"] = {"tag": hero["tag"], "rule": "B_EARLY", "trigger_index": cap["trigger_index"] - lo,
                         "fields": [f[0] for f in regs.CAPTURE_FIELDS],
                         "rows": cap["rows"][lo:cap["trigger_index"] + 24]}
        clean = [r for r in runs if r["tag"] == "bram_random_rw"]
        if clean:
            m = clean[0]["lite_mon"]
            d["latency"] = {"write_bins": [m[f"wlat_{b}"] for b in regs.LAT_BINS],
                            "read_bins": [m[f"rlat_{b}"] for b in regs.LAT_BINS], "bins": regs.LAT_BINS,
                            "write_min": m["wlat_min"], "write_max": m["wlat_max"], "read_min": m["rlat_min"],
                            "read_max": m["rlat_max"], "tag": "bram_random_rw"}
            d["coverage"] = {k: m[k] for k in m if k.startswith(("wait_", "order_", "wstrb_", "bresp_", "rresp_"))}
    return d


def readme(d: dict[str, Any]) -> str:
    L = ["# Brief 59A: the on-chip AXI transactor, protocol checker and scoreboard",
         "",
         "Design and method: [docs/axi_tx.md](../../docs/axi_tx.md). Every number below is read from a JSON file in this folder by",
         "[axi_tx/report.py](../../axi_tx/report.py); the page data is [site/data/showcase_59a_axi_tx.json](../../site/data/showcase_59a_axi_tx.json).",
         ""]
    if "board_runs" in d:
        ok = sum(r["pass"] for r in d["board_runs"])
        L += [f"## On the board (Nexys A7-100T, xc7a100tcsg324-1, Vivado 2026.1)", "",
              f"{ok} of {len(d['board_runs'])} pre-registered runs passed ([board_plan.yaml](../../axi_tx/programs/board_plan.yaml),"
              f" [board_run.json](board_run.json)); build ID `{d.get('build_id')}`, build stamp `{d.get('build_stamp')}`.",
              f"Operating conditions: {'inside' if d['conditions']['inside_roc'] else 'OUTSIDE'} the recommended operating conditions"
              " at every sample (JTAG XADC before and after, fabric XADC with its min/max and latched alarms after every run).", "",
              "| Run | Pass | Transactions | Rules fired (episodes) | Scoreboard checked / mismatched | AMD checker | Same digest as simulation |",
              "|---|---|---|---|---|---|---|"]
        for r in d["board_runs"]:
            rules = ", ".join(f"{k} {v}" for k, v in {**r["lite_rules"], **r["stream_rules"]}.items()) or "none"
            se = r["sim_equal"]
            same = "n/a" if se is None else ("not compared (AMD core on the board)" if r["target"] == "bram"
                                             else ("yes" if se["digest"] else "no"))
            L.append(f"| {r['tag']} #{r['repeat']} | {'yes' if r['pass'] else 'NO'} | {r['n_txn']} | {rules} | "
                     f"{r['sb_checked']} / {r['sb_mism']} | {'asserted' if r['amd_pc_asserted'] else 'quiet'} | {same} |")
        L += ["", "The digest is a CRC-32 over every transaction including its latency in cycles. Runs on target `periph` use the"
              " same RTL in simulation and on the board, so their digests must be equal; runs on target `bram` use AMD's AXI BRAM"
              " Controller on the board and a memory model in simulation, so only their transactions and verdicts are compared"
              " (with the model), not their timing.", ""]
    if "formal" in d:
        f = d["formal"]
        L += ["## Formal proof of the checker (SymbiYosys, bounded, depth %d)" % f["depth"], "",
              "| Unit | Proofs passed | Checker mutants killed |", "|---|---|---|"]
        for u in ("axil", "axis"):
            L.append(f"| {u}_rules | {f[u]['proofs_pass']} of {f[u]['proofs']} | {f[u]['mutants_killed']} of {f[u]['mutants']} |")
        L += ["", "Records: [formal.json](formal.json).", ""]
    if "resources" in d:
        L += ["## Resource cost (out-of-context synthesis, xc7a100tcsg324-1, Vivado 2026.1)", "",
              "| Configuration | Top | Generics | LUT | FF | BRAM tiles |", "|---|---|---|---|---|---|"]
        for r in d["resources"]:
            L.append(f"| {r['config']} | {r['top']} | {r['generics'] or '-'} | {r['lut']} | {r['ff']} | {r['bram_tiles']:g} |")
        ex = (_load("resources.json") or {}).get("excluded")
        if ex:
            L += ["", f"Not in the table: `{ex['config']}` ({ex['why']}; it synthesised to {ex['lut']} LUT, which is not a cost).",
                  "The stand-alone stream checker is measured at 32, 64 and 128 bits."]
        L += ["", "Records: [resources.json](resources.json).", ""]
    if "amd_ip" in d:
        L += [f"## AMD IP on Vivado 2026.1 ({d['amd_ip']['tier']} tier)", "",
              "| Core | Catalogue entry | Licence needed | Builds (create_ip, synth_ip) | LUT | FF | BRAM tiles |",
              "|---|---|---|---|---|---|---|"]
        for k, v in d["amd_ip"].items():
            if k == "tier":
                continue
            L.append(f"| {k} | {v['vlnv']} | {'yes' if v['requires_license'] else 'no'} | {v['build']} | {v.get('lut')} | "
                     f"{v.get('ff')} | {v.get('bram_tiles')} |")
        L += ["", "Records: [amd_ip_probe.json](amd_ip_probe.json) from [amd_ip_probe.tcl](../../axi_tx/vivado/amd_ip_probe.tcl).", ""]
    return "\n".join(L) + "\n"


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "write"
    if cmd == "collect":
        collect()
        return 0
    d = page_data()
    text, js = readme(d), json.dumps(d, indent=1) + "\n"
    if cmd == "check":
        ok = (RES / "README.md").read_text() == text and SITE.read_text() == js
        print("report: current" if ok else "report: STALE, run axi_tx/report.py write")
        return 0 if ok else 1
    (RES / "README.md").write_text(text)
    SITE.parent.mkdir(parents=True, exist_ok=True)
    SITE.write_text(js)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
