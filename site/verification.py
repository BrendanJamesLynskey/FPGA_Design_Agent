"""Data for site/src/verification.html (brief 81): how the agent's designs are verified, technique by technique.

    site/verification/verification.yaml   the authored page: techniques, the technique-to-stage map, values, text
    site/data/verification.json           what the page reads (written by site/export.py)

Nothing measured is typed by hand. A number in the prose is a {name} placeholder whose value is read from a committed file by
one of site/expertise.py's expressions (or str:REGEX for a version kept as text), or derived here from a named record by a stated
formula. The prose itself may hold only names (tools, rule ids, Vivado 2026.1). The matrices and tables are drawn from the
records, never from typed numbers. Every linked path and every check named on the map must exist. The page's number check
sees the resolved values, never the page's own text. The method is the one of site/story.py (brief 76).
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import yaml

import expertise
import story

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DIR = HERE / "verification"

ContractError = story.ContractError
#: names that contain digits but are not measurements (the story page's list, plus the bus names used here)
PROSE_OK = re.compile(story.PROSE_OK.pattern + r"|\bAXI4-Stream\b|\bAXI4\b|\bSystemVerilog\b|\bFDA-HDL\b", re.I)
NUM = story.NUM


def _fill(where: str, text, vals: dict) -> str:
    text = str(text)
    bad = NUM.findall(PROSE_OK.sub(" ", re.sub(r"\{[\w|]+\}", " ", text)))
    bad = [b for b in bad if any(c.isdigit() for c in b)]
    if bad:
        raise ContractError(f"{where}: typed number(s) {bad}; use a {{name}} placeholder with a value expression")

    def one(m):
        k = m.group(1)
        if k not in vals:
            raise ContractError(f"{where}: no value named {k}")
        v = vals[k]
        return expertise.fmt(v) if not isinstance(v, str) else v
    out = re.sub(r"\{(\w+)\}", one, text)
    if re.search(r"[{}]", out):
        raise ContractError(f"{where}: malformed placeholder in {text!r}")
    return out


def _value(spec: dict):
    files = glob.glob(str(ROOT / spec["source"]))
    if not files:
        raise ContractError(f"no file {spec['source']}")
    expr = spec["expr"]
    if expr.startswith("str:"):
        m = re.search(expr[4:], Path(sorted(files)[0]).read_text(), re.M)
        if not m:
            raise ContractError(f"no match for {expr} in {spec['source']}")
        return m.group(1)
    return expertise.evaluate(expr, {"source": spec["source"]})


def _links(paths, where):
    out = []
    for p in paths or []:
        try:
            out.append(expertise.link(p))
        except AssertionError as e:
            raise ContractError(f"{where}: {e}")
    return out


def _json(rel: str):
    return json.loads((ROOT / rel).read_text())


def _derived(vals: dict) -> None:
    """Values computed from a record by a stated formula."""
    vals["s_seeds_txt"] = ", ".join(str(s) for s in vals["s_seeds"][:-1]) + f" and {vals['s_seeds'][-1]}"
    runs = _json("results/59a_axi_tx/board_run.json")["runs"]
    cmp_ = [r["sim_compare"] for r in runs if isinstance(r.get("sim_compare"), dict) and "digest" in r["sim_compare"]]
    # a run's board result equals its simulation when the digest, the transaction count and the cycle count are equal;
    # runs on the vendor block-RAM core (program bram_*) are compared by transactions and verdicts only, so they are left out
    own = [r["sim_compare"] for r in runs if not r["program"].startswith("bram")]
    vals["px_n"] = len(own)
    vals["px_vendor"] = len(runs) - len(own)
    vals["px_equal"] = sum(1 for c in own if c["digest"]["equal"] and c["n_txn"]["equal"] and c["cycles"]["equal"])
    if not _json("results/59a_axi_tx/board_run.json")["inside_roc"]:
        raise ContractError("the AXI board run was not inside the recommended operating conditions; the page text says it was")
    cx = _json("results/81_verification/counterexample.json")
    fl = cx["checker_flags"]
    # the step where the checker flags the early response, and the step after it, where it has gone silent while the response still waits
    vals["cex_flag_step"] = fl.index(1)
    vals["cex_silent_step"] = vals["cex_flag_step"] + 1
    if fl[vals["cex_silent_step"]] != 0 or cx["signals"]["bvalid"][vals["cex_silent_step"]] != 1 or any(cx["signals"]["wvalid"]):
        raise ContractError("the counterexample no longer matches the page's description of it")
    pf = _json("results/b30/hil_runs/b30_hil_audio_pinfault.hil.json")["checks"]
    inside = {k: v for k, v in pf.items() if v.get("path") != "audio"}
    vals["pf_checks"] = len(inside)
    vals["pf_inside"] = sum(1 for v in inside.values() if v["pass"])


def cdc_matrix() -> dict:
    t = _json("results/16_cdc_gate_2026_1/mutant_table.json")
    cols = [("report_cdc_alone_flags", "AMD report_cdc"), ("structure_flags", "Structural check"),
            ("sim_flags", "Injected simulation"), ("gate_flags", "The gate")]
    rows = [{"id": r["fixture"].upper(), "what": r["what"], "flags": [bool(r[k]) for k, _ in cols]} for r in t["rows"] if r["kind"] == "mutant"]
    return {"cols": [c for _, c in cols], "rows": rows,
            "totals": [sum(1 for r in rows if r["flags"][i]) for i in range(len(cols))],
            "false_alarms": sum(1 for r in t["rows"] if r["kind"] == "correct" and r["gate_flags"]),
            "correct": sum(1 for r in t["rows"] if r["kind"] == "correct")}


def axi_matrix(spec: list) -> dict:
    runs = {r["tag"]: r for r in _json("results/59a_axi_tx/board_run.json")["runs"] if r["repeat"] == 0}
    rows = []
    for s in spec:
        if s["tag"] not in runs:
            raise ContractError(f"axi_rows: no board run {s['tag']}")
        r = runs[s["tag"]]
        stream = r["stream_bug"] != "none"
        sink = r["sink"]
        rules = r["lite_rules"]["total"] + r["stream_rules"]["total"] > 0
        data = r["summary"]["sb_mism"] > 0 or sink["data_mism"] + sink["keep_mism"] + sink["last_mism"] > 0
        rows.append({"label": s["label"], "tag": s["tag"], "flags": [rules, data, None if stream else bool(r["amd_pc_asserted"])]})
    cols = ["Protocol rules (ours)", "Data checks (ours)", "AMD protocol checker"]
    return {"cols": cols, "rows": rows,
            "totals": [sum(1 for r in rows if r["flags"][i]) for i in range(3)],
            "n": len(rows)}


def formal_table() -> dict:
    rows = []
    a = _json("results/59a_axi_tx/formal.json")
    for k, name in (("axil", "AXI4-Lite protocol rules"), ("axis", "AXI4-Stream protocol rules")):
        s = a["units"][k]["summary"]
        rows.append({"block": name, "what": f"every rule quiet on legal traffic, each fires on its seeded violation, {s['mutants']} checker mutants",
                     "method": f"bounded, depth {a['depth']}", "status": "PASS" if s["proofs_pass"] == s["proofs"] and s["mutants_killed"] == s["mutants"] else "FAIL",
                     "seconds": None})
    b = _json("results/b58a/formal.json")
    for j in b["jobs"]:
        t = j["task"]
        m = j.get("method", "k-induction") if t == "prove" else f"{'bounded' if t == 'bmc' else 'cover'}, depth {j['depth']}"
        rows.append({"block": {"interlocks": "Trading interlocks", "mac_tx": "MAC transmit FSM", "mac_rx": "MAC receive FSM", "order_ctl": "Order control"}[j["job"]],
                     "what": "", "method": m, "status": j["status"], "seconds": j["seconds"]})
    n = _json("results/b63d/formal.json")
    for j in n["jobs"]:
        t = j["job"].split()[-1]
        m = {"bmc": "bounded", "cover": "cover", "prove": "k-induction"}[t]
        rows.append({"block": j["entry"], "what": j["what"], "method": m, "status": j["status"], "seconds": j["seconds"]})
    return {"rows": rows}


def closure(vals: dict) -> dict:
    g = _json("results/04f/t1_verif_gates.json")["stages"]["V3"]["checks"]
    cover = float(g["cover_properties_pct"]["value"])
    bins = 100.0 * vals["cov_bins_hit"] / vals["cov_bins_n"]
    rows = [("Functional bins", bins, vals["fl_bins"]), ("Cover properties", cover, vals["fl_cover"]),
            ("Line coverage", vals["cov_line"], vals["fl_line"]), ("Toggle coverage", vals["cov_toggle"], vals["fl_toggle"]),
            ("Mutation score, first run", vals["m_first"], vals["fl_mut"]), ("Mutation score, final", vals["m_final"], vals["fl_mut"])]
    return {"rows": [{"label": a, "value": round(b, 2), "floor": c} for a, b, c in rows]}


def pin_fault(spec: dict, vals: dict) -> dict:
    w, f = ROOT / spec["working"] / "build.yaml", ROOT / spec["faulty"] / "build.yaml"
    yw, yf = yaml.safe_load(w.read_text()), yaml.safe_load(f.read_text())
    if yw["sources"] != yf["sources"]:
        raise ContractError("pin_fault: the two designs do not share their sources")
    if yw["constraints"] == yf["constraints"]:
        raise ContractError("pin_fault: the constraint files should differ")
    rec = _json(spec["record"])["checks"][spec["audio_check"]]
    return {"steps": [
        {"name": "Simulation", "ok": True, "text": "same RTL and sources as the working design"},
        {"name": "Checks inside the FPGA", "ok": vals["pf_inside"] == vals["pf_checks"], "text": f"{vals['pf_inside']} of {vals['pf_checks']} pass"},
        {"name": "Measured at the audio jack", "ok": rec["pass"], "text": f"{expertise.fmt(rec['measured']['level_dbfs_rms'])} dBFS rms, distortion {expertise.fmt(rec['measured']['thd_percent'])} %"}]}


def unbounded() -> dict:
    u = _json("results/81_verification/unbounded.json")
    e = _json("results/81_verification/equivalence.json")
    c = _json("results/81_verification/counterexample.json")
    names = {"house_before_after_73": "House profile, before and after the interface-profile change",
             "house_vs_amd_compatible": "House profile against the amd_compatible profile",
             "house_vs_strict": "House profile against the strict profile"}
    return {"attempts": [{"block": a["block"], "method": a["method"], "status": a["status"], "seconds": a["seconds"]} for a in u["attempts"]],
            "equivalence": [{"case": names[x["case"]], "expected": "equivalent" if x["expected_equivalent"] else "different",
                             "result": "equivalent" if x["equivalent"] else "different", "ok": x["as_expected"], "seconds": x["seconds"]} for x in e["cases"]],
            "cex": {"rule": c["rule_name"], "signals": c["signals"], "flags": c["checker_flags"], "step": c["failing_step"], "cycles": c["cycles"]}}


def build() -> dict:
    y = yaml.safe_load((DIR / "verification.yaml").read_text())
    vals = {k: _value(v) for k, v in y["values"].items()}
    _derived(vals)
    axi = axi_matrix(y["axi_rows"])
    vals.update(ax_bugs=axi["n"], ax_rules=axi["totals"][0], ax_data=axi["totals"][1])
    F = lambda w, t: _fill(w, t, vals)
    stage_ids = [s["id"] for s in y["stages"]]
    tech_ids = [t["id"] for t in y["techniques"]]
    for m in y["map"]:
        if m["technique"] not in tech_ids:
            raise ContractError(f"map: no technique {m['technique']}")
        for c in m["cells"]:
            if c not in stage_ids:
                raise ContractError(f"map: no stage {c}")
    techs = []
    for t in y["techniques"]:
        w = f"technique {t['id']}"
        techs.append({"id": t["id"], "title": t["title"], **{k: F(f"{w} {k}", t[k]) for k in ("what", "catches", "cannot", "how", "evidence")},
                      "detail": [F(w + " detail", x) for x in t.get("detail", [])], "links": _links(t.get("links"), w)})
    texts = {k: F("text " + k, v) for k, v in y["text"].items()}
    content = {"text": texts, "techniques": techs, "stages": y["stages"], "map": y["map"], "values": vals,
               "cdc": cdc_matrix(), "axi": axi, "formal": formal_table(), "closure": closure(vals),
               "pin": pin_fault(y["pin_fault"], vals), "unb": unbounded()}
    return {"content": content, "check": {"values": vals, "cdc": content["cdc"], "axi": content["axi"], "formal": content["formal"],
                                          "closure": content["closure"], "pin": content["pin"], "unb": content["unb"]}}
