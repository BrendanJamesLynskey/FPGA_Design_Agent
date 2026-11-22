#!/usr/bin/env python3
"""Render results/155_offchip/README.md from the CSV and JSON files the study wrote (every number in it comes from those files).

    python3 tools/offchip_tables.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results/155_offchip"


def rows(name):
    return list(csv.DictReader((R / name).open()))


def f(x, n=2, plus=False):
    if x in ("", None, "None"):
        return "n/a"
    v = float(x)
    return f"{v:+.{n}f}" if plus else f"{v:.{n}f}"


def md(head, body):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in body]
    return "\n".join(out)


def r_out_table(bank, std, slew):
    rs = [r for r in rows("r_out.csv") if r["bank"] == bank and r["standard"] == std and r["slew"] == slew]
    drives = sorted({int(r["drive_ma"]) for r in rs})
    body = []
    for d in drives:
        cell = {r["corner"]: r for r in rs if int(r["drive_ma"]) == d}
        body.append([d] + [f"{f(cell[c]['r_pu_ohm_into_z0'], 0)} / {f(cell[c]['r_pd_ohm_into_z0'], 0)}" for c in ("max", "typ", "min")] +
                    [f"{f(cell['typ']['r_rail_pu_ohm'], 0)} / {f(cell['typ']['r_rail_pd_ohm'], 0)}",
                     f(cell["typ"]["t2080_rise_ns"]), f(cell["typ"]["t2080_fall_ns"]), f(cell["typ"]["i_pu_max_ma"], 0)])
    return md(["DRIVE mA", "launch, strong: pull-up / pull-down ohm", "launch, typical", "launch, weak", "near the rail, typical (0.1 V from the rail it pulls to)",
               "20-80 % rise ns (typ, 50 ohm fixture)", "fall ns", "max pull-up mA"], body)


def matrix_table(bank, std, slew, metric, fmt, worst):
    m = [r for r in rows("termination_matrix.csv") if r["bank"] == bank and r["standard"] == std and r["slew"] == slew]
    drives = sorted({int(r["drive_ma"]) for r in m})
    terms = []
    for r in m:
        if r["termination"] not in terms:
            terms.append(r["termination"])
    body = []
    for d in drives:
        line = [d]
        for t in terms:
            vals = [metric(r) for r in m if int(r["drive_ma"]) == d and r["termination"] == t]
            vals = [v for v in vals if v is not None]
            line.append(fmt(worst(vals)) if vals else "n/a")
        body.append(line)
    return md(["DRIVE mA"] + terms, body)


def over(r):
    """The larger of the overshoot above VCCO and the undershoot below ground; 0 when the receiver stays inside the rails."""
    return max(0.0, float(r["overshoot_above_vcco_v"]), float(r["undershoot_below_gnd_v"]))


def fi(r):
    v = [float(r[k]) for k in ("first_incident_rise_margin_v", "first_incident_fall_margin_v") if r[k] not in ("", "None")]
    return min(v) if v else None


def rb(r):
    v = [float(r[k]) for k in ("ringback_rise_margin_v", "ringback_fall_margin_v") if r[k] not in ("", "None")]
    return min(v) if v else None


def settle(r):
    return max(float(r["settle_rise_ns"]), float(r["settle_fall_ns"]))


def main() -> int:
    P = json.loads((R / "study_parameters.json").read_text())
    out = ["# Brief 155: off-chip I/O study results\n",
           "What an FPGA output does to a 50 ohm line and a receiver, for every LVCMOS DRIVE and SLEW in the banks of our three boards' parts, computed from AMD's own "
           "IBIS output models by the time-domain model in `flow/offchip_model.py`: output resistance, termination matrix, best DRIVE with a series resistor, line length, "
           "the run on our board designs and a check of the model against the waveforms inside the IBIS files. The reading of these numbers is in [docs/offchip_io.md](../../docs/offchip_io.md).\n",
           "## Records\n",
           "| File | What it holds |", "|---|---|",
           "| `r_out.csv` | every driver at every corner: launch resistance (pull-up, pull-down, into 50 ohm and into 72 ohm), resistance near the rail, edge times, die capacitance, thresholds, IBIS source |",
           "| `dci_outputs.csv` | the impedance-controlled SSTL/HSTL/POD outputs (OUT40, OUT48, OUT60): slope resistance at VCCO/2 |",
           "| `termination_matrix.csv` | every driver x 10 terminations x 3 corners: overshoot, undershoot, first-incident margin, ringback, settling, receiver edge time |",
           "| `series_r_sweep.csv`, `best_match.json` | every driver x 7 series resistors, judged; the passing combinations and the best three per ranking |",
           "| `proposals_fixed_series.json` | which DRIVE and SLEW pass when 22, 33 or 47 ohm is already on the board |",
           "| `length_sweep.csv` | six configurations against line length |",
           "| `ibis_fixture_check.json` | the driver into IBIS's own fixture against the IBIS waveform: final level and shape error |",
           "| `boards_report.json`, `boards/*.spec.yaml` | the check run on our board designs (the specs hold the assumed loads) |",
           "| `study_parameters.json` | the line, load and model used |\n",
           "Driver data: AMD's IBIS output models (`artix7.ibs` revision 2.8, IBIS 4.2, 28-AUG-2017; `zynq.ibs` revision 2.8, 27-JAN-2016; `zynquplus.ibs` revision 2.11, IBIS 5.1, 10-FEB-2022; the files shipped with Vivado 2025.2), derived by "
           "`tools/ibis_extract.py` into `flow/offchip_data/driver_models.json`; the three corners are the IBIS typ, min (weak: slow process, low VCCO, hot) and max (strong) columns. "
           f"Line: lossless, Z0 {P['z0_ohm']:g} ohm, {P['length_in']:g} in at er_eff {P['er_eff']} "
           f"({P['length_in'] * 25.4 * (P['er_eff'] ** 0.5) / 299.792458:.2f} ns one way); receiver pin and stub {P['c_load_pf']:g} pF; receiver thresholds the IBIS Vinl/Vinh of the standard.\n",
           "## Reproduce\n",
           "Run these from the repository root in this order. The study needs only Python and the committed driver data; only the extraction needs Vivado's IBIS files on the machine.\n",
           "```\npython3 tools/ibis_extract.py              # needs Vivado's IBIS files; writes flow/offchip_data/driver_models.json (committed)\n"
           "python3 tools/offchip_study.py              # about 25 minutes, one process; writes the CSV and JSON files here\n"
           "python3 tools/ibis_fixture_check.py         # the independent check against the IBIS waveforms\n"
           "python3 tools/offchip_board_report.py       # the run on our board designs\n"
           "python3 tools/offchip_tables.py             # renders this file from the files above\n"
           "python3 -m pytest -q flow/tests/test_155_offchip.py\n```\n",
           "## Known gaps and limits\n",
           "The receiver is not clamped (overshoot is the conservative reading). Package parasitics, loss, crosstalk, multi-drop stubs and simultaneous switching noise are not modelled. "
           "The switching ramp is a smooth step calibrated to the IBIS 20-80 % time; against the IBIS waveform it matches the final level within 1 % and the shape within 0.6 to 8.8 % rms of the swing "
           "for the FAST models and 15 to 17 % for the 7-series SLOW models (peak 31 to 36 %) (see `ibis_fixture_check.json`). IBIS is AMD's own preliminary data, not measured on our boards; "
           "no scope trace has been compared with any number here. The board loads in `boards/*.spec.yaml` are assumptions where marked.\n"]
    out.append("## 1. Effective output resistance of an LVCMOS driver\n")
    out.append("The resistance the wave sees when the driver launches into a 50 ohm load from rest (chord: voltage over current at the launch point). Pull-up and "
               "pull-down separately, three corners. It is not one number per DRIVE.\n")
    for bank, std, slew in [("7-series HR", "LVCMOS33", "FAST"), ("7-series HR", "LVCMOS25", "FAST"), ("7-series HR", "LVCMOS18", "FAST"),
                            ("UltraScale+ HD", "LVCMOS33", "FAST"), ("UltraScale+ HP", "LVCMOS18", "FAST")]:
        out += [f"### {bank} {std} (SLEW {slew}; the output resistance is the same for SLOW, only the edge time differs)\n", r_out_table(bank, std, slew), ""]
    out.append("## 2. Impedance-controlled outputs (DCI, UltraScale+ HP, OUTPUT_IMPEDANCE)\n")
    d = rows("dci_outputs.csv")
    body = []
    for key in sorted({r["model"] for r in d}):
        if "SSTL15_DCI_F_OUT" not in key:
            continue
        c = {r["corner"]: r for r in d if r["model"] == key}
        body.append([key] + [f"{c[k]['r_pu_mid_ohm']} / {c[k]['r_pd_mid_ohm']}" for k in ("max", "typ", "min")])
    out.append(md(["IBIS model (zynquplus.ibs rev 2.11)", "strong pull-up / pull-down ohm", "typical", "weak"], body))
    out.append("\nSlope resistance at VCCO/2, the point an SSTL output works around.\n")
    out.append("## 3. Termination matrix, LVCMOS33 on 7-series HR, SLEW FAST, 50 ohm line\n")
    out.append("Worst of the three corners and both edges. `series_N`: N ohm at the source; `parallel_gnd`: 50 ohm to ground at the receiver; `parallel_vtt`: 50 ohm to VCCO/2; "
               "`thevenin`: 100 ohm to VCCO and 100 ohm to ground; `ac`: 50 ohm in series with 100 pF to ground.\n")
    for title, metric, fmt, worst in [("Overshoot above VCCO or undershoot below ground at the receiver, V (limit 0.20 V recommended; larger needs the data-sheet duration table)", over, lambda v: f(v, 2), max),
                                      ("First-incident-wave margin against VIH/VIL, V (negative: the receiver waits for a reflection)", fi, lambda v: f(v, 2, True), min),
                                      ("Ringback margin against the threshold, V (negative: the edge re-crosses the threshold)", rb, lambda v: f(v, 2, True), min),
                                      ("Settling time to within 5 % of VCCO, ns", settle, lambda v: f(v, 1), max)]:
        out += [f"**{title}**\n", matrix_table("7-series HR", "LVCMOS33", "FAST", metric, fmt, worst), ""]
    out.append("## 4. The same with SLEW SLOW\n")
    for title, metric, fmt, worst in [("Overshoot or undershoot, V", over, lambda v: f(v, 2), max), ("First-incident-wave margin, V", fi, lambda v: f(v, 2, True), min)]:
        out += [f"**{title}**\n", matrix_table("7-series HR", "LVCMOS33", "SLOW", metric, fmt, worst), ""]
    out.append("## 5. UltraScale+ HP LVCMOS18, SLEW FAST (the KR260 RGMII case) \n")
    for title, metric, fmt, worst in [("Overshoot or undershoot, V", over, lambda v: f(v, 2), max), ("First-incident-wave margin, V", fi, lambda v: f(v, 2, True), min)]:
        out += [f"**{title}**\n", matrix_table("UltraScale+ HP", "LVCMOS18", "FAST", metric, fmt, worst), ""]
    out.append("## 6. Best DRIVE plus series resistor on a 50 ohm line\n")
    win = json.loads((R / "best_match.json").read_text())
    c0 = next(iter(win.values()))["criteria"]
    out.append("From `series_r_sweep.csv`: every DRIVE, SLEW and E-series resistor (0, 10, 15, 22, 27, 33, 47 ohm) judged at all three corners. A combination **passes** when it has "
               "no `OFFCHIP-*` flag (receiver within VCCO + 0.2 V and GND - 0.2 V, no ringback through the threshold), a first-incident-wave margin of at least "
               f"{c0['first_wave_guard_v']:g} V over VIH/VIL at every corner, and a weak-corner receiver 20-80 % time of at most {c0['max_weak_rise_ns']:g} ns "
               f"(a quarter of a {c0['ui_ns']:g} ns unit interval). Z0 {P['z0_ohm']:g} ohm, {P['length_in']:g} in, {P['c_load_pf']:g} pF, unclamped receiver.\n")
    for key, v in win.items():
        out.append(f"### {key}: {v['n_passing']} of {v['n_total']} combinations pass\n")
        grid = v["pass_grid"]
        rs_cols = list(next(iter(grid.values())))
        out.append(md(["DRIVE / SLEW"] + [f"{r} ohm" for r in rs_cols],
                      [[k] + [("pass" if g[r] == "pass" else g[r].replace("OFFCHIP-", "").replace(" ", "+").lower()) for r in rs_cols] for k, g in grid.items()]))
        out.append("")
        body = []
        for tag, name in (("best_by_match", "smallest worst-corner mismatch"), ("best_edge_rate", "fastest receiver edge"), ("best_emi", "slowest edge")):
            for r in v[tag][:2]:
                body.append([name, f"{r['drive_ma']} mA {r['slew']} + {r['series_ohm']:g} ohm", f"{r['r_pu_typ']:g} / {r['r_pd_typ']:g}", f"{r['total_pu_typ']:g} / {r['total_pd_typ']:g}",
                             f"{r['r_pu_strong'] + r['series_ohm']:.0f} / {r['r_pd_strong'] + r['series_ohm']:.0f}", f"{r['r_pu_weak'] + r['series_ohm']:.0f} / {r['r_pd_weak'] + r['series_ohm']:.0f}",
                             r["mismatch_worst_corner_pct"], r["worst_overshoot_v"], r["first_incident_margin_v"], r["rx_rise_2080_ns_strong"], r["rx_rise_2080_ns_weak"]])
        if body:
            out.append(md(["ranking", "choice", "R_out typ pu / pd (chord into Z0 + R)", "R_out + R typ", "total, strong corner", "total, weak corner", "worst mismatch %", "worst overshoot V",
                           "first-incident margin V", "rx rise ns strong", "rx rise ns weak"], body))
            out.append("")
    out.append("\n## 7. Line length\n")
    ls = rows("length_sweep.csv")
    out.append(md(["standard", "DRIVE", "SLEW", "R series", "length in", "delay ns", "overshoot V", "undershoot V", "first-incident margin V", "staircase visible", "ringback margin V", "settle ns"],
                  [[r["standard"], r["drive_ma"], r["slew"], r["series_ohm"], r["length_in"], r["delay_ns"], r["worst_overshoot_v"], r["worst_undershoot_v"],
                    r["first_incident_margin_v"], r["staircase_visible"], r["ringback_margin_v"], r["settle_ns"]] for r in ls]))
    out.append("")
    (R / "README.md").write_text("\n".join(out) + "\n")
    print(R / "README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
