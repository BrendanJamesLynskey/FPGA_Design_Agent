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
    from .bmg_adapter import BmgAdapter
    from .cic_adapter import CicAdapter
    from .dds_adapter import DdsAdapter
    from .fir_adapter import FirAdapter
    return {"fir": FirAdapter, "cic": CicAdapter, "bmg": BmgAdapter, "dds": DdsAdapter}


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
            m = re.search(rf"^\|\s*{re.escape(label)}\*?\s*\|\s*([\d.]+)", txt, re.M)
            if not m:
                return None
            return float(m.group(1)) if "." in m.group(1) else int(m.group(1))
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

    if "sim" in stages and getattr(ad, "sim_kind", "axis") == "mem":
        record["sim"] = run_mem_sim(ad, spec, design, work, module, cfg, tb, props, part, period_ns, mem_max, outdir)
    elif "sim" in stages:
        port_info = {}
        if getattr(ad, "source_only", False):  # a core with no input channel (a DDS): the output words are all bits
            port_info = ad.parse_ports((work / "ip" / module / "sim" / f"{module}.vhd").read_text())
            in_w_port, out_w_port = 8, port_info["phase_tdata_bits"] + port_info["data_tdata_bits"]
            out_logical = out_w_port
        else:
            in_w_port, out_w_port = port_widths(work, module, getattr(ad, "in_port", "s_axis_data_tdata"),
                                                getattr(ad, "out_port", "m_axis_data_tdata"))
            out_logical = int(record["readback"].get("CONFIG.Output_Width") or record["readback"].get("CONFIG.Output_Data_Width") or out_w_port)
        samples, sample_bits = ad.stimulus(spec, design)
        stim = work / "stim.txt"
        harness.write_stimulus(stim, samples, sample_bits)
        ports = {"m_tready": bool(spec.get("back_pressure", True)) and ad.name == "fir", **port_info}
        sims = {}
        for kind, seed in getattr(ad, "schedules", (("continuous", 0), ("random", spec.get("seed", 1)))):
            sched = work / f"sched_{kind}.txt"
            harness.write_schedule(sched, harness.schedule(kind, 4096, seed))
            resp = work / f"resp_{kind}.txt"
            harness.render_tb(tb, dut_inst=ad.dut_inst(module, ports), in_w=in_w_port, out_w=out_w_port, n_in=len(samples),
                              stim=stim, sched=sched, resp=resp, n_sched=4096, out_bp=ports["m_tready"], period_ns=period_ns,
                              drain_cycles=ad.drain_cycles(spec) if hasattr(ad, "drain_cycles") else 3000)
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
        kinds = [k for k in sims if "error" not in sims[k]]
        try:
            if len(kinds) > 1:
                a = harness.read_response(work / f"resp_{kinds[0]}.txt", out_logical)["data"]
                b = harness.read_response(work / f"resp_{kinds[-1]}.txt", out_logical)["data"]
                record["sim_schedules_agree"] = (a == b)
            else:
                record["sim_schedules_agree"] = None
        except Exception:
            record["sim_schedules_agree"] = None
        dump(outdir / "sim.json", {"sim": sims, "schedules_agree": record.get("sim_schedules_agree"),
                                   "n_stimulus": len(samples)})
        # keep the response of the last (the harder: random-gap) run next to the results, data column only
        last = work / f"resp_{(kinds or ['continuous'])[-1]}.txt"
        words = harness.read_response(last, out_logical)["data"]
        if out_logical > 63:  # wide words (a DDS's phase + sine + cosine): hexadecimal
            (outdir / "xsim_output.hex").write_text("".join(f"{int(v) & ((1 << out_logical) - 1):x}\n" for v in words))
        else:
            np.savetxt(outdir / "xsim_output.txt", np.array(words, dtype=np.int64), fmt="%d")
            np.savetxt(outdir / "stimulus.txt", np.asarray(samples, dtype=np.int64), fmt="%d")

    if "synth" in stages:
        write_cfg(cfg, part=part, workdir=work, module=module, create_args=ad.create_args, props=props, tb_file=tb,
                  clock_port=ad.clock_port, clock_period_ns=period_ns)
        if (work / "synth.done").exists():
            (work / "synth.done").unlink()
        r = harness.run_vivado(harness.HERE / "tcl" / "ip_flow.tcl", [str(cfg), "synth"], work, "synth.log", mem_max)
        if r.returncode or not (work / "synth.done").exists():
            record["synth_errors"] = harness.log_errors(work / "synth.log")[:10]
    if "synth" in stages or "parse" in stages:
        if (work / "utilization.rpt").exists():
            ooc = parse_ooc(work)
            ooc["clock_period_ns"] = period_ns
            if ooc.get("wns_ns") is not None:
                ooc["fmax_est_mhz"] = round(1000.0 / (period_ns - ooc["wns_ns"]), 1)
            ooc["note"] = "post-synthesis, out-of-context, no routing delays: Fmax is an upper bound"
            record["ooc"] = ooc
            dump(outdir / "ooc.json", ooc)
    return record


def run_mem_sim(ad, spec, design, work, module, cfg, tb, props, part, period_ns, mem_max, outdir):
    """The memory-read simulation (a ROM or RAM read back word by word): addresses from a file, data and address
    recorded every clock, latency found and every word compared."""
    vhd = (work / "ip" / module / f"{module}.vho").read_text()  # the instantiation template lists the ports for any IP
    aw = int(re.search(r"addra\s*:\s*IN\s+STD_LOGIC_VECTOR\((\d+) DOWNTO 0\)", vhd, re.I).group(1)) + 1
    dw = int(re.search(r"douta\s*:\s*OUT\s+STD_LOGIC_VECTOR\((\d+) DOWNTO 0\)", vhd, re.I).group(1)) + 1
    addrs = ad.addresses(spec, design)
    af = work / "addr.txt"
    af.write_text("".join(f"{a:x}\n" for a in addrs))
    resp = work / "resp_mem.txt"
    harness.render_tb_mem(tb, dut_inst=ad.dut_inst_mem(module, {}), addr_w=aw, data_w=dw, n_addr=len(addrs), addr_file=af,
                          resp=resp, period_ns=period_ns)
    write_cfg(cfg, part=part, workdir=work, module=module, create_args=ad.create_args, props=props, tb_file=tb,
              tb_top="tb_mem_read", clock_port=ad.clock_port, clock_period_ns=period_ns)
    if (work / "sim.done").exists():
        (work / "sim.done").unlink()
    r = harness.run_vivado(harness.HERE / "tcl" / "ip_flow.tcl", [str(cfg), "sim"], work, "sim_mem.log", mem_max)
    if r.returncode or not (work / "sim.done").exists() or not resp.exists():
        res = {"match": False, "error": harness.log_errors(work / "sim_mem.log")[:10] or ["sim failed"]}
    else:
        a, d = harness.read_mem_response(resp)
        res = ad.check_mem(spec, design, a, d, dw)
        res["addr_width"], res["data_width"] = aw, dw
    dump(outdir / "sim.json", {"sim": {"mem": res}})
    return {"mem": res}


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
