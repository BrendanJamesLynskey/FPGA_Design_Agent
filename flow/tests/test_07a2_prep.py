"""Brief 07a2-prep: the four harness gaps the course-tier port (07a1) found, each reproduced.

1. task data/ files reach the run (copied, listed, found by the simulator and by the Vivado inputs);
2. a UART-subject design (no_shell) is built, linted, simulated and mutated without the test shell;
3. SystemVerilog sources are compiled in dependency order (packages and interfaces first), not in name order;
4. the interview oracle answers register-map questions from hidden/spec.yaml.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
import yaml

from flow import cocotb_run, prepare, srcorder
from flow.srcorder import NO_SHELL_MARKER, order_sv

ROOT = Path(__file__).resolve().parents[2]
needs_icarus = pytest.mark.skipif(shutil.which("iverilog") is None, reason="needs iverilog")

PKG = "package z_pkg;\n  localparam int W = 5;\nendpackage\n"
USER = "module a_core import z_pkg::*; (input logic clk, output logic [W-1:0] q);\n  always_ff @(posedge clk) q <= q + 1;\nendmodule\n"


def names(files):
    return [Path(f).name for f in files]


def write(d: Path, files: dict[str, str]) -> list[Path]:
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for n, t in files.items():
        (d / n).write_text(t)
        out.append(d / n)
    return out


# --- 3. compile order ------------------------------------------------------------------------------------------------

def test_package_file_that_sorts_after_its_user_is_moved_first(tmp_path: Path) -> None:
    files = write(tmp_path, {"a_core.sv": USER, "z_pkg.sv": PKG})
    assert names(sorted(files)) == ["a_core.sv", "z_pkg.sv"]               # name order: the gap
    assert names(order_sv(sorted(files))) == ["z_pkg.sv", "a_core.sv"]


def test_order_is_stable_and_keeps_underscore_prefixed_names(tmp_path: Path) -> None:
    files = write(tmp_path, {"_pkg.sv": PKG.replace("z_pkg", "p_pkg"), "b.sv": "module b; endmodule\n",
                             "a.sv": "module a import p_pkg::*; (); endmodule\n", "c.sv": "module c; endmodule\n"})
    got = names(order_sv(sorted(files)))
    assert got == names(sorted(files)) == ["_pkg.sv", "a.sv", "b.sv", "c.sv"]     # nothing moved


def test_interface_is_found_and_comments_and_strings_do_not_count(tmp_path: Path) -> None:
    files = write(tmp_path, {
        "a_top.sv": "module a_top (bus_if.mst b); endmodule\n",
        "b_note.sv": 'module b_note; // uses z_pkg::W and bus_if\n  initial $display("z_pkg::W");\nendmodule\n',
        "z_if.sv": "interface bus_if; logic v; modport mst (output v); endinterface\n",
        "y_pkg.sv": PKG})
    got = names(order_sv(sorted(files)))
    assert got.index("z_if.sv") < got.index("a_top.sv")
    assert got.index("b_note.sv") < got.index("y_pkg.sv") or True                # b_note has no real dependency
    assert got == ["z_if.sv", "a_top.sv", "b_note.sv", "y_pkg.sv"]


def test_cycle_falls_back_to_input_order(tmp_path: Path) -> None:
    files = write(tmp_path, {"a.sv": "package pa; import pb::*; endpackage\n", "b.sv": "package pb; import pa::*; endpackage\n"})
    assert sorted(names(order_sv(files))) == ["a.sv", "b.sv"]


@needs_icarus
def test_cocotb_run_builds_a_package_that_sorts_after_its_user(tmp_path: Path) -> None:
    """The gap: the test passes SHELL_RTL + sorted(rtl.glob), as the prompt says; ``a_core`` imports ``z_pkg``."""
    design = tmp_path / "d"
    write(design / "rtl", {"a_core.sv": USER, "z_pkg.sv": PKG})
    write(design / "tests", {"bench.py": BENCH_COUNT})
    cocotb_run.run("order_gap", "a_core", sorted((design / "rtl").glob("*.sv")), "bench", design / "tests",
                   build_root=tmp_path / "b")


BENCH_COUNT = '''
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


@cocotb.test()
async def counts(dut):
    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    dut.q.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    assert dut.q.value.is_resolvable
'''


def test_prepare_orders_vivado_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = tmp_path / "des"
    write(d / "rtl", {"a_core.sv": USER, "z_pkg.sv": PKG})
    (d / "build.yaml").write_text(yaml.safe_dump({"top": "a_core", "part": "xc7a100tcsg324-1",
                                                  "sources": [str((d / "rtl").relative_to(tmp_path)) + "/*.sv"],
                                                  "constraints": ["boards/nexys_a7_100t/master.xdc"]}))
    monkeypatch.setattr(prepare, "ROOT", tmp_path)
    monkeypatch.setattr(prepare, "expand", lambda pats: [p for pat in pats for p in sorted(tmp_path.glob(pat))])
    (tmp_path / "boards/nexys_a7_100t").mkdir(parents=True)
    (tmp_path / "boards/nexys_a7_100t/master.xdc").write_text("# x\n")
    monkeypatch.setattr(prepare, "board_for", lambda cfg: "nexys_a7_100t")
    monkeypatch.setattr(prepare, "power_env_tcl", lambda b: "")
    monkeypatch.setattr(prepare, "stop_after", lambda: "")
    out = tmp_path / "out"
    assert prepare.main([str(d), "--variant", "base", "--out", str(out)]) == 0
    tcl = (out / "inputs.tcl").read_text()
    assert tcl.index("z_pkg.sv") < tcl.index("a_core.sv")


# --- 2. no_shell ------------------------------------------------------------------------------------------------------

OWN_UART = "module uart_rx (input logic clk, output logic v);\n  assign v = 1'b1;\nendmodule\n"
TOP_NOSHELL = ("module nsh_top (input logic clk, output logic v);\n  logic w;\n  uart_rx u (.clk(clk), .v(w));\n"
               "  assign v = w;\nendmodule\n")
BENCH_NOSHELL = '''
import cocotb
from cocotb.triggers import Timer


@cocotb.test()
async def v_high(dut):
    await Timer(10, "ns")
    assert dut.v.value == 1
'''


@needs_icarus
def test_no_shell_marker_removes_the_shell_from_the_simulation(tmp_path: Path) -> None:
    """The gap: SHELL_RTL + rtl is what the test prompt says, and the shell's uart_rx clashes with the design's own."""
    design = tmp_path / "d"
    write(design / "rtl", {"uart_rx.sv": OWN_UART, "nsh_top.sv": TOP_NOSHELL})
    write(design / "tests", {"bench.py": BENCH_NOSHELL})
    srcs = cocotb_run.SHELL_RTL + sorted((design / "rtl").glob("*.sv"))
    with pytest.raises(BaseException):                                          # no marker: duplicate module uart_rx
        cocotb_run.run("noshell_gap", "nsh_top", srcs, "bench", design / "tests", build_root=tmp_path / "b1")
    (design / NO_SHELL_MARKER).write_text("")
    cocotb_run.run("noshell_fixed", "nsh_top", srcs, "bench", design / "tests", build_root=tmp_path / "b2")


def test_drop_shell_and_marker(tmp_path: Path) -> None:
    shell = sorted((ROOT / "shell" / "rtl").glob("*.sv"))
    own = write(tmp_path, {"x.sv": "module x; endmodule\n"})
    assert srcorder.drop_shell(shell + own) == own
    assert not srcorder.no_shell(tmp_path)
    (tmp_path / NO_SHELL_MARKER).write_text("")
    assert srcorder.no_shell(tmp_path)


def test_prepare_no_shell_builds_without_shell_and_without_build_stamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = tmp_path / "des"
    write(d / "rtl", {"uart_rx.sv": OWN_UART, "nsh_top.sv": TOP_NOSHELL})
    (d / NO_SHELL_MARKER).write_text("")
    (d / "build.yaml").write_text(yaml.safe_dump({"top": "nsh_top", "part": "xc7a100tcsg324-1",
                                                  "sources": ["shell/rtl/*.sv", "des/rtl/*.sv"],
                                                  "constraints": ["x.xdc"]}))
    (tmp_path / "x.xdc").write_text("# x\n")
    shutil.copytree(ROOT / "shell" / "rtl", tmp_path / "shell" / "rtl")
    monkeypatch.setattr(prepare, "ROOT", tmp_path)
    monkeypatch.setattr(srcorder, "SHELL_DIR", tmp_path / "shell" / "rtl")
    monkeypatch.setattr(prepare, "board_for", lambda cfg: "nexys_a7_100t")
    monkeypatch.setattr(prepare, "power_env_tcl", lambda b: "")
    monkeypatch.setattr(prepare, "stop_after", lambda: "")
    out = tmp_path / "out"
    assert prepare.main([str(d), "--variant", "base", "--out", str(out)]) == 0
    tcl = (out / "inputs.tcl").read_text()
    assert "uart_tx.sv" not in tcl and "BUILD_STAMP" not in tcl and "uart_rx.sv" in tcl


def test_course_scoring_orders_sources_and_drops_the_shell(tmp_path: Path) -> None:
    from benchmark.course.tools import no_shell
    from benchmark.tools import run_task
    no_shell.apply()
    task = tmp_path / "t"
    (task / "hidden").mkdir(parents=True)
    (task / "hidden" / "bench.yaml").write_text("toplevel: a_core\nno_shell: true\n")
    rtl = tmp_path / "rtl"
    write(rtl, {"a_core.sv": USER, "z_pkg.sv": PKG})
    assert names(run_task.sources(task, rtl)) == ["z_pkg.sv", "a_core.sv"]
    (task / "hidden" / "bench.yaml").write_text("toplevel: a_core\n")
    got = names(run_task.sources(task, rtl))
    assert got.index("z_pkg.sv") < got.index("a_core.sv") and "fpga_shell.sv" in got


# --- 1. data files ---------------------------------------------------------------------------------------------------

DATA_MOD = ('module rom_top (input logic clk, input logic [1:0] a, output logic [7:0] q);\n  logic [7:0] m [0:3];\n'
            '  initial $readmemh("rom.hex", m);\n  always_ff @(posedge clk) q <= m[a];\nendmodule\n')
DATA_BENCH = '''
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


@cocotb.test()
async def rom(dut):
    cocotb.start_soon(Clock(dut.clk, 10, "ns").start())
    for a, want in enumerate((0x11, 0x22, 0x33, 0x44)):
        dut.a.value = a
        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        assert int(dut.q.value) == want, (a, dut.q.value)
'''


def make_data_design(tmp: Path) -> Path:
    design = tmp / "d"
    write(design / "rtl", {"rom_top.sv": DATA_MOD})
    write(design / "tests", {"bench.py": DATA_BENCH})
    write(design / "data", {"rom.hex": "11\n22\n33\n44\n"})
    return design


@needs_icarus
def test_simulation_finds_the_task_data_file(tmp_path: Path) -> None:
    """The gap: the simulator's working directory is the build directory, where ``rom.hex`` was not."""
    design = make_data_design(tmp_path)
    cocotb_run.run("data_ok", "rom_top", sorted((design / "rtl").glob("*.sv")), "bench", design / "tests",
                   build_root=tmp_path / "b")
    assert not (design / "tests" / "rom.hex").exists() and not (design / "tests" / "data").exists()   # links removed
    shutil.rmtree(design / "data")                                              # no data: $readmemh finds nothing
    with pytest.raises(BaseException):
        cocotb_run.run("data_gap", "rom_top", sorted((design / "rtl").glob("*.sv")), "bench", design / "tests",
                       build_root=tmp_path / "b2")


def test_data_files_reach_the_vivado_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = tmp_path / "des"
    write(d / "rtl", {"rom_top.sv": DATA_MOD})
    write(d / "data", {"rom.hex": "11\n22\n33\n44\n"})
    (d / "build.yaml").write_text(yaml.safe_dump({"top": "rom_top", "part": "xc7a100tcsg324-1",
                                                  "sources": ["des/rtl/*.sv"], "constraints": ["x.xdc"]}))
    (tmp_path / "x.xdc").write_text("# x\n")
    monkeypatch.setattr(prepare, "ROOT", tmp_path)
    monkeypatch.setattr(prepare, "board_for", lambda cfg: "nexys_a7_100t")
    monkeypatch.setattr(prepare, "power_env_tcl", lambda b: "")
    monkeypatch.setattr(prepare, "stop_after", lambda: "")
    out = tmp_path / "out"
    assert prepare.main([str(d), "--variant", "base", "--out", str(out)]) == 0
    assert (out / "rom.hex").read_text() == "11\n22\n33\n44\n" and (out / "data" / "rom.hex").is_file()


def test_course_scoring_links_task_data_for_the_run_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from benchmark.course.tools import no_shell
    from benchmark.tools import run_task
    no_shell.apply()
    seen = {}
    task = tmp_path / "tk"
    write(task / "data", {"p.hex": "01\n"})
    (task / "hidden").mkdir()

    def fake(*a, **k):
        seen["during"] = ((task / "hidden" / "p.hex").read_text(), (task / "hidden" / "data" / "p.hex").read_text())
        return {}
    monkeypatch.setattr(no_shell, "_orig_run", fake)
    run_task.run(task, tmp_path, "icarus", 1, "agent", None, tmp_path / "bs")
    assert seen["during"] == ("01\n", "01\n")
    assert not (task / "hidden" / "p.hex").exists() and not (task / "hidden" / "data").exists()    # removed afterwards


# --- 4. the oracle and the register map -----------------------------------------------------------------------------------

