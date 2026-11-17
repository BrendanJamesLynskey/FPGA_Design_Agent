#!/usr/bin/env python3
"""A scripted session through the agent's real tool surface on the managed project (brief 102, stage 1 demonstration).

    python3 designs/b102_managed_fcs/scripts/demo_managed_session.py [--out results/102_managed/demo_session.json]

No model runs: the "agent" is this script, calling ``agent.core.dispatch`` (the same path the agent's tool calls take) so the
ownership, scope and contract rules are the code under test, not a prompt. It plays a latency task on the owned part only:

1. the request "make the CRC faster" names a frozen part: a question comes back, no scope, no edit;
2. the request "make the verdict one clock faster" resolves to ``ctrl``: scope ``ctrl``, plan written;
3. attempts that must fail: write the frozen netlist, read and write the excluded heartbeat, write ``top`` (owned, out of scope),
   change ``ctrl``'s ports (contract), drop the heartbeat from build.yaml, write project.yaml;
4. the allowed edit: remove the verdict's registered compare stage in ``fcs_ctrl.sv`` (one clock less latency), contract unchanged;
5. the provenance report.

It works on a scratch copy of the design (``--work``), so the committed design is unchanged. ``--keep-edit`` leaves the edit in
the copy for the build that follows (the before/after Vivado runs are made by the caller on the original and on the copy).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from agent.core import dispatch  # noqa: E402
from agent.core import managed as M  # noqa: E402
from agent.core.runner import LocalRunner  # noqa: E402
from agent.core.session import Session  # noqa: E402

DESIGN = ROOT / "designs" / "b102_managed_fcs"


def edited_ctrl(src: str) -> str:
    """One clock less verdict latency: pass_o takes the compare directly (no ok_r register) at the end of the frame."""
    a = src.replace("                ok_r    <= (crc_i == EXPECT);\n", "")
    a = a.replace("            if (frame_o) pass_o <= pass_o | ok_r;\n", "            if (int'(cnt) == N_WORDS + 1) pass_o <= pass_o | (crc_i == EXPECT);\n")
    a = a.replace("    logic                         ok_r;\n", "").replace(" pass_o <= 1'b0; frame_o <= 1'b0; ok_r <= 1'b0;", " pass_o <= 1'b0; frame_o <= 1'b0;")
    assert a != src and "ok_r" not in a, "the edit did not apply"
    return a


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--work", type=Path, default=ROOT / "build" / "102_demo" / "designs" / "b102_managed_fcs")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "102_managed" / "demo_session.json")
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

    # 1 and 2: requests
    r = M.resolve_request(proj, "make the CRC faster")
    log("request: make the CRC faster", scope=None if r.scope is None else r.scope.components, question=r.question)
    assert r.scope is None and "frozen" in (r.question or "")
    r = M.resolve_request(proj, "make the verdict one clock faster")
    log("request: make the verdict one clock faster", scope=r.scope.components, source=r.scope.source, notes=r.notes)
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

    # the agent reads the project as it may see it
    view = call("read_file", False, path="project.yaml")
    assert "heartbeat" not in view["output"]
    listing = call("list_files", False, path=".")
    assert "heartbeat" not in listing["output"]
    # 3: what must fail
    call("write_file", True, path="ext/crc32_d16.edf", content="(edif tampered)\n")
    call("read_file", True, path="rtl/heartbeat/heartbeat.sv")
    call("write_file", True, path="rtl/heartbeat/heartbeat.sv", content="module heartbeat; endmodule\n")
    call("write_file", True, path="rtl/fcs_top.sv", content=(work / "rtl/fcs_top.sv").read_text() + "// edit\n")
    call("write_file", True, path="project.yaml", content="schema: x\n")
    ctrl = (work / "rtl/fcs_ctrl.sv").read_text()
    call("write_file", True, path="rtl/fcs_ctrl.sv", content=ctrl.replace("input  logic        rst,", "input  logic        rst,\n    input  logic        extra,"))
    bcfg = (work / "build.yaml").read_text()
    call("write_file", True, path="build.yaml", content=bcfg.replace("  - designs/b102_managed_fcs/rtl/heartbeat/heartbeat.sv\n", ""))
    # 4: the allowed edit
    new = edited_ctrl(ctrl)
    call("write_file", False, path="rtl/fcs_ctrl.sv", content=new)
    # 5: the report
    md = M.write_provenance(proj, before)
    rep = json.loads((work / M.MANAGED_DIR / "provenance.json").read_text())
    out = {"design": "b102_managed_fcs", "scope": rep["scope"], "steps": steps, "changed_files": rep["changed_files"],
           "managed_refusals": len(rep["managed_refusals"]), "refusal_rules": sorted({r["rule"] for r in rep["managed_refusals"]}),
           "provenance_markdown": md.read_text(), "frozen_unchanged": M.sha256_file(work / "ext/crc32_d16.edf") == M.sha256_file(DESIGN / "ext/crc32_d16.edf"),
           "excluded_unchanged": M.sha256_file(work / "rtl/heartbeat/heartbeat.sv") == M.sha256_file(DESIGN / "rtl/heartbeat/heartbeat.sv")}
    assert out["changed_files"] == ["rtl/fcs_ctrl.sv"] and out["frozen_unchanged"] and out["excluded_unchanged"]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1) + "\n")
    print(f"changed: {out['changed_files']}; refusals {out['managed_refusals']} ({', '.join(out['refusal_rules'])}); wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
