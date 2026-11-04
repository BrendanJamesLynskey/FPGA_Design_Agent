"""Brief 05j: `simulate(coverage=True)` reaches the bench, and the tests-role checklist names the V3 evidence."""


def test_simulate_tool_passes_coverage_to_the_bench(session, monkeypatch):
    from agent.core import dispatch, tools
    from agent.core.runner import RunResult
    seen = {}

    class Runner:
        def run(self, kind, argv, cwd, env=None, timeout=600):
            seen.update(env or {})
            return RunResult(0, "1 passed", "", 0.1)

    session.runner = Runner()
    monkeypatch.setattr(tools, "available_sims", lambda: ("icarus", "verilator"))
    assert not dispatch(session, "simulate", {"sim": "icarus", "coverage": True})["ok"]      # Icarus records none
    assert dispatch(session, "simulate", {"sim": "verilator", "coverage": True})["ok"]
    assert seen["FDA_COVERAGE"] == "1"
    seen.clear()
    assert dispatch(session, "simulate", {"sim": "verilator"})["ok"] and "FDA_COVERAGE" not in seen
