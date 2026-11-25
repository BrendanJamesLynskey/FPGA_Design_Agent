"""Brief 209a: bring-up over the JTAG register bus for a board with no UART (flow/host_transport.py, flow/bringup.py, flow/hw_dry_check.py).
Every check here runs against a mock bus: no board, no Vivado."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from flow import bringup, host_transport as H, hw, hw_dry_check

ROOT = Path(__file__).resolve().parents[2]

HW_CHECKS = '''"""toy design: two registers and an LED blink"""
from flow.host_transport import MockBus

DESIGN_ID = 0x20920009


class Mock(MockBus):
    ID = DESIGN_ID

    def __init__(self, **f):
        super().__init__(**f)
        self.ctl = 0
        self.div = 0

    def read(self, a):
        return {0x010: self.ctl, 0x014: self.div}.get(a, 0)

    def write(self, a, v):
        if a == 0x010:
            self.ctl = v & 1
        elif a == 0x014:
            self.div = v & 0xFFFF


def make_mock(**f):
    return Mock(**f)


def run(bus):
    out = []
    bus.wr(0x010, 1)
    out.append(("ctl_reads_back", bus.rd(0x010) == 1, ""))
    bus.wr(0x014, 0x1234)
    out.append(("div_reads_back", bus.rd(0x014) == 0x1234, ""))
    bus.wr(0x010, 0)
    bus.wr(0x014, 0)
    return out
'''
BRINGUP_MD = "# Setup\n\n# Testing\n\n# Debug aids\n\n# If it fails\n"


def design(tmp_path: Path, checks: str = HW_CHECKS) -> Path:
    d = tmp_path / "toy"
    d.mkdir()
    (d / "hw_checks.py").write_text(checks)
    (d / "BRINGUP.md").write_text(BRINGUP_MD)
    return d


def test_the_transport_follows_the_board_file():
    assert H.board_transport("kr260", ROOT) == "jtag_bus"
    assert H.board_transport("nexys_a7_100t", ROOT) == "uart"
    assert H.board_transport("no_such_board", ROOT) == "uart"
    assert H.board_transport(None, ROOT) == "uart"
    assert H.transport({"uart": {"port": "x"}, "host_access": "JTAG"}) == "uart"
    assert H.transport({"host_access": "JTAG cable (BSCANE2 USER4 register bus); no PL UART pins"}) == "jtag_bus"


def test_every_board_in_the_repo_has_a_defined_transport():
    for f in sorted((ROOT / "boards").glob("*/board.yaml")):
        assert H.board_transport(f.parent.name, ROOT) in H.TRANSPORTS


def test_the_mock_runs_every_check_and_a_wrong_build_fails(tmp_path):
    d = design(tmp_path)
    r = H.run_mock(d)
    assert r["ok"], r
    names = [c["name"] for c in r["checks"]]
    assert names[:3] == ["id_register", "build_stamp", "scratch_register"] and "div_reads_back" in names
    mod = H.load_hw_checks(d)
    bad = H.run_checks(mod, mod.make_mock(), expected_build=0xDEAD0001)       # the board's USR_ACCESS differs from the build's
    assert [n for n, ok, _ in bad if not ok] == ["build_stamp"]


def test_a_design_that_misreads_its_own_registers_fails_in_ci(tmp_path):
    d = design(tmp_path, HW_CHECKS.replace("self.div = v & 0xFFFF", "self.div = v & 0xFF"))
    r = H.run_mock(d)
    assert not r["ok"] and "div_reads_back" in r["error"]


def test_missing_pieces_are_named(tmp_path):
    d = design(tmp_path, "DESIGN_ID = 1\n")
    assert "make_mock" in H.run_mock(d)["error"]
    probs = hw_dry_check.check_design(d, "jtag_bus")["problems"]
    assert any("make_mock" in p for p in probs) and any("run(" in p for p in probs)
    assert not any("tests/test_" in p or "probes.yaml" in p for p in probs)         # a JTAG design needs neither
    assert hw_dry_check.check_design(design(tmp_path / "x" if (tmp_path / "x").mkdir() is None else tmp_path), "jtag_bus")["ok"]


def test_the_uart_check_is_unchanged(tmp_path):
    probs = hw_dry_check.check_design(design(tmp_path))["problems"]            # the default transport
    assert any("CAPTURES" in p for p in probs) and any("probes.yaml" in p for p in probs)


def test_bringup_over_the_bus_with_a_mock(tmp_path, monkeypatch):
    d = design(tmp_path)
    mod = H.load_hw_checks(d)
    monkeypatch.setattr(bringup.hw, "ROOT", tmp_path)
    monkeypatch.setattr(bringup.program, "program", lambda *a, **k: {"pass": True, "build_stamp": "ab12", "build_id": "1234abcd"})

    class FakeServer:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
    monkeypatch.setattr(bringup.hw, "HwServer", FakeServer)
    monkeypatch.setattr(bringup.hw, "git_commit", lambda: ("0" * 40, False))
    shared = mod.make_mock()
    shared.BUILD = 0x1234ABCD
    opened = []

    def factory(serial):
        opened.append(serial)
        return shared
    run = bringup.Run(d, "kr260", False, tmp_path / "res", cable_serial="SERIAL123456", bus_factory=factory)
    # the design directory must be under hw.ROOT for the record's relative path
    assert run.transport == "jtag_bus"
    rc = run.run()
    rec = json.loads((tmp_path / "res" / "toy_bringup.json").read_text())
    assert rc == 0 and rec["pass"], rec
    assert list(rec["steps"]) == ["discover", "program_base", "bus_checks", "still_alive"]      # no UART steps, no ILA
    assert rec["steps"]["bus_checks"]["expected_build"] == 0x1234ABCD and "SERIAL123456" not in json.dumps(rec)
    assert opened == ["SERIAL123456", "SERIAL123456"]


def test_bringup_refuses_without_a_cable_serial(tmp_path, monkeypatch):
    d = design(tmp_path)
    monkeypatch.setattr(bringup.hw, "ROOT", tmp_path)
    monkeypatch.setattr(bringup.hw, "git_commit", lambda: ("0" * 40, False))

    class FakeServer:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): return None
    monkeypatch.setattr(bringup.hw, "HwServer", FakeServer)
    run = bringup.Run(d, "kr260", False, tmp_path / "res")
    assert run.run() == 1
    assert json.loads((tmp_path / "res" / "toy_bringup.json").read_text())["failed_step"] == "discover"


def test_ip_lib_entry_files_exist_and_the_bus_is_the_b58a_one():
    a = (ROOT / "ip_lib/jtag_regs/rtl/jtag_bus.sv").read_text()
    assert a == (ROOT / "designs/b58a_trigger/rtl/jtag_bus.sv").read_text()


def test_mutation_compiles_with_the_supplied_bus_kept_outside_rtl(tmp_path, monkeypatch):
    """A mutant of rtl/ is compiled with the build's other sources (data/jtag_bus.sv), or every mutant looks invalid (found in the 209a toy run)."""
    from flow import mutate
    monkeypatch.setattr(mutate, "ROOT", tmp_path)
    d = tmp_path / "runs" / "r" / "toy"
    (d / "rtl").mkdir(parents=True)
    (d / "data").mkdir()
    (d / "rtl" / "top.sv").write_text("module top; endmodule\n")
    (d / "data" / "jtag_bus.sv").write_text("module jtag_bus; endmodule\n")
    (d / "data" / "rom.hex").write_text("00\n")
    (d / "build.yaml").write_text("top: top\nsources:\n- runs/r/toy/rtl/*.sv\n- runs/r/toy/data/jtag_bus.sv\n")
    assert [p.name for p in mutate.vendored_sources(d)] == ["jtag_bus.sv"]
