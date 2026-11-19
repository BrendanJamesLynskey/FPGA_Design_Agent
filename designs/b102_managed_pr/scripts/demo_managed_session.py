#!/usr/bin/env python3
"""A scripted session through the agent's real tool surface on the placed-and-routed managed project (brief 102, stage 2 demonstration).

    python3 designs/b102_managed_pr/scripts/demo_managed_session.py [--out results/102_managed_pr/demo_session.json]
                                                                    [--rapidwright CHECKPOINT]

No model runs: the "agent" is this script, calling ``agent.core.dispatch`` (the path the agent's tool calls take), so the ownership, scope and
keep-out rules are the code under test. It plays a placement request: "place the owned logic around the locked block".

1. the request "make the block faster" names a frozen part: a question comes back, no scope, no edit;
2. the scope ``top,sink`` (the owned logic and the constraints file) is set and the plan written;
3. attempts that must fail: write the checkpoint and its stub, write a pblock over the block, a LOC inside it, a placement property on its
   cells, rw_place_chain and rw_route aimed at it, a whole-design RWRoute, relocating a checkpoint that may hold it, write an out-of-scope file;
4. the allowed work: a pblock for the sink beside the block in design.xdc;
5. with ``--rapidwright <routed checkpoint with the block>`` (needs RapidWright, Vivado 2026.1 and a heavy slot): the real tools. rw_place_chain on
   the owned cells re-places them around the block, a leaf-name pattern that would reach the block is refused by the script itself (it sees the
   real cell names), Vivado routes the result (rw_referee) and the written checkpoint is read back: the block's cells, BELs and routing equal the
   delivered ones and no cell of ours sits inside the keep-out region;
6. the provenance report.

It works on a scratch copy of the design (``--work``), so the committed design is unchanged.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ["FDA_RAPIDWRIGHT"] = "1"           # the rw_* tools register at import only with this switch

from agent.core import dispatch  # noqa: E402
from agent.core import managed as M  # noqa: E402
from agent.core import rapidwright_tools as rwt  # noqa: E402
from agent.core.runner import LocalRunner  # noqa: E402
from agent.core.session import Session  # noqa: E402
from flow import managed_placed as MP  # noqa: E402

importlib.reload(rwt)
DESIGN = ROOT / "designs" / "b102_managed_pr"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--work", type=Path, default=ROOT / "build" / "102_demo2" / "designs" / "b102_managed_pr")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "102_managed_pr" / "demo_session.json")
    ap.add_argument("--rapidwright", type=Path, help="a routed checkpoint that holds the block (the placement run's p0_routed.dcp): run the real tools on it")
    a = ap.parse_args(argv)
    work = a.work
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(DESIGN, work, ignore=shutil.ignore_patterns("build", "__pycache__"))
    proj = M.load(work)
    steps: list[dict] = []

    def log(what: str, **kw) -> None:
        steps.append({"step": what, **kw})
        print(what, "->", {k: (str(v)[:120] if not isinstance(v, (bool, list)) else v) for k, v in kw.items()})

    r = M.resolve_request(proj, "make the block faster")
    log("request: make the block faster", scope=None if r.scope is None else r.scope.components, question=r.question)
    assert r.scope is None and "frozen" in (r.question or "")
    r = M.resolve_request(proj, "", ["top", "sink"])
    log("scope: top,sink", scope=r.scope.components, source=r.scope.source)
    M.start_run(proj, r.scope)
    sess = Session(design=work, root=ROOT, runner=LocalRunner(), board="kr260")
    before = {p.relative_to(work).as_posix(): M.sha256_file(p) for c in proj.components for p in M.component_files(proj, c)}

    def call(tool: str, expect_refused: bool | None, label: str = "", **kw) -> dict:
        res = dispatch(sess, tool, kw)
        log(f"{tool} {label or kw.get('path', '')}".strip(), ok=res["ok"], refused=res["refused"], rule=res.get("rule"), output=res["output"][:150])
        if expect_refused is not None:
            assert res["refused"] is expect_refused, (tool, kw, res)
        return res

    xdc = (work / "design.xdc").read_text()
    # 3: what must fail
    call("write_file", True, path="ext/pcs_unit_p0.dcp", content="tampered")
    call("write_file", True, path="ext/pcs_unit_bb.sv", content="module pcs_unit; endmodule\n")
    call("write_file", True, "pblock over the block", path="design.xdc", content=xdc + "create_pblock pb_s\nresize_pblock pb_s -add SLICE_X30Y75:SLICE_X40Y80\n")
    call("write_file", True, "LOC inside the region", path="design.xdc", content=xdc + "set_property LOC SLICE_X28Y80 [get_cells u_sink/div_reg[0]]\n")
    call("write_file", True, "placement property on the block", path="design.xdc", content=xdc + "set_property DONT_TOUCH true [get_cells u_blk]\n")
    call("write_file", True, path="rtl/pr_src.sv", content=(work / "rtl/pr_src.sv").read_text() + "// edit\n")   # owned, outside the scope
    call("write_file", True, path="project.yaml", content="schema: x\n")
    ck = "post_route.dcp"
    (work / "build" / "base").mkdir(parents=True, exist_ok=True)
    (work / "build" / "base" / ck).write_bytes(b"placeholder for the argument checks")
    call("rw_place_chain", True, "cells u_blk/*", checkpoint=ck, output="o.dcp", cells=["u_blk/*"], anchor="SLICE_X30Y80")
    call("rw_place_chain", True, "cells *", checkpoint=ck, output="o.dcp", cells=["*"], anchor="SLICE_X30Y80")
    call("rw_route", True, "mode full", checkpoint=ck, output="o.dcp", mode="full")
    call("rw_route", True, "net inside the block", checkpoint=ck, output="o.dcp", mode="nets", nets=["u_blk/u_core/adv"])
    call("rw_relocate_block", True, "a checkpoint that may hold the block", checkpoint=ck, output="o.dcp", target_site="SLICE_X29Y20")
    (work / "build" / "base" / ck).unlink()
    # 4: the allowed work
    call("write_file", False, "a pblock for the sink beside the block", path="design.xdc",
         content=xdc + "create_pblock pb_sink\nresize_pblock pb_sink -add SLICE_X38Y72:SLICE_X45Y90\nadd_cells_to_pblock pb_sink [get_cells u_sink]\n")
    out: dict = {"design": "b102_managed_pr"}
    # 5: the real tools
    if a.rapidwright:
        b = work / "build" / "base"
        shutil.copy(a.rapidwright, b / ck)
        cfg_cells = ["u_sink/*", "u_src/*"]
        pl = call("rw_place_chain", False, "owned cells around the block", checkpoint=ck, output="placed.dcp", cells=cfg_cells, anchor="SLICE_X29Y80",
                  window_cols=40, window_rows=30, iterations=40000)
        leaf = call("rw_place_chain", None, "leaf-name pattern */sh_reg* (script-level refusal)", checkpoint=ck, output="leaf.dcp", cells=["*/sh_reg*"],
                    anchor="SLICE_X29Y80")
        log("script-level check", ok=leaf["ok"], text=leaf["output"][:200])
        assert leaf["ok"] is False and "protected" in leaf["output"]
        ref = call("rw_referee", False, "route and time the re-placed design", checkpoint="placed.dcp", route=True)
        out["place_result"] = pl.get("result")
        out["referee"] = ref.get("result")
        routed = b / "rw" / "placed_routed.dcp"
        # read the written checkpoint back: the block as delivered into the run against the block in the file
        ref_files = a.rapidwright.parent / (a.rapidwright.name.replace("_routed.dcp", ""))
        env = {**os.environ, "FDA_PR_DCP": str(routed), "FDA_PR_CELL": "u_blk", "FDA_PR_OUT": str(work / "build" / "rw_dump.txt"),
               "FDA_PR_NETS": f"{ref_files}_routes_before.txt"}
        from flow import version_pin
        rr = subprocess.run([version_pin.vivado_path(), "-mode", "batch", "-nojournal", "-nolog", "-source", str(ROOT / "flow" / "managed_block_dump.tcl")],
                            cwd=work / "build", env=env, capture_output=True, text=True, timeout=3600)
        assert rr.returncode == 0, rr.stdout[-400:]
        chk = MP.dump_check((work / "build" / "rw_dump.txt").read_text(), Path(f"{ref_files}_sites_before.txt"), Path(f"{ref_files}_routes_before.txt"),
                            M.slice_rect(proj.component("blk").placement["region"]))
        log("the written checkpoint against the delivered block", **{k: chk[k] for k in ("cells_unchanged", "routes_unchanged", "block_cells", "block_nets", "other_cells_inside_region_count")})
        out["written_checkpoint"] = chk
    # 6: the report
    md = M.write_provenance(proj, before)
    rep = json.loads((work / M.MANAGED_DIR / "provenance.json").read_text())
    out.update({"scope": rep["scope"], "steps": steps, "changed_files": rep["changed_files"], "managed_refusals": len(rep["managed_refusals"]),
                "refusal_rules": sorted({x["rule"] for x in rep["managed_refusals"]}), "provenance_markdown": md.read_text(),
                "frozen_unchanged": all(M.sha256_file(work / p) == M.sha256_file(DESIGN / p) for p in ("ext/pcs_unit_p0.dcp", "ext/pcs_unit_bb.sv"))})
    assert out["changed_files"] == ["design.xdc"] and out["frozen_unchanged"]
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1, default=str) + "\n")
    print(f"changed: {out['changed_files']}; refusals {out['managed_refusals']} ({', '.join(out['refusal_rules'])}); wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
