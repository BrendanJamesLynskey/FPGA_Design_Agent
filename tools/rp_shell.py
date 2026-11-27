#!/usr/bin/env python3
"""Build a design into the Red Pitaya vendor shell (brief 225): the "shell" way to build for the STEMlab 125-14, as opposed to "bare".

    python3 tools/rp_shell.py prepare <workdir> [--block FILE.sv ...]     # fetch the vendor repository at the pinned commit, add the blocks, patch the top
    python3 tools/rp_shell.py build   <workdir> [--mem 8G]                # run the vendor's Vivado script on it (one heavy slot, under a systemd scope)
    python3 tools/rp_shell.py package <workdir> <outdir>                  # fpga.bit.bin, the reports and build.json (the build id, the pins, the hashes)
    python3 tools/rp_shell.py check                                       # the patch's markers against the text the pin was made from (no network)

What "inside the shell" means here. The vendor's FPGA project (RedPitaya/RedPitaya-FPGA, shell v0.94, BSD 3-clause) keeps the register map, the ADC and
DAC front end, the calibration registers and the oscilloscope and generator. The vendor top has eight 1 MiB system-bus slots at 0x40000000; slots 0 to 5
are used and slot 7 is a stub (``sys_bus_stub``) that answers every access with an error. This tool replaces that stub with ``rp_user_block`` (our own
file, ``boards/redpitaya_stemlab_125_14/shell/rp_user_block.sv``, or any block with the same ports) and adds the block's ``dac_a`` and ``dac_b`` to the
sum the shell sends to the DAC. Everything else is the vendor's text, unchanged. Nothing of the vendor's is committed here: the repository is fetched at
the pinned commit into a work directory, the top file's SHA-256 is checked before the patch, and each patch marker must match exactly once, so a
vendor change makes the tool stop and say so rather than build something else.

Loading is not done here. ``fpga.bit.bin`` is loaded by the owner's script (``hil/redpitaya_load.py`` writes it), with ``overlay.sh`` keeping the shell's
own device tree. A power cycle returns the factory image.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/RedPitaya/RedPitaya-FPGA.git"
COMMIT = "728a4f37e9c0a9b5ba1d9b7a0d44c38bbd2dc674"            # the pin (also boards/redpitaya_stemlab_125_14/board.yaml, source RPFPGA)
BASE_PRJ = "v0.94"
NEW_PRJ = "fda_shell"
TOP_REL = "rtl/red_pitaya_top.sv"
TOP_SHA256 = "fa9d2a5c09702c6ca3d3bf43bb9f43af9ea06cde4642c143dce39b2818096065"          # prj/v0.94/rtl/red_pitaya_top.sv at COMMIT
BLOCK_DEFAULT = ROOT / "boards" / "redpitaya_stemlab_125_14" / "shell" / "rp_user_block.sv"
SLOT = 7
DIRECTIVES_DEFAULT = ("Explore", "Explore", "Explore")            # implementation directives: placement, physical optimisation, routing (brief 235's)
VIVADO_TCL = "red_pitaya_vivado_Z10.tcl"
OVERLAY_NAME = "fda_overlay.xdc"        # brief 235: our constraints overlay, added after the vendor's files (boards/redpitaya_stemlab_125_14/shell/fda_overlay.xdc)

ADAPT_DEFAULT = ROOT / "boards" / "redpitaya_stemlab_125_14" / "shell" / "rp_bus_adapt.sv"      # brief 243: the adapter in front of every user block


def slot_instance(slot: int, module: str, inst: str, dac: str, note: str) -> str:
    """The text that replaces a slot's stub: the bus adapter (``rp_bus_adapt``, brief 243) and the block behind it. The block keeps the one-cycle
    convention of shell.yaml; the adapter gives the vendor's clock-crossing bridge what it needs (a held answer). Indentation is the vendor's."""
    u = f"u{slot}"
    return (f"  logic [31:0] {u}_addr, {u}_wdata, {u}_rdata;  logic {u}_wen, {u}_ren, {u}_err, {u}_ack;        // fda_shell: the block's side of the adapter\n"
            f"  rp_bus_adapt i_bus_adapt{slot} (                                          // fda_shell: slot {slot}: one access per request, answer held for the shell's bridge\n"
            f"    .clk (adc_clk), .rstn (adc_rstn),\n"
            f"    .s_addr (sys[{slot}].addr), .s_wdata (sys[{slot}].wdata), .s_wen (sys[{slot}].wen), .s_ren (sys[{slot}].ren),\n"
            f"    .s_rdata (sys[{slot}].rdata), .s_err (sys[{slot}].err), .s_ack (sys[{slot}].ack),\n"
            f"    .b_addr ({u}_addr), .b_wdata ({u}_wdata), .b_wen ({u}_wen), .b_ren ({u}_ren), .b_rdata ({u}_rdata), .b_err ({u}_err), .b_ack ({u}_ack));\n"
            f"  {module} {inst} (                                          // fda_shell: {note}\n"
            f"    .clk (adc_clk), .rstn (adc_rstn),\n"
            f"    .sys_addr ({u}_addr), .sys_wdata ({u}_wdata), .sys_wen ({u}_wen), .sys_ren ({u}_ren),\n"
            f"    .sys_rdata ({u}_rdata), .sys_err ({u}_err), .sys_ack ({u}_ack),\n"
            f"    .adc_a (adc_dat[0]), .adc_b (adc_dat[1]), .dac_a ({dac}[0]), .dac_b ({dac}[1]));")


#: (marker in the vendor top, replacement): each marker must occur exactly once. The first adds the block's DAC term to the sum, the second declares it, the
#: third replaces the slot-7 stub with the block behind its bus adapter.
PATCH = (
    ("assign dac_a_sum = asg_dat[0] + pid_dat[0];", "assign dac_a_sum = asg_dat[0] + pid_dat[0] + user_dac[0];     // fda_shell: the user block's term"),
    ("assign dac_b_sum = asg_dat[1] + pid_dat[1];", "assign dac_b_sum = asg_dat[1] + pid_dat[1] + user_dac[1];     // fda_shell: the user block's term"),
    ("SBA_T [2-1:0]            pid_dat;", "SBA_T [2-1:0]            pid_dat;\nSBG_T [2-1:0]            user_dac;                                     // fda_shell: DAC terms of the user block"),
    ("  sys_bus_stub sys_bus_stub_7 (sys[7]);",
     slot_instance(7, "rp_user_block", "i_user_block", "user_dac", "slot 7 (0x40700000), replaces sys_bus_stub_7")),
)


#: the vendor's block-design script refuses a Vivado other than the 2025.1 it was written with (its own version check, not a feature it needs). The tool changes
#: that one line to accept the running version, and records it in build.json ("bd_script_version_line"): the result is a 2026.1 build of the vendor's design.
BD_VERSION = ("set scripts_vivado_version 2025.1", "set scripts_vivado_version [version -short]     ;# fda_shell: the vendor's BD script is written for 2025.1; accept the running version")


#: the optional second block, in slot 6 (0x40600000, a stub in the Z10 build; slot 6 is used only by the Gen 2 build). Applied after PATCH, on its text.
PATCH6 = (
    ("assign dac_a_sum = asg_dat[0] + pid_dat[0] + user_dac[0];", "assign dac_a_sum = asg_dat[0] + pid_dat[0] + user_dac[0] + user6_dac[0];"),
    ("assign dac_b_sum = asg_dat[1] + pid_dat[1] + user_dac[1];", "assign dac_b_sum = asg_dat[1] + pid_dat[1] + user_dac[1] + user6_dac[1];"),
    ("SBG_T [2-1:0]            user_dac;", "SBG_T [2-1:0]            user_dac, user6_dac;"),
    ("  sys_bus_stub sys_bus_stub_6 (sys[6]);",
     slot_instance(6, "{module6}", "i_user6_block", "user6_dac", "slot 6 (0x40600000), replaces sys_bus_stub_6")),
)


def apply_patch(text: str, module7: str = "rp_user_block", module6: str | None = None) -> str:
    """The vendor top with the user block (module ``module7``) in slot 7 and, if ``module6`` is given, a second block in slot 6. Raises ValueError naming
    the marker if one does not occur exactly once."""
    patches = [(a, b.replace("rp_user_block", module7)) for a, b in PATCH]
    if module6:
        patches += [(a, b.replace("{module6}", module6)) for a, b in PATCH6]
    for old, new in patches:
        n = text.count(old)
        if n != 1:
            raise ValueError(f"the vendor top has {n} occurrences of {old!r}, not 1: the shell changed since the pin {COMMIT[:10]}; re-read it before patching")
        text = text.replace(old, new)
    return text


def sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(argv: list[str], cwd: Path | None = None, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, check=True, capture_output=True, text=True, **kw)


def fetch(work: Path) -> None:
    """The vendor repository at the pinned commit in ``work/vendor`` (a git checkout: the vendor script reads ``git log``)."""
    v = work / "vendor"
    if (v / ".git").is_dir() and run(["git", "rev-parse", "HEAD"], v).stdout.strip() == COMMIT:
        return
    v.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "-q"], v)
    run(["git", "remote", "add", "origin", REPO], v)
    run(["git", "fetch", "-q", "--depth", "1", "origin", COMMIT], v)
    run(["git", "checkout", "-q", "FETCH_HEAD"], v)
    if run(["git", "rev-parse", "HEAD"], v).stdout.strip() != COMMIT:
        raise SystemExit("fetched commit is not the pin")


def prepare(work: Path, blocks: list[Path], module7: str = "rp_user_block", module6: str | None = None, baseline: bool = False, overlay: Path | None = None, explore: bool = False,
            directives: tuple[str, str, str] = DIRECTIVES_DEFAULT) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    fetch(work)
    v = work / "vendor"
    base, new = v / "prj" / BASE_PRJ, v / "prj" / NEW_PRJ
    top0 = base / TOP_REL
    if sha256(top0) != TOP_SHA256:
        raise SystemExit(f"{top0} is not the file the pin was made from (sha256 {sha256(top0)})")
    if new.exists():
        shutil.rmtree(new)
    shutil.copytree(base, new, ignore=shutil.ignore_patterns("out", "build", "sdk", ".Xil", "project"))
    added: list[str] = []
    if not baseline:                                  # baseline: the vendor's own top, only the version lines changed (to attribute a result to the vendor or to the patch)
        (new / TOP_REL).write_text(apply_patch(top0.read_text(), module7, module6))
        for b in (blocks or [BLOCK_DEFAULT]) + [ADAPT_DEFAULT]:          # brief 243: the bus adapter goes in with the blocks (hashed in build.json)
            shutil.copy(b, new / "rtl" / Path(b).name)
            added.append(Path(b).name)
    (work / "blocks.json").write_text(json.dumps(added))
    bd = new / "ip" / "system.tcl"
    t = bd.read_text()
    if t.count(BD_VERSION[0]) != 1:
        raise SystemExit(f"{bd}: the version line {BD_VERSION[0]!r} is not there exactly once; the shell changed since the pin")
    bd.write_text(t.replace(*BD_VERSION))
    for ipt in sorted((v / "ip" / "ip").glob("*/*.tcl")):          # the shared IP scripts (asg_dat_fifo, sync_fifo) carry the same 2025.1 check
        t = ipt.read_text()
        if t.count(BD_VERSION[0]) == 1:
            ipt.write_text(t.replace(*BD_VERSION))
    # the vendor script installs a Tcl-store app over the network; the build does not need it (it is the UltraFast rule set, not part of the result)
    tcl = (v / VIVADO_TCL).read_text()
    tcl = tcl.replace("tclapp::install -quiet ultrafast", "# tclapp::install -quiet ultrafast   (removed by tools/rp_shell.py: it needs the network)")
    if overlay is not None:                  # brief 235: our own constraints, read after the vendor's (never an edit of the vendor's files)
        shutil.copy(overlay, new / "sdc" / OVERLAY_NAME)
        tcl = overlay_tcl(tcl)
    if explore:                              # brief 235: our own implementation directives (the vendor script runs the default flow)
        tcl = explore_tcl(tcl, directives)
    (v / "fda_vivado_Z10.tcl").write_text(tcl)
    (work / "explore.json").write_text(json.dumps({"explore": bool(explore), "directives": list(directives) if explore else None}))
    (work / "overlay.json").write_text(json.dumps({"overlay": OVERLAY_NAME, "sha256": sha256(overlay)} if overlay is not None else {}))
    return new


def overlay_tcl(tcl: str, name: str = OVERLAY_NAME) -> str:
    """The vendor's build script with our constraints overlay added after its own constraint files (read late, so it can refer to anything they define).
    Raises SystemExit if the marker line is not there exactly once (the shell changed since the pin)."""
    marker = "set gith [exec git log"
    if tcl.count(marker) != 1:
        raise SystemExit(f"{VIVADO_TCL}: the marker {marker!r} is not there exactly once; the shell changed since the pin")
    return tcl.replace(marker, f"add_files -fileset constrs_1 sdc/{name}      ;# fda_shell: our constraints overlay (tools/rp_shell.py --overlay)\n"
                               f"set_property PROCESSING_ORDER LATE [get_files {name}]\n" + marker)


EXPLORE_LAUNCH = "\nlaunch_runs impl_1\n"


def explore_text(directives: tuple[str, str, str] = DIRECTIVES_DEFAULT) -> str:
    place, physopt, route = directives
    return ("\n# fda_shell: implementation directives (tools/rp_shell.py --explore); the vendor script runs the default flow\n"
            f"set_property STEPS.PLACE_DESIGN.ARGS.DIRECTIVE {place} [get_runs impl_1]\n"
            "set_property STEPS.PHYS_OPT_DESIGN.IS_ENABLED true [get_runs impl_1]\n"
            f"set_property STEPS.PHYS_OPT_DESIGN.ARGS.DIRECTIVE {physopt} [get_runs impl_1]\n"
            f"set_property STEPS.ROUTE_DESIGN.ARGS.DIRECTIVE {route} [get_runs impl_1]\n"
            "launch_runs impl_1\n")


EXPLORE = (EXPLORE_LAUNCH, explore_text())


def explore_tcl(tcl: str, directives: tuple[str, str, str] = DIRECTIVES_DEFAULT) -> str:
    """The vendor's build script with directives on placement, physical optimisation and routing of its ``impl_1`` run (default: Explore on all three)."""
    if tcl.count(EXPLORE_LAUNCH) != 1:
        raise SystemExit(f"{VIVADO_TCL}: the line 'launch_runs impl_1' is not there exactly once; the shell changed since the pin")
    return tcl.replace(EXPLORE_LAUNCH, explore_text(directives))


def build_argv(work: Path, mem: str = "8G", unit: str | None = None, vivado: str | None = None) -> list[str]:
    """The command the build runs: Vivado batch on the vendor script, inside a transient systemd scope with a memory cap, at nice 15."""
    vivado = vivado or subprocess.run([sys.executable, str(ROOT / "flow" / "version_pin.py"), "--vivado"], capture_output=True, text=True).stdout.strip()
    inner = ["nice", "-n", "15", vivado, "-nojournal", "-nolog", "-mode", "batch", "-source", "fda_vivado_Z10.tcl", "-tclargs", NEW_PRJ]
    scope = ["systemd-run", "--user", "--scope", "--quiet", "-p", f"MemoryMax={mem}"] + (["--unit", unit] if unit else [])
    return scope + inner


def build(work: Path, mem: str = "8G", vivado: str | None = None) -> int:
    v = work / "vendor"
    if not (v / "prj" / NEW_PRJ).is_dir():
        raise SystemExit("run prepare first")
    log = work / "build.log"
    with log.open("w") as fh:
        rc = subprocess.run(build_argv(work, mem, unit=f"fda-rp-shell-{os.getpid()}", vivado=vivado), cwd=v, stdout=fh, stderr=subprocess.STDOUT).returncode
    print(f"vivado exit {rc}; log {log}")
    return rc


def parse_reports(o: Path) -> dict:
    """Timing, utilisation and power from the build's own reports (numbers as the tool printed them; nothing computed here)."""
    r: dict = {}
    t = (o / "red_pitaya_top_timing_summary_routed.rpt")
    if t.is_file():
        m = re.search(r"WNS\(ns\).*?\n\s*-+.*?\n\s*(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)", t.read_text(errors="replace"), re.S)
        if m:
            wns, tns, tnsf, tnst, whs, ths, thsf, thst = m.groups()
            r["timing"] = {"wns_ns": float(wns), "tns_ns": float(tns), "tns_failing_endpoints": int(tnsf), "tns_total_endpoints": int(tnst), "whs_ns": float(whs),
                           "ths_failing_endpoints": int(thsf), "timing_met": float(wns) >= 0 and int(tnsf) == 0 and float(whs) >= 0}
    u = o / "red_pitaya_top_utilization_placed.rpt"
    if u.is_file():
        tx = u.read_text(errors="replace")
        def cell(label):
            m = re.search(r"\|\s*" + re.escape(label) + r"\s*\|\s*(\d+)\s*\|[^|]*\|[^|]*\|\s*(\d+)\s*\|", tx)
            return {"used": int(m.group(1)), "available": int(m.group(2))} if m else None
        r["utilization"] = {"slice_luts": cell("Slice LUTs"), "slice_registers": cell("Slice Registers"), "block_ram_tiles": cell("Block RAM Tile"), "dsps": cell("DSPs")}
    pw = o / "red_pitaya_top_power_routed.rpt"
    if pw.is_file():
        tx = pw.read_text(errors="replace")
        a, b = re.search(r"Total On-Chip Power \(W\)\s*\|\s*([\d.]+)", tx), re.search(r"Junction Temperature \(C\)\s*\|\s*([\d.]+)", tx)
        r["power"] = {"total_on_chip_w": float(a.group(1)) if a else None, "junction_c": float(b.group(1)) if b else None}
    return r


def package(work: Path, out: Path) -> dict:
    v = work / "vendor" / "prj" / NEW_PRJ
    o = v / "out"
    binf = o / "red_pitaya.bin"
    if not binf.is_file():
        raise SystemExit(f"no {binf}: the build did not finish")
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(binf, out / "fpga.bit.bin")                 # the name overlay.sh and fpgautil expect (Red Pitaya's documentation)
    shutil.copy(o / "red_pitaya.bit", out / "fpga.bit")
    for rpt in sorted(o.glob("*.rpt")):
        if re.search(r"(timing_summary|utilization|power|drc|methodology)", rpt.name):
            shutil.copy(rpt, out / rpt.name)
    info = {"schema": "fpga-design-agent/rp-shell-build/v1", "vendor_repo": REPO, "vendor_commit": COMMIT, "base_project": BASE_PRJ, "model": "Z10",
            "part": "xc7z010clg400-1", "slot": SLOT, "slot_address": f"0x40{SLOT}00000", "top_sha256_before": TOP_SHA256,
            "top_sha256_after": sha256(v / TOP_REL), "bd_script_version_line": "changed from 2025.1 to the running Vivado version in prj/fda_shell/ip/system.tcl and the IP scripts under ip/ip/",
            "vivado_version": next(iter(re.findall(r"Vivado v(\d{4}\.\d)", (work / "build.log").read_text(errors="replace"))), None), "blocks": {n: sha256(v / "rtl" / n) for n in (json.loads((work / "blocks.json").read_text()) if (work / "blocks.json").is_file() else [])},
            "explore": bool(json.loads((work / "explore.json").read_text()).get("explore")) if (work / "explore.json").is_file() else False,
            "directives": (json.loads((work / "explore.json").read_text()).get("directives") if (work / "explore.json").is_file() else None), "overlay": (json.loads((work / "overlay.json").read_text()) if (work / "overlay.json").is_file() else {}) or None, "bit_bin_sha256": sha256(out / "fpga.bit.bin"), "bit_bin_bytes": (out / "fpga.bit.bin").stat().st_size, "build_id": sha256(out / "fpga.bit.bin")[:8]}
    info.update(parse_reports(o))
    (out / "build.json").write_text(json.dumps(info, indent=1) + "\n")
    return info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("workdir", type=Path)
    p.add_argument("--block", type=Path, action="append", default=[], help="a block's SystemVerilog file (default: the trivial rp_user_block)")
    p.add_argument("--slot7", default="rp_user_block", help="the module for slot 7 (0x40700000)")
    p.add_argument("--slot6", default=None, help="the module for slot 6 (0x40600000), optional")
    p.add_argument("--overlay", type=Path, help="our constraints file, read after the vendor's constraints (default none; see boards/redpitaya_stemlab_125_14/shell/fda_overlay.xdc)")
    p.add_argument("--explore", action="store_true", help="the Explore directives on placement, physical optimisation and routing (default: the vendor script's default flow)")
    p.add_argument("--directives", default=",".join(DIRECTIVES_DEFAULT), help="with --explore: the directives for placement,physopt,route (default Explore,Explore,Explore)")
    p.add_argument("--baseline", action="store_true", help="no patch and no block: the vendor's own top (version lines changed only)")
    p = sub.add_parser("build")
    p.add_argument("workdir", type=Path)
    p.add_argument("--mem", default="8G")
    p.add_argument("--vivado", default=None, help="the vivado executable (default: the repo's pinned Vivado); e.g. /opt/Xilinx/2025.2/Vivado/bin/vivado")
    p = sub.add_parser("package")
    p.add_argument("workdir", type=Path)
    p.add_argument("outdir", type=Path)
    sub.add_parser("check")
    a = ap.parse_args(argv)
    if a.cmd == "prepare":
        print(prepare(a.workdir, a.block, a.slot7, a.slot6, a.baseline, a.overlay, a.explore, tuple(a.directives.split(","))))
    elif a.cmd == "build":
        return build(a.workdir, a.mem, a.vivado)
    elif a.cmd == "package":
        print(json.dumps(package(a.workdir, a.outdir), indent=1))
    else:
        print("markers:", len(PATCH), "pin:", COMMIT[:10])
    return 0


if __name__ == "__main__":
    sys.exit(main())
