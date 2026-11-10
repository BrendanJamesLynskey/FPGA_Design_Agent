"""The common ipgen runner (brief 19). One pipeline for every adapter:

    spec -> design -> IP config -> create_ip + read-back -> xsim vs the Python golden -> OOC synth -> record

    python3 -m flow.ipgen.run <adapter> <spec.yaml> <outdir> [--stages design,create,sim,synth] [--part PART]

`outdir` receives the design data, `<adapter>_cfg.tcl`, the Vivado work directory `work/` (not meant to be committed)
and the JSON records: `design.json`, `readback.json`, `sim.json`, `ooc.json`. Vivado stages need a heavy slot held by the
caller (see harness.run_vivado).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import yaml

from . import harness

DEFAULT_PART = "xc7a100tcsg324-1"  # the Nexys A7-100T


def adapters():
    from .cic_adapter import CicAdapter
    from .fir_adapter import FirAdapter
    return {"fir": FirAdapter, "cic": CicAdapter}


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.ndarray,)):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(type(o))


def dump(path: Path, obj) -> None:
    Path(path).write_text(json.dumps(obj, indent=2, default=_json_default) + "\n")


def tcl_list(items) -> str:
    """A Tcl list of words, each braced (values contain no braces here)."""
    return " ".join("{" + str(i) + "}" for i in items)


def write_cfg(path: Path, *, part, workdir, module, create_args, props, tb_file="", tb_top="tb_axis_io",
              clock_port="aclk", clock_period_ns=10.0):
    lines = [
        f"set ipgen(part) {{{part}}}",
        f"set ipgen(workdir) {{{Path(workdir).resolve()}}}",
        f"set ipgen(module) {{{module}}}",
        f"set ipgen(create_args) {{{create_args}}}",
        f"set ipgen(props) [list {tcl_list(props)}]",
        f"set ipgen(tb_file) {{{Path(tb_file).resolve() if tb_file else ''}}}",
        f"set ipgen(tb_top) {{{tb_top}}}",
        f"set ipgen(clock_port) {{{clock_port}}}",
        f"set ipgen(clock_period_ns) {clock_period_ns}",
    ]
    Path(path).write_text("\n".join(lines) + "\n")


def read_readback(work: Path, module: str, keys) -> dict:
    """CONFIG.* values from readback_config.tsv, and generated model parameters from the .xci (names MODEL.<C_NAME>)."""
    out = {"config_all": {}, "model": {}}
    tsv = work / "readback_config.tsv"
    if tsv.exists():
        for ln in tsv.read_text().splitlines():
            k, _, v = ln.partition("\t")
            out["config_all"][k] = v
    xci = work / "ip" / module / f"{module}.xci"
    if xci.exists():
        j = json.loads(xci.read_text())

        def find(o):
            if isinstance(o, dict):
                if "model_parameters" in o:
                    return o["model_parameters"]
                for v in o.values():
                    r = find(v)
                    if r:
                        return r
            return None

        mp = find(j) or {}
        for k, v in mp.items():
            try:
                out["model"][k] = v[0]["value"]
            except Exception:
                pass
    out["selected"] = {}
    for k in keys:
        if k.startswith("MODEL."):
            out["selected"][k] = out["model"].get(k[6:])
        else:
            out["selected"][k] = out["config_all"].get(k)
    set_err = work / "set_errors.txt"
    out["set_errors"] = set_err.read_text().splitlines() if set_err.exists() else []
    return out


def port_widths(work: Path, module: str, in_port: str, out_port: str):
    vhd = (work / "ip" / module / "sim" / f"{module}.vhd").read_text()
    def w(name):
        m = re.search(rf"{name}\s*:\s*(?:IN|OUT)\s+STD_LOGIC_VECTOR\((\d+) DOWNTO 0\)", vhd, re.I)
        return int(m.group(1)) + 1
    return w(in_port), w(out_port)


def parse_ooc(work: Path) -> dict:
    out = {}
    u = work / "utilization.rpt"
    if u.exists():
        txt = u.read_text()
        def row(label):
            m = re.search(rf"^\|\s*{re.escape(label)}\s*\|\s*(\d+)", txt, re.M)
            return int(m.group(1)) if m else None
        out["luts"] = row("Slice LUTs") if row("Slice LUTs") is not None else row("CLB LUTs")
        out["registers"] = row("Slice Registers") if row("Slice Registers") is not None else row("CLB Registers")
        out["dsp"] = row("DSPs")
        out["bram_tiles"] = row("Block RAM Tile")
        out["lutram"] = row("LUT as Memory")
    t = work / "timing_summary.rpt"
    if t.exists():
        m = re.search(r"WNS\(ns\)\s+TNS\(ns\).*?\n\s*-+.*?\n\s*(-?\d+\.\d+)", t.read_text(), re.S)
        if m:
            out["wns_ns"] = float(m.group(1))
    return out


def run(adapter_name: str, spec_path: Path, outdir: Path, stages=("design", "create", "sim", "synth"),
        part=DEFAULT_PART, mem_max="6G") -> dict:
    ad = adapters()[adapter_name]()
    spec = yaml.safe_load(Path(spec_path).read_text())
    outdir = Path(outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    work = outdir / "work"
    module = f"{ad.name}_ip"
    period_ns = 1e9 / spec["clock_hz"]
    record = {"adapter": adapter_name, "part": part, "stages": list(stages)}

    design = ad.design(spec)
    dump(outdir / "design.json", {"spec": spec, "design": design["summary"]})
    art = ad.design_artifacts(spec, design, outdir)
    props = ad.props(spec, design, art)
    record["design"] = design["summary"]
    record["predicted"] = ad.predicted(spec, design)

    cfg = outdir / f"{ad.name}_cfg.tcl"
    tb = work / "tb_axis_io.sv"
    vivado_stages = [s for s in stages if s in ("create", "sim", "synth")]

    if "create" in stages:
        work.mkdir(parents=True, exist_ok=True)
        write_cfg(cfg, part=part, workdir=work, module=module, create_args=ad.create_args, props=props, tb_file=tb,
                  clock_port=ad.clock_port, clock_period_ns=period_ns)
        # the testbench file must exist when the project is made only for sim; create does not need it
        r = harness.run_vivado(harness.HERE / "tcl" / "ip_flow.tcl", [str(cfg), "create"], work, "create.log", mem_max)
        record["create_rc"] = r.returncode
        if r.returncode or not (work / "create.done").exists():
            record["create_errors"] = harness.log_errors(work / "create.log")[:10]
            dump(outdir / "readback.json", record)
            raise SystemExit("create stage failed: " + "; ".join(record["create_errors"]))
    if (work / "ip").exists():
        rb = read_readback(work, module, ad.readback_keys())
        here = str(outdir.resolve())  # keep absolute paths out of the committed records
        rb["config_all"] = {k: v.replace(here, "<outdir>") for k, v in rb["config_all"].items()}
        rb["selected"] = {k: (v.replace(here, "<outdir>") if isinstance(v, str) else v) for k, v in rb["selected"].items()}
        rb["predicted"] = record["predicted"]
        dump(outdir / "readback.json", rb)
        record["readback"] = rb["selected"]
        record["set_errors"] = rb["set_errors"]
        record["readback_all_config"] = rb["config_all"]

    if "sim" in stages:
        in_w_port, out_w_port = port_widths(work, module, getattr(ad, "in_port", "s_axis_data_tdata"),
                                            getattr(ad, "out_port", "m_axis_data_tdata"))
        samples, sample_bits = ad.stimulus(spec, design)
        out_logical = int(record["readback"].get("CONFIG.Output_Width") or record["readback"].get("CONFIG.Output_Data_Width") or out_w_port)
        stim = work / "stim.txt"
        harness.write_stimulus(stim, samples, sample_bits)
        ports = {"m_tready": bool(spec.get("back_pressure", True)) and ad.name == "fir"}
        sims = {}
        for kind, seed in (("continuous", 0), ("random", spec.get("seed", 1))):
            sched = work / f"sched_{kind}.txt"
            harness.write_schedule(sched, harness.schedule(kind, 4096, seed))
            resp = work / f"resp_{kind}.txt"
            harness.render_tb(tb, dut_inst=ad.dut_inst(module, ports), in_w=in_w_port, out_w=out_w_port, n_in=len(samples),
                              stim=stim, sched=sched, resp=resp, n_sched=4096, out_bp=ports["m_tready"], period_ns=period_ns)
            write_cfg(cfg, part=part, workdir=work, module=module, create_args=ad.create_args, props=props, tb_file=tb,
                      clock_port=ad.clock_port, clock_period_ns=period_ns)
            if (work / "sim.done").exists():
                (work / "sim.done").unlink()
            r = harness.run_vivado(harness.HERE / "tcl" / "ip_flow.tcl", [str(cfg), "sim"], work, f"sim_{kind}.log", mem_max)
            if r.returncode or not (work / "sim.done").exists() or not resp.exists():
                sims[kind] = {"match": False, "error": harness.log_errors(work / f"sim_{kind}.log")[:10] or ["sim failed"]}
                continue
            rr = harness.read_response(resp, out_logical)
            res = ad.check(spec, design, samples, rr, out_logical)
            res["schedule"] = kind
            res["output_width_logical"] = out_logical
            res["tdata_width_in"] = in_w_port
            res["tdata_width_out"] = out_w_port
            res["total_cycles"] = (rr["meta"].get("cycles", 0))
            sims[kind] = res
        record["sim"] = sims
        # the two schedules must give the same outputs: same sequence regardless of gaps
        try:
            a = harness.read_response(work / "resp_continuous.txt", out_logical)["data"]
            b = harness.read_response(work / "resp_random.txt", out_logical)["data"]
            record["sim_schedules_agree"] = (a == b)
        except Exception:
            record["sim_schedules_agree"] = None
        dump(outdir / "sim.json", {"sim": sims, "schedules_agree": record.get("sim_schedules_agree"),
                                   "n_stimulus": len(samples)})
        # keep the response of the random run (the harder one) next to the results, compressed to the data column
        np.savetxt(outdir / "xsim_output.txt", np.array(harness.read_response(work / "resp_random.txt", out_logical)["data"], dtype=np.int64), fmt="%d")
        np.savetxt(outdir / "stimulus.txt", np.asarray(samples, dtype=np.int64), fmt="%d")

    if "synth" in stages:
        write_cfg(cfg, part=part, workdir=work, module=module, create_args=ad.create_args, props=props, tb_file=tb,
                  clock_port=ad.clock_port, clock_period_ns=period_ns)
        if (work / "synth.done").exists():
            (work / "synth.done").unlink()
        r = harness.run_vivado(harness.HERE / "tcl" / "ip_flow.tcl", [str(cfg), "synth"], work, "synth.log", mem_max)
        if r.returncode or not (work / "synth.done").exists():
            record["synth_errors"] = harness.log_errors(work / "synth.log")[:10]
        else:
            ooc = parse_ooc(work)
            ooc["clock_period_ns"] = period_ns
            if ooc.get("wns_ns") is not None:
                ooc["fmax_est_mhz"] = round(1000.0 / (period_ns - ooc["wns_ns"]), 1)
            ooc["note"] = "post-synthesis, out-of-context, no routing delays: Fmax is an upper bound"
            record["ooc"] = ooc
            dump(outdir / "ooc.json", ooc)
    return record


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("adapter")
    ap.add_argument("spec")
    ap.add_argument("outdir")
    ap.add_argument("--stages", default="design,create,sim,synth")
    ap.add_argument("--part", default=DEFAULT_PART)
    a = ap.parse_args(argv)
    rec = run(a.adapter, Path(a.spec), Path(a.outdir), tuple(a.stages.split(",")), a.part)
    keep = {k: v for k, v in rec.items() if k != "readback_all_config"}
    print(json.dumps(keep, indent=2, default=_json_default))
    ok = all(s.get("match") for s in rec.get("sim", {}).values()) if "sim" in rec else True
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
