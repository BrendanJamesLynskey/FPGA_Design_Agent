"""Stage 9 asks for hardware approval only when the bring-up artefacts exist and pass a dry check (05d, from luna
run 7: the pause came without hw_checks.py and the bringup tool then refused, routing the failure to stage 2)."""

import shutil
import uuid
from pathlib import Path

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("deepagents")

from agent.core.session import ROOT  # noqa: E402
from agent.graph import run as gr  # noqa: E402
from agent.graph.roles import RoleJail, role_session  # noqa: E402
from agent.graph.stages import MACHINE, classify, exit_check, route_failure  # noqa: E402
from agent.tests.test_episode import FakeRunner, T1  # noqa: E402
from flow import hw_dry_check  # noqa: E402

S9 = MACHINE[9]


def _copy_hw(design: Path) -> None:
    (design / "tests").mkdir(exist_ok=True)
    shutil.copy(T1 / "hw_checks.py", design / "hw_checks.py")
    shutil.copy(T1 / "tests" / "test_t1_hw.py", design / "tests" / "test_t1_dimmer_counter_hw.py")
    shutil.copy(T1 / "BRINGUP.md", design / "BRINGUP.md")
    shutil.copy(T1 / "probes.yaml", design / "probes.yaml")


def test_dry_check_lists_every_missing_artefact(tmp_path):
    r = hw_dry_check.check_design(tmp_path)
    text = "\n".join(r["problems"])
    assert not r["ok"] and "hw_checks.py does not exist" in text and "no tests/test_*_hw.py" in text
    assert "BRINGUP.md does not exist" in text and "probes.yaml does not exist" in text
    _copy_hw(tmp_path)
    assert hw_dry_check.check_design(tmp_path) == {"ok": True, "problems": []}


def test_dry_check_finds_malformed_files_without_running_them(tmp_path):
    _copy_hw(tmp_path)
    (tmp_path / "hw_checks.py").write_text("import os\nCAPTURES = []\n")
    (tmp_path / "tests" / "test_t1_dimmer_counter_hw.py").write_text("def test_x(board):\n    assert 1\n")
    (tmp_path / "BRINGUP.md").write_text("# Guide\n## Setup\n")
    text = "\n".join(hw_dry_check.check_design(tmp_path)["problems"])
    assert "CAPTURES is empty" in text and "no restore(sh)" in text and "no pytest.mark.hw" in text
    assert "BRINGUP.md has no section for: test, debug, if it fails" in text


def test_exit_check_and_routing_for_missing_artefacts():
    ev = {"gates_base": {"stages": {"bitstream": {"ran": True, "gates": {"bitstream_present": True}}}},
          "gates_ila": {"stages": {"bitstream": {"ran": True, "gates": {"bitstream_present": True, "debug_probes_present": True}}}},
          "bringup_ready": hw_dry_check.check_design(Path("/nonexistent-design"))}
    ok, fails = exit_check(S9, ev)
    assert not ok and any(f.startswith("bring-up artefacts: hw_checks.py does not exist") for f in fails)
    assert route_failure(S9, classify(S9, fails)) == 9                      # the stage's own writer, not stage 2
    refused = ["bring-up failed at 'hardware-bringup': the design has no hw_checks.py and tests/test_*_hw.py for bring-up"]
    assert route_failure(S9, classify(S9, refused)) == 9
    assert route_failure(S9, classify(S9, ["bring-up failed at 'uart_tests'"])) == 2     # a real hardware failure is unchanged


def test_approval_pause_waits_for_the_artefacts(tmp_path, monkeypatch):
    runs = ROOT / "runs" / f"_pytest_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(gr, "RUNS", runs)
    try:
        cfg = gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", review="off")
        rt = gr.new_runtime(cfg, lambda *a, **k: None, run_id="bu", runner=FakeRunner())
        (rt.design / "build.yaml").write_text((T1 / "build.yaml").read_text())
        state = {"run_id": "bu", "stage": 9, "visits": {}, "history": [], "evidence": {}}
        out = gr.node_gate(state)
        assert any("bring-up artefacts" in f for f in out["fails"])
        assert "hardware: awaiting approval before programming" not in out["fails"]
        _copy_hw(rt.design)
        out = gr.node_gate(state)
        assert out["fails"] == ["hardware: awaiting approval before programming"]
    finally:
        shutil.rmtree(runs, ignore_errors=True)


def test_bringup_files_belong_to_the_tests_role_not_the_rtl_writer(tmp_path):
    from agent.core.session import Session
    from agent.core.security import SecurityError
    s = Session(design=tmp_path)
    RoleJail(role_session(s, "tests").jail, "tests").resolve("hw_checks.py", write=True)
    with pytest.raises(SecurityError):
        RoleJail(role_session(s, "tests").jail, "tests").resolve("rtl/top.sv", write=True)
