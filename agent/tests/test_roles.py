"""Sub-agent input isolation (05b): the blind model sees only spec.yaml, the test writer never the RTL, the RTL
writer never the hidden spec."""

import pytest

from agent.core import Session, dispatch
from agent.graph.roles import role_inputs, role_session


@pytest.fixture
def s(tmp_path):
    d = tmp_path / "designs" / "x"
    (d / "rtl").mkdir(parents=True)
    (d / "tests").mkdir()
    (d / "spec.md").write_text("spec md")
    (d / "spec.yaml").write_text("name: x\n")
    (d / "model.py").write_text("# model\n")
    (d / "rtl" / "top.sv").write_text("module top; endmodule\n")
    (d / "tests" / "test_x_rtl.py").write_text("# test\n")
    (tmp_path / "hidden_full_spec.yaml").write_text("secret: 1\n")
    return Session(design=d, root=tmp_path, stage="rtl-design-creation")


def _read(s, role, path):
    return dispatch(role_session(s, role), "read_file", {"path": path})


def test_blind_model_sees_only_spec_yaml(s):
    assert set(role_inputs(s, "model")) == {"spec.yaml"}
    for p in ("rtl/top.sv", "tests/test_x_rtl.py", "spec.md", "../../hidden_full_spec.yaml"):
        assert _read(s, "model", p)["refused"], p
    assert not _read(s, "model", "spec.yaml")["refused"]
    w = dispatch(role_session(s, "model"), "write_file", {"path": "rtl/top.sv", "content": "x"})
    assert w["refused"] and w["rule"] == "role"


def test_test_writer_never_sees_rtl(s):
    assert set(role_inputs(s, "tests")) == {"spec.yaml", "model.py"}
    assert _read(s, "tests", "rtl/top.sv")["refused"]
    assert not _read(s, "tests", "model.py")["refused"]
    assert "rtl/" not in dispatch(role_session(s, "tests"), "list_files", {"path": "."})["output"]


def test_rtl_writer_never_sees_hidden_material(s):
    assert _read(s, "rtl", "../../hidden_full_spec.yaml")["refused"]
    assert not _read(s, "rtl", "rtl/top.sv")["refused"]
    w = dispatch(role_session(s, "rtl"), "write_file", {"path": "model.py", "content": "x"})
    assert w["refused"]
