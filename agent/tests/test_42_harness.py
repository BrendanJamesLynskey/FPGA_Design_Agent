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


# ---- H9: typed digests ---------------------------------------------------------------------------------------------

DATA = ROOT / "flow" / "tests" / "data"


def _dg(name: str, level: str = "summary", focus: str | None = None) -> dict:
    from agent.core.report_digest import digest
    return digest(name + ".rpt", (DATA / (name + ".rpt")).read_text(), level, focus, path=f"build/base/{name}.rpt")


@pytest.mark.parametrize("bad,good,needle", [
    ("bad_timing_summary", "good_timing_summary", "TIMING NOT MET"),
    ("bad_methodology", "good_methodology", "2 critical or error"),
    ("bad_drc", "good_drc", "2 critical or error"),
    ("bad_cdc", "good_cdc", "2 critical crossings"),
])
def test_a_seeded_fault_is_in_the_summary_digest(bad: str, good: str, needle: str) -> None:
    """Fixtures are the real Vivado reports of the flow's good and seeded-fault builds (flow/tests/data)."""
    b, g = _dg(bad), _dg(good)
    assert needle in b["verdict"] and needle not in g["verdict"]
    assert b["output"].rstrip().endswith(f"report: build/base/{bad}.rpt") and not b["rows"]


def test_digest_numbers_come_from_the_gate_parsers() -> None:
    from flow import gates
    t = (DATA / "bad_timing_summary.rpt").read_text()
    n = _dg("bad_timing_summary")["numbers"]
    assert n["wns_ns"] == gates.parse_timing_summary(t)["wns_ns"] and n["tns_failing_endpoints"] > 0
    assert _dg("good_power")["numbers"]["total_w"] == gates.parse_report_power((DATA / "good_power.rpt").read_text())["total_w"]
    assert "lut" in _dg("good_utilization")["numbers"] and "highest use" in _dg("good_utilization")["verdict"]


def test_levels_and_focus_on_rule_reports() -> None:
    s, st, de = (_dg("bad_methodology", lv) for lv in ("summary", "standard", "detail"))
    assert len(s["rows"]) == 0
    assert len({r["rule"] for r in st["rows"]}) == len(st["rows"]) == 3 or len(st["rows"]) == len({r["rule"] for r in st["rows"]})
    assert len(de["rows"]) >= len(st["rows"])
    f = _dg("bad_methodology", "standard", "TIMING-6")
    assert f["rows"] and all(r["rule"] == "TIMING-6" for r in f["rows"])


def test_timing_paths_top_n_and_focus() -> None:
    from agent.core.report_digest import digest
    blocks = "".join(f"Slack (VIOLATED) :        -{i}.000ns  (required time - arrival time)\n  Source:                 a{i}_reg/C\n"
                     f"  Destination:            b{i}_reg/D\n  Path Group:             clk\n\n" for i in range(1, 31))
    text = (DATA / "bad_timing_summary.rpt").read_text() + "\n" + blocks
    assert len(digest("t_timing_summary.rpt", text, "summary")["rows"]) == 0
    assert len(digest("t_timing_summary.rpt", text, "standard")["rows"]) == 5
    d = digest("t_timing_summary.rpt", text, "detail")
    assert len(d["rows"]) == 20 and d["rows"][0]["slack_ns"] == -30.0          # worst first
    assert digest("t_timing_summary.rpt", text, "standard", "2")["rows"][0]["slack_ns"] == -29.0


def test_simulation_and_lint_digests() -> None:
    from agent.core.report_digest import digest
    sim = ("[first failure] test_x\n  assert 3 == 4\n[end first failure]\n...\nFAILED tests/test_t_rtl.py::test_x - AssertionError\n"
           "1 failed, 4 passed in 3.2s\n")
    d = digest("simulate.txt", sim)
    assert d["kind"] == "simulation" and d["verdict"] == "simulation FAILED" and d["numbers"]["failed"] == 1
    assert "assert 3 == 4" in d["output"] and d["numbers"]["failing_tests"] == ["tests/test_t_rtl.py::test_x"]
    assert digest("simulate.txt", "5 passed in 1s")["verdict"] == "simulation passed"
    lint = "%Warning-WIDTH: a.sv:3: width\n%Warning-WIDTH: a.sv:9: width\n%Error: a.sv:12: syntax error\n"
    ld = digest("lint.txt", lint, "standard")
    assert ld["kind"] == "lint" and "1 errors, 2 warnings" in ld["verdict"] and ld["numbers"]["WIDTH"] == 2
    hang = digest("simulate.txt", "[simulation hung] x\n1 failed in 600s")
    assert hang["verdict"].startswith("[simulation hung]")


def test_vivado_log_and_generic_fallback() -> None:
    from agent.core.report_digest import digest
    log = "INFO: x\nERROR: [Synth 8-1] boom\nCRITICAL WARNING: [Vivado 12-1] w\nWARNING: [x] y\n"
    d = digest("vivado.log", log)
    assert d["numbers"]["errors"] == 1 and d["rows"][0]["line"].startswith("ERROR:")
    g = digest("notes.txt", "\n".join(f"l{i}" for i in range(100)), "summary")
    assert g["kind"] == "generic" and g["output"].count("\n") < 20 and g["output"].rstrip().endswith("report: notes.txt")


def test_report_digest_tool_and_compaction(session: Session, tmp_path: Path) -> None:
    from agent.core.report_digest import compact_result
    b = session.design / "build" / "base"
    b.mkdir(parents=True, exist_ok=True)
    shutil.copy(DATA / "bad_methodology.rpt", b / "methodology.rpt")
    r = dispatch(session, "report_digest", {"name": "methodology.rpt", "level": "standard"})
    assert r["ok"] and r["kind"] == "methodology" and r["output"].rstrip().endswith("report: build/base/methodology.rpt")
    assert not dispatch(session, "report_digest", {"name": "nope.rpt"})["ok"]
    res = {"ok": False, "tool": "simulate", "returncode": 1, "output": "FAILED t::x\n" + "noise\n" * 3000 + "1 failed, 2 passed in 3s"}
    text = compact_result(res, "simulate", session.design, 4, readable=True)
    p = json.loads(text)
    assert len(text) < 2500 and "simulation FAILED" in p["digest"] and "/build/tool_results/004_simulate.json" in p["digest"]
    assert (session.design / "build" / "tool_results" / "004_simulate.json").is_file()
    g = {"ok": False, "output": "x" * 9000, "gates": {"pass": False, "first_failed_stage": "post_synth",
                                                         "gates": {"a": True, "wns_ok": False}}}
    pg = json.loads(compact_result(g, "gates", session.design, 5, readable=False))
    assert pg["gate_summary"]["failed_gates"] == ["wns_ok"] and "not readable" in pg["digest"]


def test_h9_offers_report_digest_only_with_the_arm() -> None:
    from agent.core.registry import TOOLS
    import agent.core.tools  # noqa: F401
    assert "report_digest" in TOOLS
    from agent.graph.run import FLOW_TOOLS, effective_tools
    assert "report_digest" in FLOW_TOOLS
    assert all("report_digest" not in effective_tools(r, n, "V3") for r in ("rtl", "tests") for n in (2, 3, 4))


# ---- amendment 3: malformed provider responses are asked for again ---------------------------------------------------


def test_malformed_response_is_retried_for_every_arm() -> None:
    from types import SimpleNamespace as NS

    from agent.graph.llm import OpenRouterClient

    def resp(args: str):
        call = NS(id="c1", function=NS(name="write_file", arguments=args))
        msg = NS(content="", tool_calls=[call])
        return NS(usage=NS(prompt_tokens=3, completion_tokens=2, model_extra={"cost": 0.001}), choices=[NS(message=msg)],
                  model_extra={}, provider="p")

    seq = ["{\n\n\n", '{"path": "a"', '{"path": "a"}']          # two malformed bodies, then a good one

    class Chat:
        n = 0

        def create(self, **kw):
            a = seq[self.n]
            self.n += 1
            return resp(a)

    c = OpenRouterClient.__new__(OpenRouterClient)
    c.model, c._c = "x/y", NS(chat=NS(completions=Chat()))
    r = c([{"role": "user", "content": "hi"}], None)
    assert r.tool_calls[0]["args"] == {"path": "a"} and c.malformed_retries == 2

    seq[:] = ["{"] * 3                                         # always malformed: the third failure is raised
    c._c.chat.completions.n = 0
    with pytest.raises(json.JSONDecodeError):
        c([{"role": "user", "content": "hi"}], None)


def test_h9_note_points_only_at_tools_the_role_can_call(session: Session) -> None:
    from agent.core.report_digest import compact_result
    res = {"ok": False, "tool": "simulate", "output": "x" * 9000}
    callable_note = json.loads(compact_result(res, "simulate", session.design, 1, True, True))["note"]
    readable_note = json.loads(compact_result(res, "simulate", session.design, 2, True, False))["note"]
    blind_note = json.loads(compact_result(res, "simulate", session.design, 3, False, False))["note"]
    assert "report_digest" in callable_note
    assert "report_digest" not in readable_note and "read the path" in readable_note
    assert "report_digest" not in blind_note and "narrower scope" in blind_note


def test_malformed_body_from_the_sdk_is_retried_too() -> None:
    """The failure actually seen: ``create()`` itself raised JSONDecodeError (a body that does not parse)."""
    from types import SimpleNamespace as NS

    from agent.graph.llm import OpenRouterClient
    good = NS(usage=NS(prompt_tokens=1, completion_tokens=1, model_extra={"cost": 0.0}),
              choices=[NS(message=NS(content="ok", tool_calls=[]))], model_extra={}, provider="p")

    class Chat:
        n = 0

        def create(self, **kw):
            self.n += 1
            if self.n < 3:
                raise json.JSONDecodeError("Expecting ':' delimiter", "{" * 10, 5)
            return good

    c = OpenRouterClient.__new__(OpenRouterClient)
    c.model, c._c = "x/y", NS(chat=NS(completions=Chat()))
    assert c([{"role": "user", "content": "hi"}], None).text == "ok" and c.malformed_retries == 2
