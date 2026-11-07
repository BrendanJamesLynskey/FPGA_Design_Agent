"""Brief 07a2 fix 5, group E: the agent's iteration simulations, the gate and the mutation run use Verilator when the
design builds in it, with Icarus as the final cross-check; the mutation sample and the simulate timeout scale with the
measured baseline (batch 1, c15: 2.4 to 12.7 minutes per Icarus run, a 1800 s timeout, 1.5 h of mutation)."""

from __future__ import annotations

import json
from pathlib import Path

from agent.core import dispatch
from agent.core import tools as tl
from agent.core.runner import RunResult
from agent.graph import run as gr
from agent.tests.conftest import FakeRunner
from flow import mutate as M

VBUILD_ERROR = "%Error: file.sv:3:1: syntax error\n%Error: Exiting due to 1 error(s)\n"


class SimRunner(FakeRunner):
    """simulate results by SIM value; records the SIM and the timeout of each run."""

    def __init__(self, by_sim: dict[str, RunResult]):
        super().__init__()
        self.by_sim, self.sims, self.timeouts = by_sim, [], []

    def run(self, kind, argv, cwd, env=None, timeout=600):
        if kind != "simulate":
            return super().run(kind, argv, cwd, env, timeout)
        self.sims.append((env or {}).get("SIM"))
        self.timeouts.append(timeout)
        return self.by_sim[(env or {})["SIM"]]


def _both(monkeypatch):
    monkeypatch.setattr(tl, "available_sims", lambda: ("icarus", "verilator"))


def test_simulate_auto_runs_verilator_when_it_is_available(session, monkeypatch) -> None:
    _both(monkeypatch)
    session.runner = SimRunner({"verilator": RunResult(0, "1 passed", "", 4.0), "icarus": RunResult(0, "1 passed", "", 40.0)})
    r = dispatch(session, "simulate", {})
    assert r["ok"] and r["sim"] == "verilator" and session.runner.sims == ["verilator"]


def test_simulate_auto_falls_back_to_icarus_only_when_verilator_cannot_build(session, monkeypatch) -> None:
    _both(monkeypatch)
    session.runner = SimRunner({"verilator": RunResult(1, VBUILD_ERROR, "", 2.0), "icarus": RunResult(0, "1 passed", "", 40.0)})
    r = dispatch(session, "simulate", {"sim": "auto"})
    assert r["ok"] and r["sim"] == "icarus" and r["fell_back_from"] == "verilator" and "did not build in Verilator" in r["output"]
    # a failing TEST on Verilator is a real failure: no fallback
    fail = "___ test_x ___\nE   AssertionError: 3 != 4\n=== 1 failed ===\n"
    session.runner = SimRunner({"verilator": RunResult(1, fail, "", 9.0), "icarus": RunResult(0, "ok", "", 40.0)})
    r = dispatch(session, "simulate", {})
    assert not r["ok"] and r["sim"] == "verilator" and session.runner.sims == ["verilator"] and "fell_back_from" not in r


def test_simulate_timeout_scales_with_the_measured_baseline(session, monkeypatch) -> None:
    _both(monkeypatch)
    assert tl.sim_timeout(session.design, "icarus") == 1800                            # nothing measured yet
    session.runner = SimRunner({"icarus": RunResult(0, "ok", "", 600.0), "verilator": RunResult(0, "ok", "", 20.0)})
    dispatch(session, "simulate", {"sim": "icarus"})
    assert json.loads((session.design / "build/verif/sim_baseline.json").read_text()) == {"icarus": 600.0}
    assert tl.sim_timeout(session.design, "icarus") == 2520                            # 4 x 600 + 120
    dispatch(session, "simulate", {"sim": "verilator"})
    assert tl.sim_timeout(session.design, "verilator") == 600                          # a fast bench: the floor, not 1800
    tl.record_sim_baseline(session.design, "icarus", 5000)
    assert tl.sim_timeout(session.design, "icarus") == 7200                            # and a ceiling


def test_gate_runs_icarus_as_the_final_cross_check_and_needs_both(session, monkeypatch) -> None:
    _both(monkeypatch)
    session.runner = SimRunner({"verilator": RunResult(0, "ok", "", 4.0), "icarus": RunResult(0, "ok", "", 40.0)})
    g = gr.simulate_gate(session)
    assert g["ok"] and g["sim"] == "verilator+icarus" and session.runner.sims == ["verilator", "icarus"]
    session.runner = SimRunner({"verilator": RunResult(0, "ok", "", 4.0),
                                "icarus": RunResult(1, "___ test_y ___\nE   AssertionError: icarus only\n", "", 40.0)})
    g = gr.simulate_gate(session)
    assert not g["ok"] and g["sim"] == "icarus (cross-check)" and "icarus only" in g["text"]
    session.runner = SimRunner({"verilator": RunResult(1, "___ test_y ___\nE   AssertionError: real\n", "", 4.0),
                                "icarus": RunResult(0, "ok", "", 40.0)})
    g = gr.simulate_gate(session)
    assert not g["ok"] and session.runner.sims == ["verilator"]                         # no Icarus run on a failing iteration


def test_mutation_sample_is_capped_by_the_baseline_time() -> None:
    assert M.plan_caps(30, 20, 39, None)[0] == 20                                       # a Verilator bench: the whole sample
    n, wall = M.plan_caps(312, 20, 39, None)                                            # c15 on Icarus (12 min = 760 s: the floor)
    assert n == 10 and wall <= 3744
    assert M.plan_caps(760, 20, 39, None)[0] == M.MIN_EVALUATED                         # never under the V3 floor
    assert M.plan_caps(150, 20, 39, None)[0] == 20 and M.plan_caps(200, 20, 39, None)[0] == 16   # floor(3600/200) - 2
    # the old rule would have given 20 mutants at 760 s each: 5 h capped to 2 h
    assert M.MUTATION_BUDGET_S == 3600


def test_mutation_uses_verilator_and_falls_back_on_a_baseline_that_does_not_build(tmp_path, monkeypatch) -> None:
    calls: list[str] = []

    def fake_bench(design, env, timeout, runner=None, sim="icarus"):
        calls.append(sim)
        return ("fail", 3.0) if sim == "verilator" and env.get("FDA_MUTANT_DIR", "").endswith("rtl") else ("pass", 3.0)

    monkeypatch.setattr(M, "run_bench", fake_bench)
    monkeypatch.setattr(M, "choose_sim", lambda requested, runner=None: "verilator" if requested == "auto" else requested)
    d = tmp_path / "designs" / "x"
    (d / "rtl").mkdir(parents=True)
    (d / "tests").mkdir()
    (d / "rtl" / "a.sv").write_text("module a(input logic i, output logic o);\n assign o = i & 1'b1;\nendmodule\n")
    (d / "tests" / "test_x_rtl.py").write_text("")
    (d / "build.yaml").write_text("top: a\n")
    monkeypatch.setattr(M, "ROOT", tmp_path)

    class A:
        sim, seed, max_mutants, wall_s, mutant_timeout_s, lock_wait_s, sandbox, json = "auto", 1, 3, None, 0, 0, "host", None
    out = d / "build" / "verif" / "mutation.json"
    M._generic_locked(d, A(), d / "rtl", out, 0.0, None)
    res = json.loads(out.read_text())
    assert calls[:2] == ["verilator", "icarus"] and res["sim"] == "icarus" and "used icarus instead" in res["sim_note"]
