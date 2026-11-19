#!/usr/bin/env python3
"""A scripted session through the agent's real tool surface on the third-party-block project (brief 102, stage 3).

    python3 designs/b102_managed_ext/scripts/demo_ext_session.py [--out results/102_stage3/demo_session.json]

No model runs: the "agent" is this script, calling ``agent.core.dispatch`` (the path the agent's tool calls take), so the ownership,
scope and contract rules are the code under test. It works on a scratch copy of the design and plays:

1. "make the lfsr faster" names only the frozen third-party block: a question comes back, no scope, no edit;
2. "make the verdict one clock faster" resolves to ``ctrl``: scope ``ctrl``;
3. attempts that must fail: edit the vendored lfsr.v, its licence file, add a file beside it, reach it by a path with '..', write the
   owned adapter (owned, but out of scope), write project.yaml, and drop the block from build.yaml;
4. the allowed edit (the same one-clock change as stage 1, in fcs_ctrl.sv), then the whole design simulated before and after with
   the third-party block compiled in: both pass the self-test, the edit saves one clock;
5. the provenance report: what is theirs and what is ours.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "designs" / "b102_managed_fcs" / "scripts"))

from agent.core import dispatch  # noqa: E402
from agent.core import managed as M  # noqa: E402
from agent.core.runner import LocalRunner  # noqa: E402
from agent.core.session import Session  # noqa: E402
from demo_managed_session import edited_ctrl  # noqa: E402  (the stage 1 edit: same controller)

DESIGN = ROOT / "designs" / "b102_managed_ext"
LFSR = "third_party/verilog-ethernet/lfsr.v"
TB = """module tb; reg clk = 0; wire [1:0] led; integer cyc = 0, t_pass = -1;
  fcs_top dut (.clk_25(clk), .led(led)); always #5 clk = ~clk; initial dut.por = 4'd0;
  always @(posedge clk) begin cyc <= cyc + 1; if (dut.u_ctrl.pass_o && t_pass < 0) t_pass <= cyc; end
  initial begin repeat (200) @(posedge clk); $display("RESULT pass_cycle=%0d led0=%0d", t_pass, led[0]); $finish; end endmodule
"""


def simulate(design: Path, ctrl: Path, work: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    (work / "tb.sv").write_text(TB)
    srcs = [design / LFSR, design / "rtl/crc32_d16.sv", ctrl, design / "rtl/fcs_top.sv", work / "tb.sv"]
    subprocess.run(["iverilog", "-g2012", "-o", str(work / "s.vvp"), *map(str, srcs)], check=True, capture_output=True, text=True)
    out = subprocess.run(["vvp", str(work / "s.vvp")], check=True, capture_output=True, text=True).stdout
    m = re.search(r"RESULT pass_cycle=(-?\d+) led0=(\d)", out)
    return {"first_pass_cycle": int(m.group(1)), "led0_at_end": int(m.group(2))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--work", type=Path, default=ROOT / "build" / "102_demo3" / "designs" / "b102_managed_ext")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "102_stage3" / "demo_session.json")
    a = ap.parse_args(argv)
    work = a.work
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(DESIGN, work, ignore=shutil.ignore_patterns("build", "__pycache__"))
    proj = M.load(work)
    steps: list[dict] = []

    def log(what: str, **kw) -> None:
        steps.append({"step": what, **kw})
        print(what, "->", {k: (str(v)[:110] if not isinstance(v, (bool, list)) else v) for k, v in kw.items()})

    r = M.resolve_request(proj, "make the lfsr faster")
    log("request: make the lfsr faster", scope=None if r.scope is None else r.scope.components, question=r.question)
    assert r.scope is None and "frozen" in (r.question or "")
    r = M.resolve_request(proj, "make the verdict one clock faster")
    log("request: make the verdict one clock faster", scope=r.scope.components, source=r.scope.source)
    assert r.scope.components == ("ctrl",)
    M.start_run(proj, r.scope)
    sess = Session(design=work, root=ROOT, runner=LocalRunner(), board="kr260")
    before = {p.relative_to(work).as_posix(): M.sha256_file(p) for c in proj.components for p in M.component_files(proj, c)}

    def call(tool: str, expect_refused: bool | None, **kw) -> dict:
        res = dispatch(sess, tool, kw)
        log(f"{tool} {kw.get('path', '')}".strip(), ok=res["ok"], refused=res["refused"], rule=res.get("rule"), output=res["output"][:140])
        if expect_refused is not None:
            assert res["refused"] is expect_refused, (tool, kw, res)
        return res

    call("read_file", False, path=LFSR)                                   # frozen means readable: the agent may study the block
    call("write_file", True, path=LFSR, content="module lfsr; endmodule\n")
    call("write_file", True, path="third_party/verilog-ethernet/COPYING", content="Public domain\n")
    call("write_file", True, path="third_party/verilog-ethernet/lfsr_fast.v", content="module lfsr_fast; endmodule\n")
    call("write_file", True, path="rtl/../third_party/verilog-ethernet/lfsr.v", content="x\n")
    adapter = (work / "rtl/crc32_d16.sv").read_text()
    call("write_file", True, path="rtl/crc32_d16.sv", content=adapter + "// out of scope\n")          # owned, but this run's scope is ctrl
    call("write_file", True, path="project.yaml", content="schema: x\n")
    bcfg = (work / "build.yaml").read_text()
    call("write_file", True, path="build.yaml", content=bcfg.replace("  - designs/b102_managed_ext/third_party/verilog-ethernet/lfsr.v\n", ""))
    ctrl = (work / "rtl/fcs_ctrl.sv").read_text()
    new = edited_ctrl(ctrl)
    call("write_file", False, path="rtl/fcs_ctrl.sv", content=new)

    sim = {"baseline": simulate(DESIGN, DESIGN / "rtl/fcs_ctrl.sv", work / "sim_base"), "edited": simulate(work, work / "rtl/fcs_ctrl.sv", work / "sim_edit")}
    sim["clocks_saved"] = sim["baseline"]["first_pass_cycle"] - sim["edited"]["first_pass_cycle"]
    log("simulation with the third-party block compiled in", **sim)
    assert sim["baseline"]["led0_at_end"] == 1 and sim["edited"]["led0_at_end"] == 1 and sim["clocks_saved"] == 1

    md = M.write_provenance(proj, before)
    rep = json.loads((work / M.MANAGED_DIR / "provenance.json").read_text())
    out = {"design": "b102_managed_ext", "scope": rep["scope"], "steps": steps, "changed_files": rep["changed_files"], "simulation": sim,
           "managed_refusals": len(rep["managed_refusals"]), "refusal_rules": sorted({r["rule"] for r in rep["managed_refusals"]}),
           "provenance_markdown": md.read_text(),
           "vendored_unchanged": all(M.sha256_file(work / rel) == M.sha256_file(DESIGN / rel) for rel in proj.component("lfsr").provenance["files"])}
    assert out["changed_files"] == ["rtl/fcs_ctrl.sv"] and out["vendored_unchanged"]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(f"changed: {out['changed_files']}; refusals {out['managed_refusals']} ({', '.join(out['refusal_rules'])}); wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
