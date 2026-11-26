#!/usr/bin/env python3
"""Brief 164: the waveform samples and the two-answers-per-port table that the signal-integrity page plots.

    python3 tools/si_expertise_data.py [--out results/164_si_expertise]     # about 5 minutes, one process, no Vivado

Uses brief 155's solver (flow/offchip_model.py) and the check's two-answer proposal (flow/offchip_check.py, decision 30). Writes:

    waveforms_series_r.csv   the receiver voltage of one 50 ohm, 6 in, 5 pF line, rising then falling edge, series R 0 / 22 / 33 / 47 ohm,
                             for LVCMOS33 (7-series HR) and LVCMOS18 (UltraScale+ HP), DRIVE 12 FAST, strong IBIS corner (the worst overshoot)
    kr260_two_answers.json   per KR260 port (A, B) and per assumption (4 in assumed by brief 155; the carrier's measured length from brief 162):
                             the XDC setting, the best setting for the board as built, the optimal setting if the resistor can change, each with its
                             peaks, the time beyond the 0.2 V limit and the verdict; plus the receiver waveform of each
    kr260_waveforms.csv      those waveforms

Every row comes from the model on AMD's IBIS data (model, not a scope); the files name the IBIS file and revision.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "flow"))
import offchip_check as C       # noqa: E402
import offchip_model as M       # noqa: E402

SERIES = (0, 22, 33, 47)
PANELS = [("LVCMOS33 in a 7-series HR bank", "7series", "HR", "LVCMOS33"),
          ("LVCMOS18 in an UltraScale+ HP bank", "ultrascale_plus", "HP", "LVCMOS18")]
LENGTH_IN, C_PF, Z0, DRIVE, SLEW, CORNER = 6.0, 5.0, 50.0, 12, "FAST", "max"
STEP_NS = 0.1          # waveform samples are kept every 0.1 ns (the solver steps are 10 to 20 ps)
SPAN_NS = 12.0         # per edge; each edge is simulated from a settled state and drawn side by side


def _driver(fc: str, bt: str, std: str, drive: int, slew: str, corner: str) -> M.Driver:
    mf = C.model_family(fc, bt)
    key = M.model_key(mf, std, drive, slew, bt if mf != "artix7" else "")
    return M.get_driver(key, corner), key


def _wave(fc, bt, std, drive, slew, rs, length, c_pf, corner, edge, z0=Z0):
    drv, key = _driver(fc, bt, std, drive, slew, corner)
    res = M.simulate(drv, M.Line(z0, length, 3.2), M.Load(c_pf=c_pf), rs, edge)
    out, last = [], -1e9
    for t, v in zip(res.t, res.v_rx):
        tn = t * 1e9
        if -0.5 <= tn <= SPAN_NS and tn - last >= STEP_NS - 1e-9:
            out.append((round(tn, 2), round(v, 4)))
            last = tn
    return out, drv, key


def series_r_waveforms(out: Path) -> None:
    rows = []
    for label, fc, bt, std in PANELS:
        lim = C.rx_limits(fc, bt)
        for rs in SERIES:
            for edge in ("r", "f"):
                w, drv, key = _wave(fc, bt, std, DRIVE, SLEW, float(rs), LENGTH_IN, C_PF, CORNER, edge)
                src = M.source_for(key)
                for t, v in w:
                    rows.append([label, std, bt, DRIVE, SLEW, LENGTH_IN, C_PF, Z0, CORNER, rs, "rise" if edge == "r" else "fall", t, v, drv.vcc,
                                 round(drv.vcc + lim["roc_over"], 3), -lim["roc_under"], drv.vinh, drv.vinl, key, src["file"], src["file_rev"]])
    with (out / "waveforms_series_r.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["panel", "standard", "bank", "drive_ma", "slew", "length_in", "c_pf", "z0_ohm", "corner", "series_ohm", "edge", "t_ns", "v_rx_v",
                    "vcco_v", "limit_over_v", "limit_under_v", "vih_v", "vil_v", "model", "ibis_file", "file_rev"])
        w.writerows(rows)


def _metrics(fc, bt, std, drive, slew, rs, length, c_pf, z0, ui, ext):
    mf = C.model_family(fc, bt)
    ev = C.evaluate_cached(mf, bt, std, drive, slew, rs, "none", z0, length, c_pf, 3.2, tuple(sorted(ext.items())), None, None)
    lim = C.rx_limits(fc, bt)
    flags = C.judge(ev, lim, not ev["lumped"], ui)
    return {"drive": drive, "slew": slew, "series_ohm": rs, "worst_over_v": round(ev["worst_over_vcco_v"], 3),
            "worst_under_v": round(ev["worst_under_gnd_v"], 3), "t_over_ns": round(ev["t_over_roc_ns"], 2), "t_under_ns": round(ev["t_under_roc_ns"], 2),
            "ui_ns": ui, "flags": sorted({f[0] for f in flags}), "meets_overshoot_limit": max(ev["worst_over_vcco_v"], ev["worst_under_gnd_v"]) <= lim["roc_over"],
            "first_incident_margin_v": round(ev["min_first_incident_margin_always_v"], 3), "rx_rise_2080_ns_weak": round(ev["rx_rise_2080_ns"]["min"], 2),
            "source": ev["source"]}


def kr260(out: Path) -> None:
    fc, bt = "ultrascale_plus", "HP"
    specs = {"assumed": ROOT / "results/155_offchip/boards/kr260_b58a_trigger.spec.yaml",
             "measured": ROOT / "results/162_kr260_si/kr260_b58a_trigger_carrier_data.spec.yaml"}
    xdc = C.parse_xdc((ROOT / "designs/b58a_trigger/design.xdc").read_text())
    result: dict = {"note": "Model results on AMD's preliminary IBIS data (not a scope measurement). Strong IBIS corner for the waveforms (the worst overshoot).",
                    "xdc_setting": {"standard": "LVCMOS18", "drive": 12, "slew": "FAST", "series_ohm": 0},
                    "limit_v": 0.2, "ports": []}
    assert xdc["a_txd[0]"]["DRIVE"] == "12" and xdc["a_txd[0]"]["SLEW"].upper() == "FAST", xdc["a_txd[0]"]
    wave_rows = []
    for assumption, sp in specs.items():
        spec = yaml.safe_load(sp.read_text())
        assert C.family_class(spec["family"], spec["part"]) == fc
        for g in spec["off_chip"]:
            if g["name"] not in ("rgmii_a_tx", "rgmii_b_tx"):
                continue
            t = C.propose_two(g, fc, bt)
            ui = float(g["ui_ns"])
            ln, cpf = float(g["line"]["length_in"]), float(g["load"]["c_pf"])
            asb = t["as_built"]["best"] or t["as_built"]["least_bad"]
            opt = t["optimal"]["best"] or t["optimal"]["least_bad"]
            answers = {"xdc": _metrics(fc, bt, "LVCMOS18", 12, "FAST", 0.0, ln, cpf, 50.0, ui, {}),
                       "as_built": _metrics(fc, bt, "LVCMOS18", asb["drive"], asb["slew"], asb["rs_ohm"], ln, cpf, 50.0, ui, {}),
                       "optimal": _metrics(fc, bt, "LVCMOS18", opt["drive"], opt["slew"], opt["rs_ohm"], ln, cpf, 50.0, ui, {})}
            for a in answers.values():
                a["max_rise_ns"] = float(g.get("max_rise_ns", C.RISE_FRACTION_OF_UI * ui))        # the house assumption: a quarter of the unit interval
            answers["as_built"]["all_limits_met"] = bool(t["as_built"]["best"])
            answers["as_built"]["fails"] = [] if t["as_built"]["best"] else t["as_built"]["least_bad"]["fails"]
            answers["optimal"]["all_limits_met"] = bool(t["optimal"]["best"])
            answers["optimal"]["passing_combinations"] = len(t["optimal"]["all_passing"])
            answers["as_built"]["passing_combinations"] = len(t["as_built"]["all_passing"])
            for which, a in answers.items():
                w, drv, key = _wave(fc, bt, "LVCMOS18", a["drive"], a["slew"], float(a["series_ohm"]), ln, cpf, CORNER, "r")
                wf, _, _ = _wave(fc, bt, "LVCMOS18", a["drive"], a["slew"], float(a["series_ohm"]), ln, cpf, CORNER, "f")
                src = M.source_for(key)
                for edge, ww in (("rise", w), ("fall", wf)):
                    for tt, v in ww:
                        wave_rows.append([assumption, g["name"], which, a["drive"], a["slew"], a["series_ohm"], ln, cpf, edge, tt, v, drv.vcc, key, src["file_rev"]])
            result["ports"].append({"assumption": assumption, "group": g["name"], "port": "A" if g["name"].startswith("rgmii_a") else "B",
                                    "length_in": ln, "c_pf": cpf, "ui_ns": ui, "board_series_ohm": t["board_series_ohm"], "answers": answers,
                                    "dci": t["dci"]})
    (out / "kr260_two_answers.json").write_text(json.dumps(result, indent=1) + "\n")
    with (out / "kr260_waveforms.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["assumption", "group", "answer", "drive_ma", "slew", "series_ohm", "length_in", "c_pf", "edge", "t_ns", "v_rx_v", "vcco_v", "model", "file_rev"])
        w.writerows(wave_rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results/164_si_expertise"))
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    series_r_waveforms(out)
    kr260(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
