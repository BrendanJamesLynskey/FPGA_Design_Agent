#!/usr/bin/env python3
"""Brief 102F on the third-party-block project: waiver files owner-only, frozen-file writes prevented, the scope in the run record, resume re-check.

    python3 designs/b102_managed_ext/scripts/demo_gaps_session.py [--out results/102f_managed_gaps/demo_session.json]

No model runs: the "agent" is this script, calling ``agent.core.dispatch``. It works on a scratch copy of ``designs/b102_managed_ext`` and plays:

1. the agent tries to write the owner's waiver files (``lint/third_party.vlt``, a new ``lint/x.vlt``, ``waivers.yaml``) and to add an in-source
   waiver to its own RTL: all refused (``managed-waiver``);
2. a tool that runs design code (here a stand-in for ``simulate``) tries to overwrite the frozen lfsr.v and the waiver file: the write itself
   fails (PermissionError), and the modes are back after the tool;
3. the same attempt from inside the sandbox container (``ContainerRunner``), where the protected files are mounted read-only: the write and
   a chmod-then-write both fail (needs docker and the ``fda-sim:2`` image; skipped and said so otherwise);
4. the scope in the run record (selected, selectable, frozen, excluded), in ``config.json`` and ``summary.json`` form;
5. the resume re-check: the same scope passes; another scope, a widened one, and a manifest edited after the run began are refused.

Like the stage 3 session it needs the agent access key outside pytest; ``agent/tests/test_102f_gaps.py`` has the same checks as tests.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from agent.core import dispatch, registry  # noqa: E402
from agent.core import managed as M  # noqa: E402
from agent.core.runner import ContainerRunner, LocalRunner, container_available  # noqa: E402
from agent.core.session import Session  # noqa: E402

DESIGN = ROOT / "designs" / "b102_managed_ext"
LFSR = "third_party/verilog-ethernet/lfsr.v"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--work", type=Path, default=ROOT / "build" / "102f_demo" / "designs" / "b102_managed_ext")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "102f_managed_gaps" / "demo_session.json")
    a = ap.parse_args(argv)
    work = a.work
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(DESIGN, work, ignore=shutil.ignore_patterns("build", "__pycache__"))
    (work / "waivers.yaml").write_text("timing_47: []\n")
    proj = M.load(work)
    steps: list[dict] = []

    def log(what: str, **kw) -> None:
        steps.append({"step": what, **kw})
        print(what, "->", {k: (str(v)[:120] if not isinstance(v, (bool, list, dict)) else v) for k, v in kw.items()})

    r = M.resolve_request(proj, "make the verdict one clock faster")
    M.start_run(proj, r.scope)
    sess = Session(design=work, root=ROOT, runner=LocalRunner(), board="kr260")

    # 1. waiver files
    for path, content in [("lint/third_party.vlt", "lint_off -rule WIDTH\n"), ("lint/x.vlt", "lint_off -rule UNUSED\n"),
                          ("waivers.yaml", "timing_47: [{text: x, count: 1, reason: y}]\n"),
                          ("rtl/fcs_ctrl.sv", (work / "rtl/fcs_ctrl.sv").read_text() + "// std-waive: STD-RST-01 not needed\n")]:
        res = dispatch(sess, "write_file", {"path": path, "content": content})
        log(f"write {path}", refused=res.get("refused"), rule=res.get("rule"), output=res.get("output"))
        assert res["refused"] and res["rule"] == "managed-waiver"

    # 2. design code under the lock
    seen: dict = {}

    def code(s, **kw):
        out = {}
        for rel in (LFSR, "lint/third_party.vlt"):
            try:
                (work / rel).write_text("changed\n")
                out[rel] = "WRITTEN"
            except PermissionError as e:
                out[rel] = f"PermissionError: {e.strerror}"
        seen.update(out)
        return {"output": json.dumps(out)}
    real_simulate = registry.TOOLS["simulate"]
    registry.TOOLS["simulate"] = replace(real_simulate, fn=code)
    before = {rel: (work / rel).read_bytes() for rel in (LFSR, "lint/third_party.vlt")}
    try:
        res = dispatch(sess, "simulate", {})
    finally:
        registry.TOOLS["simulate"] = real_simulate              # the registry is process-wide: put the real tool back
    log("a tool that runs design code writes the frozen lfsr.v and the waiver file", result=seen, files_unchanged=all((work / k).read_bytes() == v for k, v in before.items()),
        mode_after=oct(os.stat(work / LFSR).st_mode & 0o777), integrity_refusal=res.get("refused"))
    assert all(v.startswith("PermissionError") for v in seen.values())

    # 3. the container
    if container_available():
        cr = ContainerRunner(work, ROOT)
        Session(design=work, root=ROOT, runner=cr, board="kr260")
        prog = (f"import os\nfor p in ({str(work / LFSR)!r}, {str(work / 'lint/third_party.vlt')!r}):\n"
                f" for step in ('write', 'chmod+write', 'replace'):\n  try:\n"
                f"   if step == 'chmod+write': os.chmod(p, 0o644)\n"
                f"   if step == 'replace': open(p + '.new', 'w').write('x'); os.replace(p + '.new', p)\n"
                f"   else: open(p, 'w').write('changed')\n   print(os.path.basename(p), step, 'WRITTEN')\n"
                f"  except OSError as e: print(os.path.basename(p), step, 'refused:', e.strerror)\n")
        rr = cr.run("simulate", ["python3", "-c", prog], ROOT, timeout=120)
        log("the same attempts inside the sandbox container (protected files mounted read-only)", returncode=rr.returncode, output=rr.stdout.strip().splitlines(), stderr=rr.stderr[-200:])
        assert all(b == (work / k).read_bytes() for k, b in before.items())
    else:
        log("container step skipped: docker or the fda-sim:2 image is not available here")

    # 4. the scope record
    rec = M.scope_record(M.load(work))
    log("scope record (config.json and summary.json carry it)", scope=rec)

    # 5. the resume re-check
    p = M.load(work)
    log("resume, same scope", problems=M.check_resume(p, rec, ["ctrl"]))
    log("resume, another scope", problems=M.check_resume(p, rec, ["crc_adapter"]))
    log("resume, a wider scope", problems=M.check_resume(p, rec, ["ctrl", "crc_adapter"]))
    log("resume, scope naming the frozen block", problems=M.check_resume(p, rec, ["lfsr"]))
    assert M.check_resume(p, rec, ["ctrl"]) == [] and all(M.check_resume(p, rec, x) for x in (["crc_adapter"], ["ctrl", "crc_adapter"], ["lfsr"]))
    (work / "project.yaml").write_text((work / "project.yaml").read_text() + "agent_may_write_waivers: true\n")
    log("resume after the manifest was edited", problems=M.check_resume(M.load(work), rec))
    assert any("project.yaml changed" in x for x in M.check_resume(M.load(work), rec))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"design": "b102_managed_ext", "steps": steps}, indent=1) + "\n")
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
