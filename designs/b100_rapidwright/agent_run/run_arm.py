"""Stage 2 of brief 100: one agent run on the transmit chain with the RapidWright tools (arm A) or without them (arm B).

    The access key comes from <worktree>/.env (the caller copies it; never printed). python3 designs/b100_rapidwright/agent_run/run_arm.py a|b [--max-turns N]

The agent is Claude Sonnet 5.5 through the Claude Code arm of brief 05c (headless `claude -p`, Max plan, our MCP tools only, no shell, no web).
Both arms get the same design (a copy of rtl/chain_top.sv with brief 96's mac64_tx and pcs_tx and a bare GT), the same task text, the
same turn and wall budget, and the tools build, report, read_file, write_file, list_files, check_constraints; arm A also gets rw_status,
rw_relocate_block, rw_place_chain, rw_route, rw_referee. Vivado's timing (build's reports, rw_referee) is the only judge. Results go to
results/b100/agent/<arm>/ (the stream, the tool audit log, the final reports); the design copies and their builds stay in
designs/b100_rapidwright/agent_run/arm_<x>/ (build/ is git-ignored)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from agent.claude_code_arm.arm import MCP_NAME, TOKEN_FILE, isolated_env, oauth_token  # noqa: E402

MODEL = "claude-sonnet-5-5"
BASE_TOOLS = ["read_file", "write_file", "list_files", "build", "report", "check_constraints"]
RW_TOOLS = ["rw_status", "rw_relocate_block", "rw_place_chain", "rw_route", "rw_referee"]
PERIOD_NS = 3.2
SRC = {"b96_pkg.sv": "designs/b96_kr260_10g/rtl/b96_pkg.sv", "pcs_tx.sv": "designs/b96_kr260_10g/rtl/pcs_tx.sv",
       "mac64_tx.sv": "designs/b96_kr260_10g/rtl/mac64_tx.sv", "chain_top.sv": "designs/b100_rapidwright/rtl/chain_top.sv"}

SYSTEM = """You are a physical-design engineer working through tools only (no shell). The design is a 64-bit Ethernet transmit chain for a
Kria K26 (xck26-sfvc784-2LV-c): a MAC (mac64_tx) hands a word to a 10GBASE-R PCS (pcs_tx), whose output register feeds the TXDATA pins of
a GTHE4 transceiver channel (u_gt, site GTHE4_CHANNEL_X0Y6). One clock, `clk`. Vivado 2026.1 is the only judge of timing: use its
reports. Never claim a result you did not read from a Vivado report or a tool result."""

TASK = f"""Goal: make the transmit chain as fast as you can by physical means only, because its latency in nanoseconds is the number of
clock cycles on the path (fixed at two: the MAC's output registers x_d/x_c, then the PCS's gt_d register, then the GT's TXDATA pins)
times the clock period, so a shorter achievable period is a lower latency. The clock constraint in design.xdc is {PERIOD_NS} ns.

Rules:
- Do not change the RTL (rtl/*.sv): no new registers, no logic change. Placement and routing, and constraints, only.
- Report the worst setup slack (WNS) of the whole design and of the paths into the GT's TXDATA pins and from the MAC to the PCS, before and
  after each change, as Vivado reports them. The achieved period is the constraint minus WNS.
- You have a budget of {{turns}} tool calls and about {{minutes}} minutes of wall time. A build takes about six minutes.
Start with a build of the design as it is (build until=route), read the timing summary, then improve it. End with a short report: what you
tried, what Vivado measured for each attempt (WNS and the paths above), the best result, and what did not work."""


def stage_arm(arm: str) -> Path:
    d = ROOT / "designs" / "b100_rapidwright" / "agent_run" / f"arm_{arm}"
    if d.exists():
        shutil.rmtree(d)
    (d / "rtl").mkdir(parents=True)
    for n, rel in SRC.items():
        shutil.copy(ROOT / rel, d / "rtl" / n)
    xdc = (ROOT / "designs/b100_rapidwright/chain.xdc").read_text()
    (d / "design.xdc").write_text(xdc + f"create_clock -name clk -period {PERIOD_NS} [get_ports clk]\n")
    rel = f"designs/b100_rapidwright/agent_run/arm_{arm}"
    (d / "build.yaml").write_text(
        "# How flow/run_vivado.sh builds the arm's design (brief 100, stage 2).\ntop: chain_top\npart: xck26-sfvc784-2LV-c\nboard: kr260\n"
        f"sources:\n  - {rel}/rtl/b96_pkg.sv\n  - {rel}/rtl/pcs_tx.sv\n  - {rel}/rtl/mac64_tx.sv\n  - {rel}/rtl/chain_top.sv\n"
        f"constraints:\n  - {rel}/design.xdc\ngenerics: {{}}\n")
    return d


def main() -> int:
    arm = sys.argv[1]
    assert arm in ("a", "b")
    turns = int(sys.argv[sys.argv.index("--max-turns") + 1]) if "--max-turns" in sys.argv else 40
    minutes = int(sys.argv[sys.argv.index("--minutes") + 1]) if "--minutes" in sys.argv else 120
    d = stage_arm(arm)
    out = ROOT / "results" / "b100" / "agent" / arm
    out.mkdir(parents=True, exist_ok=True)
    tools = BASE_TOOLS + (RW_TOOLS if arm == "a" else [])
    token = oauth_token()
    assert token, f"no Claude Code token ({TOKEN_FILE})"
    work = Path(tempfile.mkdtemp(prefix="fda_b100_"))
    tf = work / "tools.yaml"
    tf.write_text("path: []\nenv:\n  FDA_VIVADO_MAX: '2'\n  FDA_RAPIDWRIGHT: '1'\n")        # builds may run beside one other session's Vivado
    env = {"PYTHONPATH": str(ROOT), "PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""), "FDA_TOOLS_FILE": str(tf), "FDA_RAPIDWRIGHT": "1"}
    if os.environ.get("FDA_ACCESS_KEY"):                  # else the server reads the git-ignored .env at the repo root (the key is never written here)
        env["FDA_ACCESS_KEY"] = "${FDA_ACCESS_KEY}"
    mcp = {"mcpServers": {MCP_NAME: {"command": sys.executable, "args": [
        "-m", "agent.mcp_server", "--design", str(d), "--board", "kr260", "--role", "rtl", "--stage", "timing-closure",
        "--tools", ",".join(tools)], "env": env}}}
    (work / "mcp.json").write_text(json.dumps(mcp))
    task = TASK.format(turns=turns, minutes=minutes)
    argv = ["claude", "-p", task, "--output-format", "stream-json", "--verbose", "--system-prompt", SYSTEM, "--tools", "",
            "--mcp-config", str(work / "mcp.json"), "--strict-mcp-config", "--allowedTools", *[f"mcp__{MCP_NAME}__{t}" for t in tools],
            "--permission-mode", "dontAsk", "--setting-sources", "", "--disable-slash-commands", "--no-session-persistence",
            "--model", MODEL, "--max-turns", str(turns)]
    (out / "task.txt").write_text(SYSTEM + "\n\n" + task + "\n\ntools: " + ", ".join(tools) + "\n")
    t0 = time.time()
    try:
        p = subprocess.run(argv, cwd=work, env=isolated_env(work, token), capture_output=True, text=True, timeout=minutes * 60,
                           stdin=subprocess.DEVNULL)
        stream, err = p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        stream, err = (e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout or ""), "timeout"
    (out / "stream.jsonl").write_text(stream)
    (out / "meta.json").write_text(json.dumps({"arm": arm, "model": MODEL, "tools": tools, "max_turns": turns, "minutes": minutes,
                                               "wall_s": round(time.time() - t0, 1), "stderr_tail": err[-400:]}, indent=1))
    for line in stream.splitlines():                       # the final message and the turn count, from the stream, into result.json
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "result":
            (out / "result.json").write_text(json.dumps({"text": ev.get("result"), "num_turns": ev.get("num_turns"), "is_error": ev.get("is_error"),
                                                          "usage": ev.get("usage"), "plan_cost_estimate_usd": ev.get("total_cost_usd")}, indent=1))
    for src, dst in ((d / "build" / "audit.jsonl", "audit.jsonl"), (d / "rtl" / "chain_top.sv", "final_chain_top.sv"), (d / "design.xdc", "final_design.xdc")):
        if src.is_file():
            shutil.copy(src, out / dst)
    for f in list((d / "build" / "base").glob("rw/*_run.json")) + list((d / "build" / "base").glob("rw/*_chain.json")) + \
            list((d / "build" / "base").glob("run.json")) + list((d / "build" / "base").glob("timing_summary.rpt")):
        shutil.copy(f, out / f.name.replace("run.json", "build_run.json") if f.name == "run.json" else out / f.name)
    shutil.rmtree(work, ignore_errors=True)
    print("done", arm, round(time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
