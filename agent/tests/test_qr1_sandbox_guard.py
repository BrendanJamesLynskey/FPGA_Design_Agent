"""QR1: a run with a hidden spec is refused when the sandbox image is missing (agent-written tests would run on the host,
next to benchmark/tasks/*/hidden); a run without one, or with the explicit opt-out, falls back to the host."""
import pytest

from agent.core.runner import LocalRunner
from agent.graph import run as gr
from agent.graph.run import ArmBlocked
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
T1 = ROOT / "designs" / "t1_dimmer_counter"


def _cfg(tmp_path, hidden):
    h = tmp_path / "full.yaml"
    h.write_text((T1 / "spec.yaml").read_text())
    return gr.Config(spec_md=T1 / "spec.md", name="t1_dimmer_counter", interview="off", hidden_spec=h if hidden else None)


@pytest.fixture
def no_image(monkeypatch, tmp_path):
    monkeypatch.setattr(gr, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(gr, "container_available", lambda *a, **k: False)
    monkeypatch.delenv("FDA_ALLOW_HOST_SANDBOX", raising=False)


def test_hidden_spec_run_is_refused_without_the_image(no_image, tmp_path):
    with pytest.raises(ArmBlocked, match="fda-sim:2"):
        gr.new_runtime(_cfg(tmp_path, True), lambda *a, **k: None, run_id="g1")


def test_opt_out_and_no_hidden_spec_use_the_host(no_image, tmp_path, monkeypatch):
    rt = gr.new_runtime(_cfg(tmp_path, False), lambda *a, **k: None, run_id="g2")
    assert isinstance(rt.session.runner, LocalRunner)
    monkeypatch.setenv("FDA_ALLOW_HOST_SANDBOX", "1")
    rt = gr.new_runtime(_cfg(tmp_path, True), lambda *a, **k: None, run_id="g3")
    assert isinstance(rt.session.runner, LocalRunner)
