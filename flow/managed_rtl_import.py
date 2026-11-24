#!/usr/bin/env python3
"""Importing a third-party RTL block into a managed project (brief 102, stage 3).

    python3 flow/managed_rtl_import.py check designs/<name> [--component C] [--upstream CLONE] [--eqy] [--out FILE]

``check`` runs on every ``level: rtl`` component that names an upstream (``provenance.upstream_url``) and is not owned:

1. **provenance**: an open licence (Apache-2.0, MIT, BSD-2/3-Clause), the exact 40-hex commit, the licence file in the tree, and
   the SHA-256 of every file as received equal to the file now (:func:`agent.core.managed.third_party_gaps`);
2. **upstream** (``--upstream CLONE``): each file's bytes at that commit in a git clone of the upstream
   (``git show <commit>:<path>``) hash to the recorded value, so "vendored unmodified" is checked against the source, not
   against our own record;
3. **interface**: the module's ports at the parameters the design instantiates it with (``interface.parameters``) against the
   contract's ``interface.ports``;
4. **simulation**: the block alone against a Python model of one CRC-32 step (reflected, polynomial 04C11DB7), 2,000 random
   vectors at each of the widths 8, 16, 32 and 64; and, where the design has an adapter component whose module has the CRC
   port list (``clk rst init en d crc``), that adapter plus the block against the register model of
   :func:`flow.managed_import.crc32_model`. A copy of the block with one line removed must fail both (the tests plant it);
5. **equivalence** (``--eqy``): ``eqy`` proves the adapter plus the block equivalent to the adapter component's ``reference_rtl``
   (our own specification, written without the block).

A passing run with the simulations executed writes ``build/managed/evidence/<component>.json`` (``verified``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.core import managed as M  # noqa: E402
from flow import managed_import as I  # noqa: E402

STEP_WIDTHS = (8, 16, 32, 64)
N_VECTORS = 2000


def _env() -> dict[str, str]:
    cad = os.environ.get("FDA_OSS_CAD")
    return {**os.environ, "PATH": (f"{cad}/bin:" if cad else "") + os.environ["PATH"]}


def crc_step(state: int, data: int, width: int) -> int:
    """One CRC-32 step (reflected, polynomial 04C11DB7, register form) over ``width`` data bits, least significant bit first."""
    r = state
    for i in range(width):
        fb = (r ^ (data >> i)) & 1
        r >>= 1
        if fb:
            r ^= 0xEDB88320
    return r


def simulate_block(block: Path, module: str, work: Path, width: int, seed: int = 7, n: int = N_VECTORS) -> dict[str, Any]:
    """The combinational block (ports data_in, state_in, data_out, state_out) at CRC-32 settings against :func:`crc_step`."""
    work.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed + width)
    hx = (width + 3) // 4
    lines = ["`timescale 1ns/1ps", "module tb;", f"  reg [{width - 1}:0] d = 0; reg [31:0] s = 0; wire [{width - 1}:0] dout; wire [31:0] so; integer bad = 0;",
             f"  {module} #(.LFSR_WIDTH(32), .LFSR_POLY(32'h04c11db7), .LFSR_CONFIG(\"GALOIS\"), .LFSR_FEED_FORWARD(0), .REVERSE(1), .DATA_WIDTH({width}), .STYLE(\"AUTO\"))"
             "    dut (.data_in(d), .state_in(s), .data_out(dout), .state_out(so));",
             "  task chk(input [%d:0] dd, input [31:0] ss, input [31:0] want);" % (width - 1),
             "    begin d = dd; s = ss; #1; if (so !== want) bad = bad + 1; end", "  endtask", "  initial begin"]
    for _ in range(n):
        dd, ss = rng.getrandbits(width), rng.getrandbits(32)
        lines.append(f"    chk({width}'h{dd:0{hx}x}, 32'h{ss:08x}, 32'h{crc_step(ss, dd, width):08x});")
    lines += [f'    $display("RESULT bad=%0d of {n}", bad); $finish;', "  end", "endmodule"]
    (work / "tb.sv").write_text("\n".join(lines) + "\n")
    c = subprocess.run(["iverilog", "-g2012", "-o", str(work / "sim.vvp"), str(work / "tb.sv"), str(block)], capture_output=True, text=True)
    if c.returncode:
        return {"width": width, "passed": False, "error": c.stderr[-300:]}
    r = subprocess.run(["vvp", str(work / "sim.vvp")], capture_output=True, text=True, timeout=300)
    m = re.search(r"RESULT bad=(\d+) of (\d+)", r.stdout)
    return {"width": width, "passed": bool(m and m.group(1) == "0"), "mismatches": int(m.group(1)) if m else None, "vectors": n}


def planted_fault_copy(block: Path, out: Path) -> str:
    """A copy of the block with one line of the Galois next-state mask removed: what the simulations must reject."""
    text = block.read_text()
    old = "lfsr_mask_state[j] = lfsr_mask_state[j] ^ state_val;"
    if text.count(old) != 1:
        raise ValueError("the planted-fault anchor line was not found exactly once (a different version of the block?)")
    out.write_text(text.replace(old, "lfsr_mask_state[j] = lfsr_mask_state[j];"))
    return f"removed {old!r} (the state feedback into one polynomial tap)"


def upstream_problems(comp: M.Component, project: M.Project, clone: Path) -> list[str]:
    """Each recorded file against ``git show <commit>:<upstream path>`` in a clone of the upstream."""
    prov, out = comp.provenance, []
    commit = str(prov.get("commit", ""))
    if subprocess.run(["git", "-C", str(clone), "cat-file", "-e", f"{commit}^{{commit}}"], capture_output=True).returncode:
        return [f"commit {commit} is not in {clone}"]
    for rel, upath in sorted((prov.get("upstream_paths") or {}).items()):
        r = subprocess.run(["git", "-C", str(clone), "show", f"{commit}:{upath}"], capture_output=True)
        if r.returncode:
            out.append(f"{upath} not found at {commit[:12]}")
        elif hashlib.sha256(r.stdout).hexdigest() != M.sha256_file(project.design / rel):
            out.append(f"{rel} differs from {upath} at {commit[:12]}")
    missing = sorted(set((prov.get("files") or {})) - set(prov.get("upstream_paths") or {}))
    return out + [f"{m}: no upstream_paths entry, so not checked against the source" for m in missing]


def contract_problems(project: M.Project, comp: M.Component) -> list[str]:
    from flow import sources
    unread = sources.no_reader(M.component_files(project, comp), {"sv"}, "the managed RTL import (it reads a Verilog port list and simulates under Icarus)")
    if unread:                                           # brief 153: a VHDL component is not "a module with no port list": say what was not read
        return [unread]
    srcs = [p for p in M.component_files(project, comp) if p.suffix in (".v", ".sv")]
    for f in srcs:
        got = M.parse_module_ports(f.read_text(), comp.module or "", {k: int(v) for k, v in (comp.interface.get("parameters") or {}).items()})
        if got:
            return M.interface_diff(comp.interface.get("ports") or [], got) if comp.interface.get("ports") else ["no interface contract (interface.ports)"]
    return [f"no module {comp.module!r} with an ANSI port list in the component's files"]


def build_files(project: M.Project, comp: M.Component) -> list[Path]:
    """The component's source files as the build compiles them (build_sources, repo-relative), not its reference or licence files;
    resolved under the project's own design directory (so a copy of the design in a scratch folder is read, not the original)."""
    from flow import sources
    pre = f"designs/{project.design.name}/"
    files = [project.design / b[len(pre):] if b.startswith(pre) else ROOT / b for b in comp.build_sources if sources.language(b) in ("sv", "vhdl")]
    unread = sources.no_reader(files, {"sv"}, "the managed RTL import")
    if unread:                                           # never drop a VHDL source silently from a component's build files
        raise ValueError(unread)
    return [f for f in files if f.suffix in (".v", ".sv")]


def adapter_of(project: M.Project) -> M.Component | None:
    """The owned component whose module is the CRC port list the sequencer uses (``clk rst init en d crc``)."""
    want = {"clk", "rst", "init", "en", "d", "crc"}
    for c in project.components:
        if c.ownership == "owned" and c.interface.get("ports") and {p["name"] for p in c.interface["ports"]} == want:
            return c
    return None


def import_check(design: Path, only: str | None = None, upstream: Path | None = None, run_eqy: bool = False, work: Path | None = None) -> dict[str, Any]:
    project = M.load(design)
    if project is None:
        raise SystemExit(f"{design}: no project.yaml")
    work = work or design / "build" / "managed" / "rtl_import"
    rep: dict[str, Any] = {"design": design.name, "components": {}}
    adapter = adapter_of(project)
    for c in project.components:
        if c.level != "rtl" or c.ownership == "owned" or not c.provenance.get("upstream_url") or (only and c.name != only):
            continue
        r: dict[str, Any] = {"provenance": M.third_party_gaps(project, c), "licence": c.provenance.get("spdx"),
                             "commit": c.provenance.get("commit"), "upstream_url": c.provenance.get("upstream_url"),
                             "interface": contract_problems(project, c)}
        if upstream is not None:
            r["upstream"] = upstream_problems(c, project, upstream)
        try:
            block = next(iter(build_files(project, c)), None)
        except ValueError as e:                          # a VHDL source: not read, so not simulated and not passed (brief 153)
            block = None
            r["not_run"] = str(e)
        sims = []
        if block is not None:
            sims = [simulate_block(block, c.module or "", work / c.name / f"step{w}", w) for w in STEP_WIDTHS]
            fault = planted_fault_copy(block, work / c.name / "lfsr_fault.v")
            fsim = simulate_block(work / c.name / "lfsr_fault.v", c.module or "", work / c.name / "fault16", 16)
            r["planted_fault"] = {"what": fault, "rejected_by_block_sim": fsim.get("passed") is False and bool(fsim.get("mismatches")), "mismatches": fsim.get("mismatches")}
        r["block_simulation"] = sims
        if adapter is not None and block is not None:
            afiles = [*build_files(project, adapter), block]
            r["adapter_simulation"] = {"adapter": adapter.name, **I.simulate_crc_netlist(afiles, adapter.module or "", work / c.name / "adapter", 16)}
            if "planted_fault" in r:
                fa = I.simulate_crc_netlist([*(f for f in afiles if f != block), work / c.name / "lfsr_fault.v"], adapter.module or "", work / c.name / "adapter_fault", 16)
                r["planted_fault"]["rejected_by_adapter_sim"] = fa.get("passed") is False and bool(fa.get("mismatches"))
                r["planted_fault"]["adapter_mismatches"] = fa.get("mismatches")
        if run_eqy and adapter is not None and block is not None and adapter.reference_rtl:
            gate = work / c.name / "gate.v"
            gate.write_text("\n".join(f.read_text() for f in [*build_files(project, adapter), block]))
            r["eqy"] = I.eqy_prove([project.design / p for p in adapter.reference_rtl], gate, adapter.module or "", work / c.name / "eqy", timeout=600)
        needs_adapter = bool(adapter is not None and adapter.reference_rtl) or adapter is not None
        ok = (needs_adapter and "adapter_simulation" in r
              and not r["provenance"] and not r["interface"] and not r.get("upstream")
              and bool(sims) and all(s["passed"] for s in sims)
              and r.get("adapter_simulation", {"passed": True})["passed"] is True
              and r.get("planted_fault", {}).get("rejected_by_block_sim") is True and r.get("planted_fault", {}).get("rejected_by_adapter_sim") is True
              and (not run_eqy or r.get("eqy", {}).get("equivalent") is True))
        r["passed"] = ok
        rep["components"][c.name] = r
        if ok:
            M.write_evidence(project, c, "verified", {"passed": True, "upstream_checked": upstream is not None, "tests": ["provenance", "interface", "block_simulation", "planted_fault"] +
                                                      (["upstream"] if upstream is not None else []) + (["adapter_simulation"] if "adapter_simulation" in r else []) +
                                                      (["eqy"] if run_eqy else [])})
    rep["passed"] = bool(rep["components"]) and all(v["passed"] for v in rep["components"].values())
    return rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("design", type=Path)
    c.add_argument("--component")
    c.add_argument("--upstream", type=Path, help="a git clone of the upstream repository (the files are compared with the recorded commit)")
    c.add_argument("--eqy", action="store_true")
    c.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    os.environ["PATH"] = _env()["PATH"]
    rep = import_check(a.design, a.component, a.upstream, a.eqy)
    text = json.dumps(rep, indent=1, default=str) + "\n"
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text)
    print(text)
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
