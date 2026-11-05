"""Brief 05m: Verilator in the sandbox image (fda-sim:2) and mutation runs through the sandbox runner. Fast: fake
runners and a fake docker; no container is started."""

import sys
from pathlib import Path

import pytest

from agent.core import runner as rn
from agent.core import tools as T
from agent.core.runner import ContainerRunner, RunResult
from agent.core.session import ROOT
from flow import mutate as M


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    rn._IMAGE_VERILATOR.clear()
    T.available_sims.cache_clear()
    yield
    rn._IMAGE_VERILATOR.clear()
    T.available_sims.cache_clear()


class _Spy:
    def __init__(self, rc=0):
        self.calls, self.rc = [], rc

    def run(self, kind, argv, cwd, env=None, timeout=600):
        self.calls.append((kind, argv, env, timeout))
        return RunResult(self.rc, "", "", 0.0)


def test_image_is_fda_sim_2_with_pinned_verilator():
    df = (ROOT / "agent" / "container" / "Dockerfile").read_text()
    assert rn.SIM_IMAGE == "fda-sim:2"
    assert "VERILATOR_TAG=v5.048" in df and "COPY --from=verilator-build /opt/verilator" in df
    assert "iverilog" in df and "cocotb==2.0.1" in df           # Icarus and cocotb unchanged


def test_image_probe_parses_version_and_is_cached(monkeypatch):
    calls = []

    def fake(argv, **kw):
        calls.append(argv)
        return type("P", (), {"returncode": 0, "stdout": "Verilator 5.048 2026-01-01 rev v5.048\n"})()
    monkeypatch.setattr(rn.subprocess, "run", fake)
    assert rn.image_verilator_version() == (5, 48) and rn.image_verilator_version() == (5, 48)
    assert len(calls) == 1 and calls[0][:2] == ["docker", "run"] and "--network" in calls[0] and rn.SIM_IMAGE in calls[0]


def test_image_probe_none_without_verilator_or_engine(monkeypatch):
    monkeypatch.setattr(rn.subprocess, "run", lambda argv, **kw: type("P", (), {"returncode": 125, "stdout": ""})())
    assert rn.image_verilator_version() is None
    rn._IMAGE_VERILATOR.clear()

    def boom(*a, **k):
        raise OSError("no docker")
    monkeypatch.setattr(rn.subprocess, "run", boom)
    assert rn.image_verilator_version() is None


@pytest.mark.parametrize("image,imgv,hostv,expect", [
    (True, (5, 48), None, ("icarus", "verilator")),        # image has it: offered, host irrelevant
    (True, None, (5, 48), ("icarus",)),                    # old image, host has it: never the host while an image exists
    (True, (5, 20), None, ("icarus",)),                    # too old for cocotb 2
    (False, None, (5, 48), ("icarus", "verilator")),       # no image: the host's Verilator
    (False, None, (5, 20), ("icarus",)),
    (False, None, None, ("icarus",)),
])
def test_available_sims(monkeypatch, image, imgv, hostv, expect):
    monkeypatch.setattr(rn, "container_available", lambda *a, **k: image)
    monkeypatch.setattr(rn, "image_verilator_version", lambda *a, **k: imgv)
    monkeypatch.setattr(T, "_verilator_version", lambda *a, **k: hostv)
    assert T.available_sims() == expect


def test_container_has_name_memory_and_build_tmpfs():
    spy = _Spy()
    cr = ContainerRunner(ROOT / "designs" / "t1_dimmer_counter", ROOT, inner=spy)
    cr.run("simulate", [sys.executable, "-m", "pytest"], ROOT, {"SIM": "verilator"})
    argv = spy.calls[0][1]
    assert argv[argv.index("--memory") + 1] == rn.DEFAULT_MEMORY and "--name" in argv
    assert f"{ROOT}/build:rw,exec,size={rn.DEFAULT_BUILD_TMPFS}" in argv and argv[-3] == "python3"


def test_timed_out_container_is_removed_by_name(monkeypatch):
    spy = _Spy(rc=124)
    removed = []
    monkeypatch.setattr(rn.subprocess, "run", lambda argv, **kw: removed.append(argv))
    ContainerRunner(ROOT / "designs" / "t1_dimmer_counter", ROOT, inner=spy).run("simulate", ["x"], ROOT)
    name = spy.calls[0][1][spy.calls[0][1].index("--name") + 1]
    assert removed == [["docker", "rm", "-f", name]]


def test_mutate_bench_and_compile_go_through_the_runner():
    spy, d = _Spy(), ROOT / "designs" / "t1_dimmer_counter"
    st, _ = M.run_bench(d, {"FDA_MUTANT_DIR": "/x"}, 30, spy)
    assert st == "pass" and spy.calls[0][0] == "simulate"
    assert spy.calls[0][1][1:3] == ["-m", "pytest"] and spy.calls[0][2]["SIM"] == "icarus" and spy.calls[0][3] == 30
    assert M.compile_ok([Path("/a/b.sv")], spy) is True and spy.calls[1][1][0] == "iverilog"
    assert M.run_bench(d, {}, 5, _Spy(rc=1))[0] == "fail" and M.run_bench(d, {}, 5, _Spy(rc=124))[0] == "timeout"
    assert M.compile_ok([Path("/a/b.sv")], _Spy(rc=1)) is False


def test_mutate_never_uses_host_subprocess_when_a_runner_is_given(monkeypatch):
    monkeypatch.setattr(M.subprocess, "Popen", lambda *a, **k: pytest.fail("host Popen"))
    monkeypatch.setattr(M.subprocess, "run", lambda *a, **k: pytest.fail("host run"))
    M.run_bench(ROOT / "designs" / "t1_dimmer_counter", {}, 5, _Spy())
    M.compile_ok([Path("/a/b.sv")], _Spy())


def test_make_runner_modes(monkeypatch, tmp_path):
    monkeypatch.delenv("FDA_MUTATE_SANDBOX", raising=False)
    monkeypatch.setattr(rn, "container_available", lambda *a, **k: True)
    assert isinstance(M.make_runner(tmp_path, "auto"), ContainerRunner) and M.make_runner(tmp_path, "host") is None
    monkeypatch.setenv("FDA_MUTATE_SANDBOX", "host")
    assert M.make_runner(tmp_path, "auto") is None
    assert isinstance(M.make_runner(tmp_path, "container"), ContainerRunner)
    monkeypatch.setattr(rn, "container_available", lambda *a, **k: False)
    assert M.make_runner(tmp_path, "auto") is None
    with pytest.raises(RuntimeError):
        M.make_runner(tmp_path, "container")


def test_mutate_tool_asks_for_the_sandbox_the_session_runs_in(session):
    from agent.core import dispatch

    class Host(_Spy):
        pass

    class Box(ContainerRunner):
        def __init__(self, spy):
            self.spy = spy

        def run(self, kind, argv, cwd, env=None, timeout=600):
            return self.spy.run(kind, argv, cwd, env, timeout)
    for make, want in ((lambda spy: spy, "host"), (Box, "container")):
        spy = _Spy(rc=75)
        session.runner = make(spy)
        dispatch(session, "mutate", {"lock_wait_s": 0})
        argv = next(c[1] for c in spy.calls if c[0] == "mutate")
        assert argv[argv.index("--sandbox") + 1] == want
