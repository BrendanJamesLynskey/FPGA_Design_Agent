"""Brief 07a2 fix 4: run 4 (c14_int8_dot_requant, 20261107-005621-8deb) stopped at stage 2: V3 cover_properties_pct was 0.0
because the tests role's entry built only the shell and rtl/*.sv, never verif/checkers/*.sv; each Icarus simulate took
~6 min and used up the stage's four visits; the agent suite waited on the shared heavy-slot lock."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from agent.graph import stages
from flow import cocotb_run
from flow.mutate import lock_path

FIX = Path(__file__).parent / "fixtures" / "run4_c14"


@pytest.fixture()
def run4(tmp_path: Path) -> Path:
    d = tmp_path / "designs" / "c14_int8_dot_requant"
    shutil.copytree(FIX, d)
    return d


def test_with_checkers_adds_the_bound_checker_of_run4_last(run4: Path) -> None:
    src = cocotb_run.SHELL_RTL + sorted((run4 / "rtl").glob("*.sv"))          # run 4's entry, as written
    out = cocotb_run.with_checkers(src, run4)
    assert [p.name for p in out[:len(src)]] == [p.name for p in src]
    assert out[-1].name == "c14_int8_dot_requant_checker.sv"                  # it holds the bind statement
    assert not any(p.suffix == ".svh" for p in out)


def test_with_checkers_does_not_list_a_checker_twice_and_puts_bind_files_last(run4: Path) -> None:
    chk = run4 / "verif" / "checkers"
    (chk / "a_bind.sv").write_text("bind c14_int8_dot_requant_top c14_int8_dot_requant_checker u2 (.*);\n")
    (chk / "z_other.sv").write_text("module z_other; endmodule\n")
    src = sorted((run4 / "rtl").glob("*.sv")) + [chk / "z_other.sv", chk / "a_bind.sv"]
    out = cocotb_run.with_checkers(src, run4)
    names = [p.name for p in out]
    assert len(names) == len(set(names))
    assert names.index("a_bind.sv") > names.index("z_other.sv")
    assert names[-2:] == ["a_bind.sv", "c14_int8_dot_requant_checker.sv"]
    assert all(names.index(n) < names.index("a_bind.sv") for n in ("z_other.sv", "c14_int8_dot_requant_top.sv"))


def test_with_checkers_without_a_checkers_directory_changes_nothing(tmp_path: Path) -> None:
    f = tmp_path / "x.sv"
    f.write_text("module x; endmodule\n")
    assert cocotb_run.with_checkers([f], tmp_path) == [f]


class _Spy:
    """Stands in for cocotb's runner: records the sources of build() and stops."""
    built: list[str] = []

    def build(self, sources, **kw):
        _Spy.built = list(sources)
        raise _Stop

    def test(self, **kw):                                                    # pragma: no cover
        raise AssertionError("the build should have stopped the run")


class _Stop(Exception):
    pass


def _build_sources(monkeypatch: pytest.MonkeyPatch, run4: Path, sim: str) -> list[str]:
    monkeypatch.setenv("SIM", sim)
    monkeypatch.setattr(cocotb_run, "get_runner", lambda name: _Spy())
    src = cocotb_run.SHELL_RTL + sorted((run4 / "rtl").glob("*.sv"))
    with pytest.raises(_Stop):
        cocotb_run.run("x", "c14_int8_dot_requant_top", src, "c14_bench", run4 / "tests", build_root=run4 / "b")
    return [Path(s).name for s in _Spy.built]


def test_the_verilator_build_gets_the_checkers_the_bench_did_not_list(monkeypatch, run4) -> None:
    names = _build_sources(monkeypatch, run4, "verilator")
    assert names[-1] == "c14_int8_dot_requant_checker.sv"


def test_the_icarus_build_does_not(monkeypatch, run4) -> None:
    assert "c14_int8_dot_requant_checker.sv" not in _build_sources(monkeypatch, run4, "icarus")


def _verilator_ok() -> bool:
    from agent.core.tools import _verilator_version
    v = _verilator_version()
    return bool(v and v >= (5, 36))


@pytest.mark.skipif(not _verilator_ok() or os.environ.get("FDA_RUN_VERILATOR_TESTS") != "1",
                    reason="a real Verilator coverage build of run 4's bench (minutes); set FDA_RUN_VERILATOR_TESTS=1")
def test_run4_bench_now_reaches_cover_properties_under_verilator(run4: Path, monkeypatch) -> None:
    pytest.importorskip("cocotb_coverage")
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[2]
    from agent.core import runner as rn
    env = {**os.environ, **rn.scrubbed_env(), "SIM": "verilator", "FDA_COVERAGE": "1", "FDA_SIM_RESULTS_DIR": str(run4 / "res")}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-k", "seed_1",
                        str(run4 / "tests" / "test_c14_int8_dot_requant_rtl.py")], cwd=root, env=env,
                       capture_output=True, text=True, timeout=1500)
    assert r.returncode == 0, r.stdout[-3000:]
    dat = next((run4.parents[1] / "build").rglob("coverage.dat"), None) or next(root.glob("build/sim/**/coverage.dat"))
    assert "C_led_rise" in dat.read_text(errors="replace")


def test_stage_2_has_more_visits_than_the_others_and_nothing_else_changed() -> None:
    lim = dict(stages.RUN_LIMITS)
    assert stages.visit_limit(2, lim) == 6
    assert all(stages.visit_limit(n, lim) == 4 for n in (0, 1, 3, 4, 5, 6, 7, 8, 9))
    assert stages.visit_limit(2, {**lim, "visits_per_stage": 2}) == 2          # an explicit lower cap still wins


def test_the_work_node_stops_stage_2_only_after_six_visits() -> None:
    import inspect

    from agent.graph import run
    src = inspect.getsource(run.node_work)
    assert "visit_limit(n, rt.cfg.run_limits)" in src and 'run_limits["visits_per_stage"]' not in src


def test_the_suite_never_uses_the_shared_heavy_lock() -> None:
    p = lock_path()
    assert p is not None and "_handoff" not in str(p) and p.parent.is_dir()
    assert not p.exists()
