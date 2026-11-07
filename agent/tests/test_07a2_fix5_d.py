"""Brief 07a2 fix 5, group D: `lint` also runs an Icarus elaboration (batch 1, c15: ROM tables built by a constant
function returning an unpacked array; Verilator accepts it, Icarus 12 does not, and the agent found out only in simulate)."""

from __future__ import annotations

import shutil

import pytest

from agent.core import dispatch
from agent.core.runner import LocalRunner, RunResult
from agent.tests.conftest import FakeRunner

C15_ICARUS_ERROR = "rtl/softmax.sv:7: error: Unable to evaluate parameter T1_ROM value: softmax.gen_t1()"


def test_lint_reports_an_icarus_elaboration_error(session) -> None:
    session.runner = FakeRunner({"lint-icarus": RunResult(2, "", C15_ICARUS_ERROR, 0.1)})
    r = dispatch(session, "lint", {})
    assert r["ok"] is False and "[icarus elaboration" in r["output"] and "T1_ROM" in r["output"]
    argv = dict(session.runner.calls)["lint-icarus"]
    assert argv[:3] == ["iverilog", "-g2012", "-s"] and "-o" in argv and "/dev/null" in argv


def test_lint_is_unchanged_when_icarus_accepts_and_skips_when_it_is_missing(session) -> None:
    session.runner = FakeRunner()
    assert dispatch(session, "lint", {})["ok"] is True

    class NoIverilog(FakeRunner):
        def run(self, kind, argv, cwd, env=None, timeout=600):
            if kind == "lint-icarus":
                raise FileNotFoundError("iverilog")
            return super().run(kind, argv, cwd, env, timeout)
    session.runner = NoIverilog()
    r = dispatch(session, "lint", {})
    assert r["ok"] is True and "icarus" not in r["output"]


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog not installed")
def test_real_icarus_rejects_the_constant_function_returning_an_array(session) -> None:
    (session.design / "rtl" / "t.sv").write_text(
        "module t;\n  typedef int tab_t [0:3];\n  function automatic tab_t gen();\n    tab_t r;\n"
        "    for (int i = 0; i < 4; i++) r[i] = i * 3;\n    return r;\n  endfunction\n"
        "  localparam tab_t T = gen();\n  initial $display(\"%0d\", T[2]);\nendmodule\n")
    for f in (session.design / "rtl").glob("*.sv"):
        if f.name != "t.sv":
            f.unlink()
    (session.design / "build.yaml").write_text("top: t\npart: xc7a100tcsg324-1\nsources: [designs/t1_dimmer_counter/rtl/*.sv]\n"
                                               "constraints: [designs/t1_dimmer_counter/design.xdc]\ngenerics: {}\n")

    class Hybrid(FakeRunner):
        def run(self, kind, argv, cwd, env=None, timeout=600):
            return LocalRunner().run(kind, argv, cwd, env, timeout) if kind == "lint-icarus" else super().run(kind, argv, cwd, env, timeout)
    session.runner = Hybrid()
    r = dispatch(session, "lint", {})
    assert r["ok"] is False and "Unable to evaluate parameter T" in r["output"]
