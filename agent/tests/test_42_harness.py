"""Brief 42 harness arms H1 (context management) and H2 (hang protection). Off by default: the baseline is unchanged."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from agent.core import dispatch
from agent.core.cocotb_lint import declared_budget_ns, h2_wall_limit, unbounded_waits
from agent.core.runner import RunResult
from agent.core.session import ROOT, Session
from agent.graph.context import OFFLOAD_CHARS, offload_result
from agent.graph.run import Config

# ---- config ------------------------------------------------------------------------------------------------------


def test_arms_default_empty_and_parse() -> None:
    c = Config(spec_md=Path("spec.md"), name="x")
    assert c.arms == ()
    assert Config(spec_md=Path("spec.md"), name="x", harness_arms="h1, H2").arms == ("H1", "H2")
    assert Session.__dataclass_fields__["harness_arms"].default == ()


# ---- H1 ----------------------------------------------------------------------------------------------------------


def test_small_result_is_unchanged(tmp_path: Path) -> None:
    res = {"ok": True, "tool": "lint", "output": "fine"}
    assert offload_result(res, tmp_path, "lint", 1) == json.dumps(res)
    assert not (tmp_path / "build").exists()


def test_large_result_is_offloaded_with_head_tail_and_path(tmp_path: Path) -> None:
    out = "HEAD-" + "x" * 20000 + "-TAIL"
    res = {"ok": False, "tool": "simulate", "returncode": 1, "output": out, "log_tail": "t" * 4000}
    text = offload_result(res, tmp_path, "simulate", 7)
    p = json.loads(text)
    assert len(text) < OFFLOAD_CHARS
    assert p["output_head"].startswith("HEAD-") and p["output_tail"].endswith("-TAIL")
    assert p["returncode"] == 1 and p["full_result"] == "/build/tool_results/007_simulate.json"
    assert p["fields_in_file_only"] == ["log_tail"]
    assert json.loads((tmp_path / "build" / "tool_results" / "007_simulate.json").read_text()) == res


def test_offloaded_file_is_readable_through_the_rtl_jail(wd: Path) -> None:
    from agent.graph.roles import RoleJail
    s = Session(design=wd, root=wd.parents[1])
    offload_result({"output": "y" * 9000, "ok": True}, wd, "build", 1)
    assert RoleJail(s.jail, "rtl").resolve("build/tool_results/001_build.json").is_file()


def test_h1_middleware_takes_the_default_slot() -> None:
    import deepagents.graph as dg
    from deepagents import create_deep_agent
    from deepagents.backends import StateBackend

    from agent.graph.context import SUMMARY_TRIGGER_TOKENS, summarisation_middleware
    from agent.tools.harness_audit import Client, Meter
    from agent.graph.llm import chat_model
    cap = {}
    orig = dg.create_agent

    def spy(*a, **k):
        cap["mw"] = k["middleware"]
        return orig(*a, **k)

    dg.create_agent = spy
    try:
        m = chat_model(Client(), Meter(), [])
        create_deep_agent(model=m, tools=[], system_prompt="x", middleware=[summarisation_middleware(m, StateBackend())])
    finally:
        dg.create_agent = orig
    summ = [x for x in cap["mw"] if x.name == "SummarizationMiddleware"]
    assert len(summ) == 1                                     # replaced, not added
    assert summ[0]._lc_middleware.trigger == ("tokens", SUMMARY_TRIGGER_TOKENS) if hasattr(summ[0], "_lc_middleware") else True


# ---- H2: the static check ---------------------------------------------------------------------------------------


def _lint(tmp_path: Path, src: str) -> list[dict]:
    f = tmp_path / "test_x.py"
    head = "".join(x + "\n" for x in src.splitlines() if x.startswith(("import ", "from ")))
    body = "\n".join(x for x in src.splitlines() if not x.startswith(("import ", "from ")))
    f.write_text(head + textwrap.dedent(body))
    return unbounded_waits(f)


HEAD = "import cocotb\nfrom cocotb.triggers import RisingEdge, Timer, FallingEdge\n"


def test_lint_flags_unbounded_edge_wait(tmp_path: Path) -> None:
    r = _lint(tmp_path, HEAD + """
        @cocotb.test()
        async def t(dut):
            while dut.done.value == 0:
                await RisingEdge(dut.clk)
        """)
    assert len(r) == 1 and r[0]["function"] == "t" and r[0]["waits"] == ["RisingEdge"]


def test_lint_flags_helper_while_true(tmp_path: Path) -> None:
    assert _lint(tmp_path, HEAD + """
        async def wait_ack(dut):
            while True:
                await RisingEdge(dut.clk)
                if dut.ack.value: break
        """)


@pytest.mark.parametrize("body", [
    "n = 0\n    while n < 1000:\n        await RisingEdge(dut.clk)\n        n += 1",
    "n = 0\n    while True:\n        await RisingEdge(dut.clk)\n        n += 1\n        if n > 500:\n            raise AssertionError('timeout')",
    "for _ in range(100):\n        await RisingEdge(dut.clk)",
    "while dut.q.value != 3:\n        await RisingEdge(dut.clk)\n        assert cycles() < 5",   # not recognised: flagged below
])
def test_lint_accepts_bounded_loops(tmp_path: Path, body: str) -> None:
    r = _lint(tmp_path, HEAD + f"\n@cocotb.test()\nasync def t(dut):\n    {body}\n")
    assert bool(r) == body.startswith("while dut.q")


def test_lint_accepts_clock_driver_and_declared_timeout(tmp_path: Path) -> None:
    assert not _lint(tmp_path, HEAD + """
        async def clk(dut):
            while True:
                dut.clk.value = 0
                await Timer(5, unit="ns")
                dut.clk.value = 1
                await Timer(5, unit="ns")
        """)
    assert not _lint(tmp_path, HEAD + """
        @cocotb.test(timeout_time=2, timeout_unit="ms")
        async def t(dut):
            while dut.done.value == 0:
                await RisingEdge(dut.clk)
        """)
    assert not _lint(tmp_path, HEAD + "from cocotb.triggers import with_timeout\n" + """
        async def t(dut):
            while dut.done.value == 0:
                await RisingEdge(dut.clk)
        """)


def test_lint_has_no_false_alarm_on_the_repo_benches() -> None:
    """Every committed bench that is not a deliberate trap passes the check (counted in results/42_workflows)."""
    files = [f for pat in ("designs/*/tests/*.py", "benchmark/tasks/*/ref/tests/*.py", "benchmark/tasks/*/hidden/*.py")
             for f in ROOT.glob(pat)]
    flagged = [str(f.relative_to(ROOT)) for f in files if unbounded_waits(f)]
    assert not flagged, flagged


def test_wall_limit_rules(tmp_path: Path) -> None:
    (tmp_path / "t.py").write_text(HEAD + '@cocotb.test(timeout_time=10, timeout_unit="ms")\nasync def t(dut): pass\n')
    assert declared_budget_ns(tmp_path) == 1e7
    assert h2_wall_limit(tmp_path, None) == (220, "declared simulation-time budget 10000000 ns")
    empty = tmp_path / "e"
    empty.mkdir()
    assert h2_wall_limit(empty, None)[0] == 600
    assert h2_wall_limit(empty, 30.0)[0] == 240
    assert h2_wall_limit(empty, 1000.0)[0] == 900
    assert h2_wall_limit(empty, 30.0, coverage=True)[0] == 480


# ---- H2: simulate ------------------------------------------------------------------------------------------------


def _bench(session: Session, body: str) -> None:
    t = session.design / "tests"
    t.mkdir(exist_ok=True)
    (t / "test_t1dc_rtl.py").write_text("def test_x(): pass\n")
    (t / "bench.py").write_text(HEAD + body)


def test_simulate_unchanged_without_h2(session: Session) -> None:
    _bench(session, "\n@cocotb.test()\nasync def t(dut):\n    while dut.d.value == 0:\n        await RisingEdge(dut.clk)\n")
    seen = {}

    class R:
        def run(self, kind, argv, cwd, env=None, timeout=600):
            if kind == "simulate":
                seen["argv"], seen["timeout"] = argv, timeout
            return RunResult(0, "1 passed", "", 0.1)

    session.runner = R()
    assert dispatch(session, "simulate", {"sim": "icarus"})["ok"]
    assert "sim_watchdog" not in " ".join(seen["argv"]) and seen["timeout"] == 1800


def test_h2_refuses_unbounded_wait_without_running(session: Session) -> None:
    session.harness_arms = ("H2",)
    _bench(session, "\n@cocotb.test()\nasync def t(dut):\n    while dut.d.value == 0:\n        await RisingEdge(dut.clk)\n")
    class R:
        def run(self, kind, argv, cwd, env=None, timeout=600):
            assert kind != "simulate", "the simulator must not start"
            return RunResult(0, "", "", 0.0)

    session.runner = R()
    r = dispatch(session, "simulate", {"sim": "icarus"})
    assert not r["ok"] and r["kind"] == "unbounded_wait" and "bench.py:" in r["output"]


def test_h2_wraps_the_run_and_returns_a_structured_hang(session: Session) -> None:
    session.harness_arms = ("H2",)
    _bench(session, "\n@cocotb.test()\nasync def t(dut):\n    for _ in range(10):\n        await RisingEdge(dut.clk)\n")
    hang = {"limit_s": 600, "test": {"name": "bench.t", "index": 2, "of": 3}, "sim_time_ns": 12345.0,
            "sim_time_advancing": True, "tail": "last log line"}
    seen = {}

    class R:
        def run(self, kind, argv, cwd, env=None, timeout=600):
            if kind != "simulate":
                return RunResult(0, "", "", 0.0)
            seen["argv"], seen["timeout"] = argv, timeout
            return RunResult(124, "partial\nFDA_HANG " + json.dumps(hang) + "\n", "", 600.0)

    session.runner = R()
    r = dispatch(session, "simulate", {"sim": "icarus"})
    assert "sim_watchdog.py" in seen["argv"][1] and "--limit" in seen["argv"] and seen["timeout"] == 690
    assert not r["ok"] and r["kind"] == "sim_hang" and r["hang"]["sim_time_ns"] == 12345.0
    assert "hung at simulation time 12345 ns in test bench.t" in r["output"] and "still advancing" in r["output"]


# ---- H2: the watchdog itself -------------------------------------------------------------------------------------


def test_parse_sim_log() -> None:
    from flow.sim_watchdog import parse_sim_log
    log = ("     -.--ns INFO     gpi   x\n    0.00ns INFO     cocotb.regression   running bench.a (1/2)\n"
           "  100.00ns INFO     cocotb.regression   bench.a passed\n  200.00ns INFO     cocotb.regression   running bench.b (2/2)\n"
           "  3.50us INFO     bench   still going\n   continuation line\n")
    p = parse_sim_log(log)
    assert p["test"] == {"name": "bench.b", "index": 2, "of": 2} and p["sim_time_ns"] == 3500.0


def test_watchdog_kills_a_sleeping_command_and_reports(tmp_path: Path) -> None:
    (tmp_path / "build" / "x").mkdir(parents=True)
    (tmp_path / "build" / "x" / "sim.log").write_text("    0.00ns INFO     cocotb.regression   running m.t (1/1)\n 50.00ns INFO  m  hi\n")
    p = subprocess.run([sys.executable, str(ROOT / "flow" / "sim_watchdog.py"), "--limit", "2", "--heartbeat", "0.5", "--root",
                        str(tmp_path), "--", sys.executable, "-c", "import time; time.sleep(60)"],
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 124
    h = json.loads(p.stdout.split("FDA_HANG ", 1)[1])
    assert h["test"]["name"] == "m.t" and h["sim_time_ns"] == 50.0 and h["sim_time_advancing"] is False


def test_watchdog_passes_through_a_normal_exit(tmp_path: Path) -> None:
    p = subprocess.run([sys.executable, str(ROOT / "flow" / "sim_watchdog.py"), "--limit", "20", "--root", str(tmp_path), "--",
                        sys.executable, "-c", "print('ok'); raise SystemExit(3)"], capture_output=True, text=True, timeout=30)
    assert p.returncode == 3 and "ok" in p.stdout


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="Icarus not installed")
def test_watchdog_on_a_real_cocotb_hang(tmp_path: Path) -> None:
    """The brief 24 B1 failure in small: a bench that waits on a value the design never reaches."""
    (tmp_path / "cnt.sv").write_text("module cnt(input logic clk, input logic rst, output logic [7:0] q);\n"
                                     "always_ff @(posedge clk) if (rst) q <= 0; else q <= q + 1;\nendmodule\n")
    (tmp_path / "hangbench.py").write_text(HEAD + """
@cocotb.test()
async def test_ok(dut):
    await Timer(10, unit="ns")

@cocotb.test()
async def test_hang(dut):
    from cocotb.clock import Clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst.value = 0
    while True:
        await RisingEdge(dut.clk)
""")
    (tmp_path / "test_run_rtl.py").write_text(
        "from cocotb_tools.runner import get_runner\n"
        "def test_run():\n    r = get_runner('icarus')\n"
        "    r.build(sources=['cnt.sv'], hdl_toplevel='cnt', build_dir='build/b', always=True, timescale=('1ns','1ps'))\n"
        "    r.test(test_module='hangbench', hdl_toplevel='cnt', build_dir='build/b', log_file='build/b/sim.log', test_dir='.', "
        "timescale=('1ns','1ps'))\n")
    import os
    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    p = subprocess.run([sys.executable, str(ROOT / "flow" / "sim_watchdog.py"), "--limit", "12", "--heartbeat", "1", "--root",
                        str(tmp_path), "--", sys.executable, "-m", "pytest", "-q", "-s", "-p", "no:cacheprovider", "test_run_rtl.py"],
                       capture_output=True, text=True, timeout=120, cwd=tmp_path, env=env)
    assert p.returncode == 124, p.stdout[-800:]
    h = json.loads(p.stdout.split("FDA_HANG ", 1)[1].splitlines()[0])
    assert h["test"]["name"].endswith("test_hang") and h["sim_time_ns"] > 0 and h["sim_time_advancing"] is True
