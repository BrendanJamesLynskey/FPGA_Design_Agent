"""Agent tools for the on-chip AXI transactor (axi_tx/): check a transaction program, run it in simulation, run it on
the board. The program is the format of axi_tx/host/program.py, given inline as a mapping (or YAML text). No tool here
takes a path, a Tcl command or a cable serial. The board tool needs the debug stage, a passing power check and hardware
budget, programs volatile configuration only, and takes the board lock (it refuses while the board is in use).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

from agent.core.registry import tool
from agent.core.security import SecurityError
from agent.core.session import Session

PY = sys.executable
PROGRAM = {"description": "A transaction program (axi_tx/host/program.py): a mapping with name, target (bram | periph), "
                          "optional lite_bug / stream_bug, and steps; or the same as YAML text.",
           "type": ["object", "string"]}


def _assemble(program: Any):
    from axi_tx.host.program import ProgramError, assemble
    spec = yaml.safe_load(program) if isinstance(program, str) else program
    try:
        return assemble(spec), spec
    except ProgramError as e:
        raise SecurityError("axi-program", f"the program does not fit the format: {e}") from None


def _out_dir(s: Session, name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)[:40] or "program"
    d = s.design / "build" / "axi_tx" / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


@tool("axi_program_check", "Assemble an AXI transaction program for the on-chip transactor (axi_tx) and run its "
      "transaction-level model: the instruction count, the disassembly and the predicted transactions and verdict counters. "
      "No simulator, no board.", {"program": PROGRAM}, required=["program"])
def axi_program_check(s: Session, program: Any) -> dict:
    from axi_tx.host import model
    from axi_tx.host.program import disassemble
    prog, _ = _assemble(program)
    pred = model.run(prog)
    dis = disassemble(prog.words)
    return {"ok": pred.ended == "done", "output": "\n".join(dis[:80]), "instructions": prog.n_instr,
            "predicted": pred.counts, "ended": pred.ended, "first_transactions": pred.txns[:16]}


@tool("axi_simulate", "Run an AXI transaction program on the transactor RTL in simulation (cocotb + Icarus: the "
      "transactor, the protocol checkers, the scoreboard, our AXI4-Lite peripheral, a memory model and the stream FIFO), "
      "through the same host code as the board. Returns verdicts, rule counts, coverage and latency counters.",
      {"program": PROGRAM}, required=["program"])
def axi_simulate(s: Session, program: Any) -> dict:
    prog, spec = _assemble(program)
    d = _out_dir(s, prog.name)
    (d / "program.yaml").write_text(yaml.safe_dump(spec, sort_keys=False))
    env = {"AXI_TX_PROGRAM": str(d / "program.yaml"), "AXI_TX_RESULT": str(d / "sim_result.json")}
    r = s.runner.run("axi_simulate", [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                       str(s.root / "axi_tx" / "tests" / "test_59a_program_rtl.py")], s.root, env=env,
                     timeout=1200)
    res = json.loads((d / "sim_result.json").read_text()) if (d / "sim_result.json").is_file() else None
    keep = {k: res[k] for k in ("status", "n_txn", "digest", "sb_checked", "sb_mism", "exp_mism", "resp_mism",
                                "lite_rules", "stream_rules", "sink", "lite_mon", "stream_mon", "model_compare")} if res else None
    return {"ok": r.returncode == 0 and res is not None, "output": (r.stdout + r.stderr)[-4000:], "result": keep}


@tool("axi_board_run", "Run an AXI transaction program on the board's transactor design (designs/b59a_axi_tx, SRAM "
      "only, by the local board file's cable serial), with operating conditions logged before and after. Needs stage "
      "configuration-and-debug, a passing power_ok for that build, and hardware budget.",
      {"program": PROGRAM}, required=["program"], hardware=True)
def axi_board_run(s: Session, program: Any) -> dict:
    from flow import hw
    if s.stage != "configuration-and-debug":
        raise SecurityError("hardware-stage", f"axi_board_run needs the stage configuration-and-debug (now {s.stage})")
    bdir = s.root / "designs" / "b59a_axi_tx" / "build" / "base"
    if not list(bdir.glob("*.bit")):
        raise SecurityError("hardware-build", "no b59a_axi_tx bitstream; build it first")
    pw = hw.power_ok(bdir, s.board)
    if not pw["pass"]:
        raise SecurityError("hardware-power", f"power_ok failed: {pw['why']}; not programming")
    prog, spec = _assemble(program)
    s.hw.charge("axi_board_run")
    d = _out_dir(s, prog.name)
    (d / "program.yaml").write_text(yaml.safe_dump(spec, sort_keys=False))
    plan = d / "plan.yaml"
    plan.write_text(yaml.safe_dump({"runs": [{"path": str(d / "program.yaml"), "tag": prog.name, "expect": {}}]}))
    # one board job at a time: the tool takes the board lock itself, and refuses while anyone else holds it
    import time
    from hil.instruments.board_lock import BoardBusy, BoardLock
    lock = BoardLock(f"FPGA agent: axi_board_run {prog.name}, {time.strftime('%H:%M')}, expected end "
                     f"{time.strftime('%H:%M', time.localtime(time.time() + 1800))}")
    try:
        lock.take()
    except BoardBusy as e:
        raise SecurityError("hardware-board-busy", f"the board is in use; not starting ({e})") from None
    try:
        r = s.runner.run("axi_board_run", [PY, str(s.root / "axi_tx" / "host" / "run_board.py"), "--plan", str(plan),
                                           "--json", str(d / "board_result.json")], s.root, timeout=1800)
    finally:
        lock.release()
    res = json.loads((d / "board_result.json").read_text()) if (d / "board_result.json").is_file() else None
    return {"ok": r.returncode in (0, 1) and res is not None, "output": (r.stdout + r.stderr)[-4000:],
            "result": res and {"inside_roc": res.get("inside_roc"), "runs": [{k: x.get(k) for k in (
                "status", "summary", "lite_rules", "stream_rules", "model_compare", "capture")} for x in res["runs"]]}}
