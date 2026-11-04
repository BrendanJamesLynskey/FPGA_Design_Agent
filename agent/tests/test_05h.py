"""Brief 05h: `simulate` tells the bench where the gate reads results; the RTL role is not woken without a reason."""

from agent.core.runner import RunResult
from agent.core import dispatch
from agent.graph import run as gr
from agent.tests.test_05c2_fixes import rt  # noqa: F401  (the fixture)


def test_simulate_sets_the_results_dir_and_clears_the_old_one(session) -> None:
    seen = {}

    class Runner:
        def run(self, kind, argv, cwd, env=None, timeout=600):
            seen.update(env or {})
            return RunResult(0, "1 passed", "", 0.1)

    old = session.design / "build" / "verif" / "sim" / "seed9"
    old.mkdir(parents=True)
    (old / "results.xml").write_text("<testsuites/>")
    session.runner = Runner()
    assert dispatch(session, "simulate", {"sim": "icarus"})["ok"]
    assert seen["FDA_SIM_RESULTS_DIR"] == str((session.design / "build" / "verif" / "sim").relative_to(session.root))
    assert not old.exists()


def test_rtl_is_not_woken_without_a_reason(rt) -> None:  # noqa: F811
    d = rt.design
    (d / "model.py").write_text("class Model: pass\n")
    (d / "tests").mkdir(exist_ok=True)
    (d / "tests" / "test_x_rtl.py").write_text("# t\n")
    (d / "rtl").mkdir(exist_ok=True)
    (d / "rtl" / "top.sv").write_text("module top; endmodule\n")
    assert gr.stage2_plan(rt, {"owners": {}}) == {}
    assert "later stage failed" not in str(gr.stage2_plan(rt, {"owners": {}, "fails": ["x"]}))
