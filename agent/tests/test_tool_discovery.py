"""The core finds its tools from the local tools file, and a missing tool gives a clear error (05b fix 1);
bring-up results go under the design's build directory (05b fix 2)."""

from pathlib import Path

import pytest

from agent.core import runner as rn


def test_tools_file_puts_dirs_on_path_and_sets_env(tmp_path, monkeypatch):
    bindir = tmp_path / "vroot" / "bin"
    bindir.mkdir(parents=True)
    exe = bindir / "verilator"
    exe.write_text("#!/bin/sh\necho fake-verilator \"$VERILATOR_ROOT\"\n")
    exe.chmod(0o755)
    f = tmp_path / "tools.yaml"
    f.write_text(f"path: [{bindir}]\nenv: {{VERILATOR_ROOT: {tmp_path / 'vroot'}}}\n")
    monkeypatch.setattr(rn, "TOOLS_FILE", f)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    r = rn.LocalRunner().run("lint", ["verilator", "--version"], tmp_path)
    assert r.returncode == 0 and f"fake-verilator {tmp_path / 'vroot'}" in r.stdout


def test_missing_tool_names_tool_and_install(tmp_path, monkeypatch):
    monkeypatch.setattr(rn, "TOOLS_FILE", tmp_path / "none.yaml")
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(rn.ToolMissing) as e:
        rn.LocalRunner().run("lint", ["verilator", "--version"], tmp_path)
    assert "'verilator' not found" in str(e.value) and "tools.yaml" in str(e.value)


def test_bringup_writes_under_design_build(tmp_path):
    src = (Path(__file__).resolve().parents[1] / "core" / "tools.py").read_text()
    body = src.split('def bringup(', 1)[1].split("\n@tool", 1)[0]
    assert '"--results-dir"' in body and 'results" / "f0b' not in body


def test_shell_view_is_read_only(tmp_path):
    from agent.core import Session, dispatch
    from agent.core.session import ROOT
    s = Session(design=ROOT / "designs" / "t1_dimmer_counter", stage="rtl-design")
    r = dispatch(s, "read_file", {"path": "@shell/rtl/uart_tx.sv"})
    assert r["ok"] is not False and "module" in r["output"]
    assert "@shell/host/protocol.py" in dispatch(s, "list_files", {"path": "@shell/"})["output"]
    assert "@shell/host/fpga_shell.py" not in dispatch(s, "list_files", {"path": "@shell/"})["output"]
    for bad in ("@shell/host/fpga_shell.py", "@shell/../flow/build.tcl", "@shell/rtl/../../agent/core/tools.py"):
        assert dispatch(s, "read_file", {"path": bad})["refused"], bad
    w = dispatch(s, "write_file", {"path": "@shell/rtl/uart_tx.sv", "content": "x"})
    assert w["refused"] and w["rule"] == "path-jail"
