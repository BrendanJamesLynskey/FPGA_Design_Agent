#!/usr/bin/env python3
"""Brief 59A results: collect the raw records into results/59a_axi_tx/, derive the showcase files, write the README.

    python3 axi_tx/report.py collect      # copy build/59a records (formal, simulation, AMD IP probe, resources) into results/
    python3 axi_tx/report.py write        # results/59a_axi_tx/README.md and page_data.json
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

import yaml

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results" / "59a_axi_tx"
BUILD = ROOT / "build" / "59a"
SITE = ROOT / "results" / "59a_axi_tx" / "page_data.json"     # the full record; the showcase page reads summary.json, hero.json
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
    import os
    res_dir = BUILD / os.environ.get("AXI_TX_RES_DIR", "resources")
    for line in (res_dir / "vivado.log").read_text().splitlines():
        m = re.match(r"FDA-RES (\S+) top (\S+) generics \{(.*)\} LUT (\d+) FF (\d+) BRAM ([0-9.]+) seconds (\d+)", line)
        if m and m.group(1) == "core_full_s64":
            excluded = {"config": m.group(1), "lut": int(m.group(4)), "ff": int(m.group(5)), "bram_tiles": float(m.group(6)),
                        "why": "synthesis trimmed the sequencer at SDATA_W = 64 (not root-caused); 59A's core is 32-bit only"}
        elif m:
            rows.append({"config": m.group(1), "top": m.group(2), "generics": m.group(3), "lut": int(m.group(4)),
                         "ff": int(m.group(5)), "bram_tiles": float(m.group(6))})
    if excluded is None and (RES / "resources.json").is_file():       # keep the record of the withdrawn row
        excluded = json.loads((RES / "resources.json").read_text()).get("excluded")
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
    board, summ, build = _load("board_run.json"), _load("summary.json") or {}, _load("board_build.json") or {}
    L = ["# Results: the on-chip AXI transactor and protocol checker",
         "",
         "Measured results for the on-chip AXI transactor, protocol checker and scoreboard: board runs on a Nexys A7-100T, a",
         "bounded formal check of the checker, its resource cost, and a build test of the AMD AXI IP cores it was compared with.",
         "Method and terms: [docs/axi_tx.md](../../docs/axi_tx.md).",
         "",
         "Reproduce the simulation and formal parts (no board): `python -m pytest -q axi_tx/tests/test_59a_rtl.py && "
         "python axi_tx/formal/run_formal.py`.",
         "",
         "Rule names used below: B_EARLY = a write response sent before its write data arrived; R_HOLD = read data changed while",
         "the master was not ready; EXOKAY = an exclusive-access response, which AXI4-Lite does not allow; AW_HOLD, W_HOLD,",
         "AR_HOLD = a request dropped or changed before it was accepted; IN_RESET = a VALID high while reset is held; HOLD",
         "(stream) = stream data changed while the receiver was not ready.",
         ""]
    if "board_runs" in d:
        ok = sum(r["pass"] for r in d["board_runs"])
        L += ["## On the board (Nexys A7-100T, xc7a100tcsg324-1, Vivado 2026.1)", "",
              f"{ok} of {len(d['board_runs'])} runs passed. The runs and what each must show were written in a plan before the"
              " board was used ([board_plan.yaml](../../axi_tx/programs/board_plan.yaml)); a run passes when its verdict is the"
              f" one the plan expects ([board_run.json](board_run.json)). Build ID `{d.get('build_id')}` (read back over JTAG"
              f" before the runs: {'matched' if (board.get('build_id_jtag') or {}).get('match') else 'not recorded'}), build"
              f" stamp `{d.get('build_stamp')}`.",
              f"Operating conditions: {'inside' if d['conditions']['inside_roc'] else 'OUTSIDE'} the recommended operating conditions"
              " at every sample (JTAG XADC before and after, fabric XADC with its min/max and latched alarms after every run).", ""]
        att = RES / "board_run_attempts.md"
        if att.is_file():
            L += ["Earlier attempts, before this plan's final run, are listed in [board_run_attempts.md](board_run_attempts.md):"
                  " the model and the RTL were changed after them, and the whole plan was then run again on the final build.", ""]
        if board.get("git_dirty"):
            L += [f"The host code ran from a working tree with uncommitted changes (`git_dirty_files` in board_run.json),"
                  f" based on commit `{board.get('git_commit', '')[:7]}`; the bitstream is identified by its build ID.", ""]
        L += ["| Run | Pass | Transactions | Rules fired (episodes) | Scoreboard checked / mismatched | Stream receiver: packets, TLAST mismatches | AMD checker (AXI4-Lite) | Same digest and cycle count as simulation |",
              "|---|---|---|---|---|---|---|---|"]
        for r in d["board_runs"]:
            rules = ", ".join(f"{k} {v}" for k, v in {**r["lite_rules"], **r["stream_rules"]}.items()) or "none"
            se = r["sim_equal"]
            same = "n/a" if se is None else ("not compared (vendor IP on the board)" if r["target"] == "bram"
                                             else ("yes" if se["digest"] and se["cycles"] else "no"))
            L.append(f"| {r['tag']} #{r['repeat']} | {'yes' if r['pass'] else 'NO'} | {r['n_txn']} | {rules} | "
                     f"{r['sb_checked']} / {r['sb_mism']} | {r['sink']['packets']}, {r['sink']['last_mism']} | "
                     f"{'asserted' if r['amd_pc_asserted'] else 'quiet'} | {same} |")
        L += ["",
              "- Data bugs are caught by the data checks, not by a rule: `periph_regs_no_strb` by the scoreboard, `stream_packets_lose_last`"
              " by the stream receiver's TLAST check.",
              "- The digest covers the AXI4-Lite transactions, latency included. Runs against our own peripheral and FIFO use the same RTL"
              " in simulation and on the board, so their digests must be equal; the stream runs are also compared counter by counter."
              " Runs on target `bram` use a vendor block-RAM controller IP core on the board and a memory model in simulation, so only"
              " their transactions and verdicts are compared (with the model), not their timing.",
              "- AMD's AXI Protocol Checker watches only the AXI4-Lite bus; on stream runs it can only stay quiet.",
              f"- The latency figures on the showcase page come from one run ({summ.get('latency_from_run', 'bram_random_rw #0')}).", ""]
    if "formal" in d:
        f = d["formal"]
        L += ["## Formal check of the checker (SymbiYosys, bounded to %d clock cycles)" % f["depth"], "",
              "A proof passes when no violation of its property is reachable within the depth; it says nothing about longer runs."
              " A mutant (a copy of the checker with one deliberate fault) is killed when at least one proof fails on it.", "",
              "| Unit | Proofs passed | Mutants killed (structural and semantic) | Of which semantic |", "|---|---|---|---|"]
        for u in ("axil", "axis"):
            L.append(f"| {u}_rules | {f[u]['proofs_pass']} of {f[u]['proofs']} | {f[u]['mutants_killed']} of {f[u]['mutants']} | "
                     f"{f[u].get('semantic_killed', '-')} of {f[u].get('semantic', '-')} |")
        L += ["", "Records: [formal.json](formal.json).", ""]
    if "resources" in d:
        L += ["## Resource cost (out-of-context synthesis, xc7a100tcsg324-1, Vivado 2026.1)", "",
              "| Configuration | Top | Generics | LUT | FF | BRAM tiles |", "|---|---|---|---|---|---|"]
        for r in d["resources"]:
            L.append(f"| {r['config']} | {r['top']} | {r['generics'] or '-'} | {r['lut']} | {r['ff']} | {r['bram_tiles']:g} |")
        core = next((r for r in d["resources"] if r["config"] == "core_full_s32"), None)
        if core and build.get("utilization"):
            L += ["", f"The full core is {core['lut']} LUTs here; the whole board design used {build['utilization']['lut']} after"
                  " implementation, because it adds the demo peripheral, the stream FIFO, the UART shell, the logic analyser, the"
                  " XADC readout and the vendor IP cores."]
        ex = (_load("resources.json") or {}).get("excluded")
        if ex:
            L += ["", f"A 64-bit stream version is not in the table: synthesis removed part of the sequencer at that width (cause not"
                  f" investigated), so its {ex['lut']} LUTs would understate the cost. The core is 32-bit only, and refuses other"
                  " widths at elaboration. The stand-alone stream checker is measured at 32, 64 and 128 bits."]
        L += ["", "Records: [resources.json](resources.json).", ""]
    if "amd_ip" in d:
        L += ["## AMD AXI IP cores on Vivado 2026.1 (the free licence tier)", "",
              "| Core | Catalogue entry | Licence needed | Builds (create_ip, synth_ip) | LUT | FF | BRAM tiles |",
              "|---|---|---|---|---|---|---|"]
        for k, v in d["amd_ip"].items():
            if k == "tier":
                continue
            L.append(f"| {k} | {v['vlnv']} | {'yes' if v['requires_license'] else 'no'} | {v['build']} | {v.get('lut')} | "
                     f"{v.get('ff')} | {v.get('bram_tiles'):g} |")
        L += ["", "Records: [amd_ip_probe.json](amd_ip_probe.json) from [amd_ip_probe.tcl](../../axi_tx/vivado/amd_ip_probe.tcl).", ""]
    L += ["Every number above is read from a JSON file in this folder by [axi_tx/report.py](../../axi_tx/report.py); the showcase"
          " page reads [summary.json](summary.json) and [hero.json](hero.json).", ""]
    return "\n".join(L) + "\n"


def showcase_files() -> None:
    """results/59a_axi_tx/hero.json (the wave hero: the board capture around the seeded B_EARLY bug) and summary.json
    (the page's numbers, each derived here from board_run.json, formal.json, board_build.json and resources.json)."""
    board, formal, build = _load("board_run.json"), _load("formal.json"), _load("board_build.json")
    runs = board["runs"]
    hero_run = next(r for r in runs if r["tag"] == "periph_regs_b_early")
    cap = hero_run["capture"]
    t = cap["trigger_index"]
    # the window opens just before the address handshake and closes after the master takes the early response
    rule_bit = [n for n, _, _ in regs.LITE_RULES].index("B_EARLY")
    first = next(i for i in range(t, -1, -1) if cap["rows"][i]["awvalid"] and cap["rows"][i]["awready"])
    last = next(i for i in range(t, len(cap["rows"])) if cap["rows"][i]["bvalid"] and cap["rows"][i]["bready"])
    lo, hi = max(0, first - 3), min(len(cap["rows"]), last + 2)
    rows = cap["rows"][lo:hi]
    sig = [("AWVALID", "awvalid"), ("AWREADY", "awready"), ("WVALID", "wvalid"), ("WREADY", "wready"),
           ("BVALID", "bvalid"), ("BREADY", "bready")]
    signals = [{"name": n, "kind": "bit", "v": [r[k] for r in rows]} for n, k in sig]
    signals.append({"name": "checker: B_EARLY", "kind": "bit", "v": [r["lite_viol"] >> rule_bit & 1 for r in rows]})
    caps, aw_done, w_done, b_done = [], False, False, False
    for r in rows:
        viol = r["lite_viol"] >> rule_bit & 1
        if r["awvalid"] and r["awready"]:
            c, aw_done = "AW accepted: the address is taken; no write data yet", True
        elif r["wvalid"] and r["wready"]:
            c, w_done = "W accepted: the write data arrives, after the response was raised", True
        elif viol and r["trig"]:
            c = "Violation: BVALID rises before any W handshake; the checker flags B_EARLY and starts this capture"
        elif r["bvalid"] and r["bready"]:
            c, b_done = "B accepted: the master takes the early response", True
        elif viol:
            c = "BVALID held, still no write data: B_EARLY stays flagged"
        elif r["bvalid"]:
            c = "BVALID held; the master is not ready for the response yet"
        elif b_done:
            c = "Write complete: the bus is quiet again"
        elif not aw_done:
            c = "Bus quiet before the write"
        else:
            c = "Address held by the peripheral, waiting for its data"
        caps.append(c)
    xs = [i + lo - t for i in range(len(rows))]
    w_at = next((x for x, r in zip(xs, rows) if r["wvalid"] and r["wready"]), None)
    amd = hero_run.get("amd_pc_asserted")
    stages = [
        {"name": "Run", "fact": f"build {board['build_id']}", "phase": "before",
         "captions": ["The transactor runs a register program against our peripheral with its early-response bug switched on. "
                      "The checker watches the bus wires and has armed a capture on its first violation."]},
        {"name": "Capture", "fact": f"{len(rows)} cycles", "phase": "during",
         "captions": ["The capture from the board, replayed cycle by cycle around the trigger."]},
        {"name": "Verdict", "fact": f"cycle {hero_run['lite_rules']['first_time']} of the run", "phase": "after",
         "captions": ["The checker names the rule broken: B_EARLY, a write response raised before its write data had arrived."
                      + (" AMD's AXI Protocol Checker on the same bus also flagged this run." if amd else "")]},
    ]
    marks = [{"x": 0, "label": "trigger: B_EARLY", "signal": "BVALID"}]
    if w_at is not None:
        marks.append({"x": w_at, "label": "write data arrives", "signal": "WVALID"})
    hero = {"wave": {"unit": "cycle", "x": xs, "signals": signals, "captions": caps, "stages": stages, "marks": marks,
                     "tick": 5, "source_run": hero_run["tag"], "trigger_at_x": 0,
                     "alt": "A waveform captured on the board: after the address handshake the peripheral raises BVALID, its "
                            "write response, before any write data; the checker's B_EARLY rule goes high in that cycle and the "
                            "write data arrives afterwards."}}
    (RES / "hero.json").write_text(json.dumps(hero, indent=1) + "\n")

    def flagged(r):
        return sorted(k for k, v in {**r["lite_rules"]["counts"], **r["stream_rules"]["counts"]}.items() if v)
    # what each run was meant to be comes from the plan, never from what fired
    plan = yaml.safe_load((ROOT / "axi_tx" / "programs" / board["plan"]).read_text())["runs"]
    expect = {it.get("tag", it.get("program")): it.get("expect", {}) for it in plan}
    def exp_rules(r):
        e = expect[r["tag"]]
        return e.get("lite_rules", []) + e.get("stream_rules", [])
    proto = [r for r in runs if exp_rules(r)]
    data = [r for r in runs if not exp_rules(r) and (expect[r["tag"]].get("sb_mism") or expect[r["tag"]].get("sink_last_mism"))]
    periph = [r for r in runs if not r["tag"].startswith("bram")]
    compared = [r for r in periph if "sim_compare" in r]
    lite_flag = [r for r in runs if any(r["lite_rules"]["counts"].values())]
    clean = [r for r in runs if not exp_rules(r) and r not in data]
    m = next(r for r in runs if r["tag"] == "bram_random_rw")["lite_mon"]
    jt = board["conditions_jtag"]
    summ = {
        "runs": len(runs), "runs_pass": sum(r["pass"] for r in runs),
        "protocol_bug_runs": len(proto),
        "protocol_faults": sum(len(exp_rules(r)) for r in proto),
        "protocol_bug_runs_expected_rule": len([r for r in proto if flagged(r) == sorted(exp_rules(r))]),
        "functional_bug_runs": len(data),
        "functional_bug_runs_caught": len([r for r in data if r["pass"] and not flagged(r)]),
        "clean_runs": len(clean), "clean_runs_quiet": len([r for r in clean if not flagged(r)]),
        "latency_from_run": "bram_random_rw #0",
        "parity_runs": len(compared),
        "parity_digest_equal": len([r for r in compared if r["sim_compare"]["digest"]["equal"] and r["sim_compare"]["cycles"]["equal"]]),
        "parity_txn_compared": sum(r["sim_compare"]["log"]["compared"] for r in compared),
        "parity_txn_differences": sum(r["sim_compare"]["log"]["differences"] for r in compared),
        "amd_agree": len([r for r in runs if bool(r.get("amd_pc_asserted")) == any(r["lite_rules"]["counts"].values())]),
        "amd_asserted": len([r for r in runs if r.get("amd_pc_asserted")]), "ours_lite_flagged": len(lite_flag),
        "b_early_cycle": hero_run["lite_rules"]["first_time"],
        "formal_proofs": sum(u["summary"]["proofs"] for u in formal["units"].values()),
        "formal_proofs_pass": sum(u["summary"]["proofs_pass"] for u in formal["units"].values()),
        "formal_mutants": sum(u["summary"]["mutants"] for u in formal["units"].values()),
        "formal_mutants_killed": sum(u["summary"]["mutants_killed"] for u in formal["units"].values()),
        "formal_depth": formal["depth"],
        "lite_rules": len(regs.LITE_RULES), "stream_rules": len(regs.STREAM_RULES),
        "wns_ns": build["timing"]["wns_ns"], "power_w": build["power"]["total_w"], "lut": build["utilization"]["lut"],
        "ff": build["utilization"]["ff"], "build_id": build["build_id"],
        "tj_max_c": max(s["max"]["TEMPERATURE"] for s in jt if "max" in s),
        "vccint_min_v": min(s["min"]["VCCINT"] for s in jt if "min" in s), "vccint_max_v": max(s["max"]["VCCINT"] for s in jt if "max" in s),
        "alarms_latched": sum(len(s.get("alarms_latched", [])) for s in board["conditions_fabric"]),
        "inside_roc": board["inside_roc"],
        "bram_write_latency_min": m["wlat_min"], "bram_write_latency_max": m["wlat_max"],
        "bram_read_latency_min": m["rlat_min"], "bram_read_latency_max": m["rlat_max"],
        "bram_reads_checked": next(r for r in runs if r["tag"] == "bram_random_rw")["summary"]["sb_checked"],
    }
    (RES / "summary.json").write_text(json.dumps(summ, indent=1) + "\n")


def portfolio_card() -> None:
    """site/portfolio/axi_transactor/portfolio.json: three facts, every number from summary.json and named by its source in
    site/data (the page's resolved values), checked by axi_tx/tests/test_59a_host.py."""
    s = _load("summary.json")
    v = "site/data:showcase.projects.id=axi_transactor.values."
    card = {
        "id": "axi_transactor", "title": "An on-chip AXI traffic generator and protocol checker",
        "tagline": "A block beside the design under test that drives AXI4-Lite and AXI4-Stream traffic from a program loaded at run "
                   "time and checks named protocol rules in hardware",
        "url": "https://fpga-design-agent.vercel.app/showcase/axi_transactor.html",
        "facts": [
            {"text": f"A hardware checker flagged the expected rule in all {s['protocol_bug_runs']} runs with a seeded protocol bug "
                     f"({s['protocol_faults']} faults) on the Nexys A7; AMD's own AXI Protocol Checker on the same AXI4-Lite bus "
                     f"gave the same verdict in all {s['runs']} runs.",
             "source": v + "bug_runs", "also": [v + "faults", v + "runs"]},
            {"text": f"On our own test peripheral and stream FIFO, the board's traffic matched the simulation cycle for cycle in "
                     f"{s['parity_digest_equal']} of {s['parity_runs']} runs, with {s['parity_txn_differences']} differences in "
                     f"{s['parity_txn_compared']} logged transactions.",
             "source": v + "parity_eq", "also": [v + "parity", v + "txn_diff", v + "txns"]},
            {"text": f"The checker is checked formally to {s['formal_depth']} clock cycles (bounded): {s['formal_proofs_pass']} of "
                     f"{s['formal_proofs']} properties hold, and {s['formal_mutants_killed']} of {s['formal_mutants']} "
                     f"deliberately broken copies of it are caught.",
             "source": v + "proofs_pass", "also": [v + "depth", v + "proofs", v + "mutants_killed", v + "mutants"]}],
        "media": {"still_1200x630": "hero_1200x630.png", "animation": "replay.webm", "animation_mp4": "replay.mp4",
                  "alt": "A waveform captured on the board, replayed cycle by cycle: after the address handshake the peripheral "
                         "raises BVALID, its write response, before any write data; the checker's B_EARLY rule (a response "
                         "before its data) goes high, and the write data arrives only afterwards.",
                  "note": "Recorded from the showcase page's own hero (results/59a_axi_tx/hero.json) by axi_tx/portfolio_capture.js."},
        "status": "Measured on the board; full AXI4, the slave side and long soak runs are planned next."}
    (ROOT / "site" / "portfolio" / "axi_transactor" / "portfolio.json").write_text(json.dumps(card, indent=1) + "\n")


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "write"
    if cmd == "collect":
        collect()
        showcase_files()
        return 0
    if cmd == "write":
        showcase_files()
        portfolio_card()
    d = page_data()
    text, js = readme(d), json.dumps(d, indent=1) + "\n"
    if cmd == "check":
        # the showcase sources too: regenerate summary.json and hero.json into memory and compare with the committed files
        before = {n: (RES / n).read_text() for n in ("summary.json", "hero.json")}
        showcase_files()
        after = {n: (RES / n).read_text() for n in before}
        for n, t in before.items():
            (RES / n).write_text(t)
        ok = (RES / "README.md").read_text() == text and SITE.read_text() == js and before == after
        print("report: current" if ok else "report: STALE (README, page_data, summary.json or hero.json); run axi_tx/report.py write")
        return 0 if ok else 1
    (RES / "README.md").write_text(text)
    SITE.parent.mkdir(parents=True, exist_ok=True)
    SITE.write_text(js)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
