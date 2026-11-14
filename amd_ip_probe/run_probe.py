#!/usr/bin/env python3
"""Run one AMD-IP probe bench in Vivado 2026.1 xsim and write its record (brief 69).

    python3 amd_ip_probe/run_probe.py gpio [--out DIR] [--record results/69_amd_ip_conventions/gpio.json]

Needs a local Vivado 2026.1 (Basic tier). Generates the IP in a throw-away project, compiles it with the bench and our
AXI transactor and protocol checker (axi_tx/rtl), runs xsim, and parses the `PROBE|name|key=value ...` lines the bench
prints. Small simulation, no implementation; the caller holds a heavy slot while Vivado runs (FDA house rules).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from ips import IPS  # noqa: E402

VIVADO = os.environ.get("FDA_VIVADO", "/opt/Xilinx/2026.1/Vivado/bin/vivado")
CORE = ["axil_tx_master.sv", "axil_rules.sv", "axi_viol_log.sv", "axil_checker.sv"]
PROBE_RE = re.compile(r"^PROBE\|([^|]*)\|(.*)$")
KV_RE = re.compile(r"(\w+)=(\S+)")


BD_TCL = """
create_bd_design bd
set ic [create_bd_cell -type ip -vlnv $def ic]
set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 2] $ic
set gp [create_bd_cell -type ip -vlnv [lindex [lsort [get_ipdefs -all xilinx.com:ip:axi_gpio:*]] end] gpio]
set_property -dict [list CONFIG.C_GPIO_WIDTH 8 CONFIG.C_IS_DUAL 1 CONFIG.C_GPIO2_WIDTH 4 CONFIG.C_INTERRUPT_PRESENT 1 CONFIG.C_TRI_DEFAULT 0x000000F0 CONFIG.C_DOUT_DEFAULT 0x000000A5 CONFIG.C_TRI_DEFAULT_2 0x0000000F CONFIG.C_DOUT_DEFAULT_2 0x00000005] $gp
set ua [create_bd_cell -type ip -vlnv [lindex [lsort [get_ipdefs -all xilinx.com:ip:axi_uartlite:*]] end] uart]
set s [create_bd_intf_port -mode Slave -vlnv xilinx.com:interface:aximm_rtl:1.0 S00_AXI]
set_property -dict [list CONFIG.PROTOCOL AXI4LITE CONFIG.DATA_WIDTH 32 CONFIG.ADDR_WIDTH 32 CONFIG.FREQ_HZ 100000000] $s
create_bd_port -dir I -type clk -freq_hz 100000000 aclk
create_bd_port -dir I -type rst aresetn
connect_bd_intf_net $s [get_bd_intf_pins ic/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins ic/M00_AXI] [get_bd_intf_pins gpio/S_AXI]
connect_bd_intf_net [get_bd_intf_pins ic/M01_AXI] [get_bd_intf_pins uart/S_AXI]
foreach p [get_bd_pins -quiet -of_objects [get_bd_cells ic] -filter {TYPE==clk}] { connect_bd_net [get_bd_ports aclk] $p }
foreach p [get_bd_pins -quiet -of_objects [get_bd_cells ic] -filter {TYPE==rst}] { connect_bd_net [get_bd_ports aresetn] $p }
connect_bd_net [get_bd_ports aclk] [get_bd_pins gpio/s_axi_aclk] [get_bd_pins uart/s_axi_aclk]
connect_bd_net [get_bd_ports aresetn] [get_bd_pins gpio/s_axi_aresetn] [get_bd_pins uart/s_axi_aresetn]
make_bd_intf_pins_external [get_bd_intf_pins gpio/GPIO]
make_bd_intf_pins_external [get_bd_intf_pins uart/UART]
assign_bd_address -offset 0x00001000 -range 4K [get_bd_addr_segs gpio/S_AXI/Reg]
assign_bd_address -offset 0x00002000 -range 4K [get_bd_addr_segs uart/S_AXI/Reg]
validate_bd_design
save_bd_design
generate_target all [get_files bd.bd]
make_wrapper -files [get_files bd.bd] -top
add_files -norecurse [glob WORKDIR/proj/probe.gen/sources_1/bd/bd/hdl/bd_wrapper.v]
update_compile_order -fileset sources_1
"""


def tcl_text(name: str, cfg: dict, work: Path) -> str:
    e = IPS[name]
    if e.get("bd"):
        head = [
            "set_param general.maxThreads 1",
            "set_param synth.maxThreads 1",
            f"create_project -force probe {work}/proj -part xc7a100tcsg324-1",
            f"set def [lindex [lsort [get_ipdefs -all xilinx.com:ip:{e['ip']}:*]] end]",
            'puts "FDA-IP VIVADO [version -short]"',
            'puts "FDA-IP VLNV $def REQUIRES_LICENSE [get_property REQUIRES_LICENSE $def]"',
            'puts "FDA-IP VLNV_GPIO [lindex [lsort [get_ipdefs -all xilinx.com:ip:axi_gpio:*]] end] VLNV_UART [lindex [lsort [get_ipdefs -all xilinx.com:ip:axi_uartlite:*]] end]"',
            BD_TCL.replace("WORKDIR", str(work)),
        ]
        tail = [
            "set core {" + " ".join(str(ROOT / 'axi_tx' / 'rtl' / f) for f in CORE) + "}",
            "add_files -fileset sim_1 $core",
            f"add_files -fileset sim_1 {HERE}/tb/{e['tb']}.sv",
            f"set_property include_dirs {HERE}/tb [get_filesets sim_1]",
            f"set_property top {e['tb']} [get_filesets sim_1]",
            "set_property top_lib xil_defaultlib [get_filesets sim_1]",
            "set_property -name {xsim.simulate.runtime} -value {all} -objects [get_filesets sim_1]",
            "update_compile_order -fileset sim_1",
            "launch_simulation -simset sim_1 -mode behavioral",
            "close_sim", "close_project", "exit",
        ]
        return "\n".join(head + tail) + "\n"
    lines = [
        "set_param general.maxThreads 1",
        "set_param synth.maxThreads 1",
        f"create_project -force probe {work}/proj -part xc7a100tcsg324-1",
        f"set defs [lsort [get_ipdefs -all xilinx.com:ip:{e['ip']}:*]]",
        "set def [lindex $defs end]",
        'puts "FDA-IP VIVADO [version -short]"',
        'puts "FDA-IP VLNV $def REQUIRES_LICENSE [get_property REQUIRES_LICENSE $def]"',
        f"create_ip -vlnv $def -module_name {e['module']}",
        f"set ip [get_ips {e['module']}]",
        "set_property -dict {" + " ".join(f"{k} {{{v}}}" for k, v in cfg.items()) + "} $ip",
        "foreach p [list_property $ip CONFIG.*] { puts \"FDA-IP CFG $p [get_property $p $ip]\" }",
        "generate_target all $ip",
        "set core {" + " ".join(str(ROOT / 'axi_tx' / 'rtl' / f) for f in CORE) + "}",
        "add_files -fileset sim_1 $core",
        f"add_files -fileset sim_1 {HERE}/tb/{e['tb']}.sv",
        f"set_property include_dirs {HERE}/tb [get_filesets sim_1]",
        f"set_property top {e['tb']} [get_filesets sim_1]",
        "set_property top_lib xil_defaultlib [get_filesets sim_1]",
        "set_property -name {xsim.simulate.runtime} -value {all} -objects [get_filesets sim_1]",
        "update_compile_order -fileset sim_1",
        "launch_simulation -simset sim_1 -mode behavioral",
        "close_sim",
        "close_project",
        "exit",
    ]
    return "\n".join(lines) + "\n"


def parse(log: str) -> dict:
    meta, probes = {}, []
    for ln in log.splitlines():
        if ln.startswith("FDA-IP VIVADO"):
            meta["vivado"] = ln.split()[-1]
        elif ln.startswith("FDA-IP VLNV_GPIO"):
            m = re.match(r"FDA-IP VLNV_GPIO (\S+) VLNV_UART (\S+)", ln)
            meta["slaves"] = [m.group(1), m.group(2)]
        elif ln.startswith("FDA-IP VLNV "):
            m = re.match(r"FDA-IP VLNV (\S+) REQUIRES_LICENSE (.*)", ln)
            meta["vlnv"], meta["requires_license"] = m.group(1), m.group(2).strip()
        elif ln.startswith("FDA-IP CFG"):
            parts = ln.split(None, 3)
            meta.setdefault("config", {})[parts[2]] = parts[3] if len(parts) > 3 else ""
        m = PROBE_RE.match(ln.strip())
        if m:
            kv = dict(KV_RE.findall(m.group(2)))
            probes.append({"probe": m.group(1), "text": m.group(2).strip(), "values": kv})
    return {"meta": meta, "probes": probes}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ip", choices=sorted(IPS))
    ap.add_argument("--out", default=str(Path(os.environ.get("TMPDIR", "/tmp")) / "amd_ip_probe"))
    ap.add_argument("--record", help="write the JSON record here")
    a = ap.parse_args()
    e = IPS[a.ip]
    work = Path(a.out) / a.ip
    work.mkdir(parents=True, exist_ok=True)
    tcl = work / "run.tcl"
    tcl.write_text(tcl_text(a.ip, e["cfg"], work))
    r = subprocess.run([VIVADO, "-mode", "batch", "-notrace", "-nojournal", "-log", str(work / "vivado.log"),
                        "-source", str(tcl)], capture_output=True, text=True, cwd=work, timeout=1500)
    log = r.stdout + r.stderr
    (work / "stdout.log").write_text(log)
    sim = list(work.rglob("simulate.log"))
    simlog = sim[0].read_text() if sim else ""
    rec = parse(log)
    probes_src = simlog if simlog else log
    rec["probes"] = parse(probes_src)["probes"]
    rec["ip"] = a.ip
    rec["bench"] = f"amd_ip_probe/tb/{e['tb']}.sv"
    rec["bench_sha256"] = hashlib.sha256((HERE / "tb" / f"{e['tb']}.sv").read_bytes()).hexdigest()[:16]
    rec["returncode"] = r.returncode
    rec["errors"] = [ln for ln in log.splitlines() if re.match(r"^(ERROR|FATAL)", ln)][:10]
    if a.record:
        Path(a.record).write_text(json.dumps(rec, indent=1) + "\n")
    print(f"{a.ip}: {len(rec['probes'])} probes, vivado rc={r.returncode}, errors={len(rec['errors'])}")
    for ln in rec["errors"]:
        print("  ", ln)
    return 0 if rec["probes"] and not rec["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
