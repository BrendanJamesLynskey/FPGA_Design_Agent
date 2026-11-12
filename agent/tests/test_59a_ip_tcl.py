"""build.yaml `ip_tcl:` cannot run agent-written Tcl in Vivado (brief 59A review, blocker B1).

flow/build.tcl sources every ip_tcl file inside Vivado, so only Tcl listed with its SHA-256 in the maintainer-owned
flow/ip_tcl_allow.yaml may run. The agent core refuses unknown build.yaml keys and unlisted ip_tcl entries; flow/prepare.py
refuses them for every build, whoever starts it."""
from __future__ import annotations

import shutil
import subprocess
import sys

import pytest
import yaml

from agent.core.artefacts import check_artefact
from agent.core.security import SecurityError
from agent.core.session import ROOT
from agent.core.tools import load_build_cfg
from flow import ip_tcl_allow

ALLOWED = "designs/b59a_axi_tx/ip/amd_ip.tcl"


def _with(session, **extra) -> None:
    f = session.design / "build.yaml"
    cfg = yaml.safe_load(f.read_text())
    cfg.update(extra)
    f.write_text(yaml.safe_dump(cfg))


def test_agent_written_ip_tcl_is_refused(session) -> None:
    (session.design / "ip.tcl").write_text("exec sh -c true\n")
    rel = str((session.design / "ip.tcl").relative_to(session.root))
    _with(session, ip_tcl=[rel])
    with pytest.raises(SecurityError) as e:
        load_build_cfg(session)
    assert e.value.rule == "build-yaml-ip-tcl" and "not in flow/ip_tcl_allow.yaml" in str(e.value)
    assert "ip_tcl entry" in check_artefact("build.yaml", (session.design / "build.yaml").read_text())


def test_a_tampered_allowed_file_is_refused(session) -> None:
    dst = session.root / ALLOWED
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text((ROOT / ALLOWED).read_text() + "\nexec sh -c true\n")
    _with(session, ip_tcl=[ALLOWED])
    with pytest.raises(SecurityError, match="differs from its reviewed version"):
        load_build_cfg(session)


def test_globs_and_parent_paths_are_refused(session) -> None:
    for bad in (["designs/*/ip/*.tcl"], ["../x.tcl"], ["/tmp/x.tcl"], "designs/b59a_axi_tx/ip/amd_ip.tcl"):
        _with(session, ip_tcl=bad)
        with pytest.raises(SecurityError):
            load_build_cfg(session)


def test_unknown_build_yaml_key_is_refused(session) -> None:
    _with(session, tcl_hook="source x.tcl")
    with pytest.raises(SecurityError, match="unknown key"):
        load_build_cfg(session)
    assert "unknown key 'tcl_hook'" in check_artefact("build.yaml", (session.design / "build.yaml").read_text())


def test_the_allowed_path_passes(session) -> None:
    dst = session.root / ALLOWED
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / ALLOWED, dst)
    _with(session, ip_tcl=[ALLOWED])
    assert load_build_cfg(session)["ip_tcl"] == [ALLOWED]
    assert ip_tcl_allow.check([ALLOWED]) == [(ROOT / ALLOWED).resolve()]


def test_prepare_refuses_unlisted_tcl_for_every_build(tmp_path) -> None:
    d = ROOT / "designs" / "b59a_axi_tx"
    cfg = yaml.safe_load((d / "build.yaml").read_text())
    assert cfg["ip_tcl"] == [ALLOWED]
    bad = tmp_path / "evil.tcl"
    bad.write_text("exec sh -c true\n")
    with pytest.raises(ip_tcl_allow.IpTclRefused):
        ip_tcl_allow.check([str(bad)])
    r = subprocess.run([sys.executable, str(ROOT / "flow" / "prepare.py"), "designs/b59a_axi_tx", "--out", str(tmp_path / "o")],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr           # the listed file passes through prepare
    # a design whose build.yaml names unlisted Tcl: prepare stops before any Vivado
    d2 = ROOT / "designs" / "_t59a_ip_tcl_probe"
    try:
        d2.mkdir()
        (d2 / "evil.tcl").write_text("exec sh -c true\n")
        (d2 / "build.yaml").write_text(yaml.safe_dump({**cfg, "ip_tcl": ["designs/_t59a_ip_tcl_probe/evil.tcl"]}))
        r = subprocess.run([sys.executable, str(ROOT / "flow" / "prepare.py"), "designs/_t59a_ip_tcl_probe", "--out",
                            str(tmp_path / "o2")], capture_output=True, text=True, cwd=ROOT)
        assert r.returncode != 0 and "not in flow/ip_tcl_allow.yaml" in r.stderr + r.stdout
    finally:
        shutil.rmtree(d2, ignore_errors=True)


def test_axi_board_run_refuses_while_the_board_is_locked(session, tmp_path, monkeypatch) -> None:
    """The agent's board tool takes the board lock; while someone else holds it, it refuses before touching hardware."""
    from agent.core import axi_tools
    from flow import hw
    from hil.instruments import board_lock
    lock = tmp_path / "board.lock"
    lock.write_text("FPGA other: a board job\n")
    monkeypatch.setattr(board_lock, "DEFAULT", lock)
    monkeypatch.setattr(board_lock.BoardLock.__init__, "__defaults__", (lock,))
    bdir = session.root / "designs" / "b59a_axi_tx" / "build" / "base"
    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / "x.bit").write_bytes(b"")
    monkeypatch.setattr(hw, "power_ok", lambda *a, **k: {"pass": True})
    session.stage = "configuration-and-debug"
    with pytest.raises(SecurityError) as e:
        axi_tools.axi_board_run(session, {"name": "p", "target": "periph", "steps": [{"read": {"addr": 0}}]})
    assert e.value.rule == "hardware-board-busy"
    assert lock.read_text() == "FPGA other: a board job\n"
    assert not session.runner.calls
