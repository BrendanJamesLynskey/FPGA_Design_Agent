"""Brief 50A: the RTL index and resolver (names from a request -> probe pins), on T1 and on small synthetic sources."""

from __future__ import annotations

from pathlib import Path

import pytest

from debug_core.rtl_index import RtlIndex, eval_expr

T1 = Path("designs/t1_dimmer_counter")


@pytest.fixture(scope="module")
def t1() -> RtlIndex:
    return RtlIndex.from_design(T1)


def test_t1_hierarchy_and_one_clock(t1: RtlIndex) -> None:
    assert {"u_dut", "u_shell.u_core", "u_shell.u_rx", "u_dut.u_db_up.u_sync"} <= set(t1.insts)
    assert t1.clock_domains() == ["CLK100MHZ"]


@pytest.mark.parametrize("query,path,width,pins", [
    ("u_dut.count", "u_dut.count", 16, "u_dut/count_reg[*]/Q"),
    ("u_dut/phase", "u_dut.phase", 8, "u_dut/phase_reg[*]/Q"),
    ("t1_dimmer_counter_top.u_dut.led", "u_dut.led", 16, "u_dut/led_reg[*]/Q"),
    ("u_shell.u_core.frame[1]", "u_shell.u_core.frame[1]", 8, "u_shell/u_core/frame_reg[1][*]/Q"),
    ("u_dut.pre", "u_dut.pre", 3, "u_dut/pre_reg[*]/Q"),                      # $clog2(PWM_PRESCALE + 1)
    ("u_shell.u_rx.cnt", "u_shell.u_rx.cnt", 10, "u_shell/u_rx/cnt_reg[*]/Q"),  # $clog2(868 + 1) with the top's value
    ("count[3]", "u_dut.count[3]", 1, "u_dut/count_reg[3]/Q"),
])
def test_registers_resolve_to_register_output_pins(t1, query, path, width, pins) -> None:
    r = t1.resolve(query)
    assert r.ok and r.kind == "register" and (r.path, r.width, r.pins) == (path, width, pins)
    assert r.clock == "CLK100MHZ"


def test_a_port_is_traced_to_the_register_that_drives_it(t1) -> None:
    r = t1.resolve("u_dut.win_wr")
    assert r.ok and r.pins == "u_shell/u_core/win_wr_reg/Q"
    assert r.trace == ["u_dut.win_wr", "win_wr", "u_shell.win_wr", "u_shell.u_core.win_wr"]
    out = t1.resolve("UART_RXD_OUT")                     # a top output driven by the UART transmitter's register
    assert out.ok and out.pins == "u_shell/u_tx/tx_reg/Q"


def test_probes_yaml_names_are_aliases(t1) -> None:
    r = t1.resolve("addr")
    assert r.ok and r.source == "probes.yaml" and r.pins == "u_shell/u_core/frame_reg[1][*]/Q" and r.width == 8
    assert r.path == "u_shell.u_core.frame[1]" and r.clock == "CLK100MHZ"


def test_top_input_pin(t1) -> None:
    r = t1.resolve("UART_TXD_IN")
    assert r.ok and r.kind == "top_input" and r.pins == "UART_TXD_IN_IBUF_inst/O"
    bus = t1.resolve("SW")                               # a 16-bit input: probe its synchroniser instead
    assert not bus.ok and "u_dut.u_sw_sync.s1" in bus.suggestions


def test_combinational_signal_is_an_error_with_register_suggestions(t1) -> None:
    r = t1.resolve("duty_eff")
    assert not r.ok and r.kind == "combinational"
    assert {"u_dut.ctrl", "u_dut.duty"} <= set(r.suggestions)


def test_ambiguous_and_unknown_names(t1) -> None:
    r = t1.resolve("cnt")
    assert not r.ok and r.kind == "ambiguous" and "u_shell.u_rx.cnt" in r.candidates and len(r.candidates) == 5
    same = t1.resolve("data")                            # two places, one register: not ambiguous
    assert same.ok and same.pins == "u_shell/u_rx/data_reg[*]/Q"
    assert not t1.resolve("fifo_overflow").ok
    ph = t1.resolve("uart tx")                           # a phrase: read as uart_tx
    assert ph.ok and ph.pins == "u_shell/u_tx/tx_reg/Q"
    nope = t1.resolve("fifo overflow flag")
    assert not nope.ok and nope.kind == "unresolved"


def test_arrays_need_an_element(t1) -> None:
    r = t1.resolve("u_shell.u_core.frame")
    assert not r.ok and r.suggestions == ["u_shell.u_core.frame[0]"]


def test_enum_state_register_carries_a_note(t1) -> None:
    r = t1.resolve("u_shell.u_rx.state")
    assert r.ok and r.width == 3 and any("FSM" in n for n in r.notes)


def test_eval_expr() -> None:
    env = {"N": 868, "W": 8}
    assert eval_expr("$clog2(N + 1)", env) == 10
    assert eval_expr("W-1", env) == 7
    assert eval_expr("32'h5431_4443", {}) == 0x54314443
    assert eval_expr("1_000_000 / 2", {}) == 500000
    assert eval_expr("UNKNOWN + 1", env) is None


SRC = """
module leaf #(parameter int W = 4, parameter int D = 3) (input logic clk, input logic [W-1:0] d, output logic [W-1:0] q);
  logic [W-1:0] pipe [D];
  always_ff @(posedge clk) begin
    pipe[0] <= d;
    q <= pipe[0];
  end
endmodule
module two #(parameter int A = 2) (input logic clk_a, input logic clk_b, input logic [7:0] din, output logic [7:0] dout);
  logic [7:0] ra; logic rb;
  leaf #(.W(8)) u_l (.clk(clk_b), .d(din), .q(dout));
  always_ff @(posedge clk_a) ra <= din;
  always @(posedge clk_b) rb <= ra[0];
  assign alias_ra = ra;
  logic [7:0] alias_ra;
endmodule
"""


def test_synthetic_parameters_clocks_and_aliases(tmp_path: Path) -> None:
    f = tmp_path / "two.sv"
    f.write_text(SRC)
    idx = RtlIndex.from_files([f], "two")
    assert idx.clock_domains() == ["clk_a", "clk_b"]
    q = idx.resolve("u_l.q")
    assert q.ok and q.width == 8 and q.clock == "clk_b"            # W overridden to 8
    assert idx.resolve("dout").pins == "u_l/q_reg[*]/Q"
    p = idx.resolve("u_l.pipe[2]")
    assert p.ok and p.pins == "u_l/pipe_reg[2][*]/Q"
    a = idx.resolve("alias_ra")
    assert a.ok and a.path == "ra" and a.clock == "clk_a"


def test_two_declarations_on_one_line(tmp_path: Path) -> None:
    """Review of brief 50A: the declaration after a ';' on the same line was dropped."""
    for decl, w in (("logic rb, fa;", 1), ("logic rb; logic fa;", 1), ("reg rb, fa;", 1), ("logic [3:0] rb, fa;", 4)):
        f = tmp_path / "t.sv"
        f.write_text("module top (input logic clk_a, input logic [7:0] din, output logic dout);\n  " + decl + "\n"
                     "  always_ff @(posedge clk_a) begin rb <= din[0]; fa <= din[1]; end\n  assign dout = rb;\nendmodule\n")
        idx = RtlIndex.from_files([f], "top")
        assert [(idx.resolve(q).ok, idx.resolve(q).width) for q in ("rb", "fa")] == [(True, w), (True, w)], decl
    f = tmp_path / "two.sv"
    f.write_text(SRC)
    assert RtlIndex.from_files([f], "two").resolve("rb").pins == "rb_reg/Q"


GEN = """
module leaf #(parameter int W = 4) (input logic clk, input logic [W-1:0] d, output logic [W-1:0] q);
  always_ff @(posedge clk) q <= d;
endmodule
module top (input logic clk, input logic clk2, input logic [7:0] din, output logic [7:0] dout, output logic [3:0] o4,
            output logic [7:0] plain);
  logic [7:0] gq [4];
  logic [3:0] r;
  genvar i;
  generate
    for (i = 0; i < 4; i++) begin : g
      leaf #(.W(8)) u_l (.clk(clk), .d(din), .q(gq[i]));
      logic gx;
      always_ff @(posedge clk) gx <= din[i];
      always_ff @(posedge clk) r[i] <= din[i];
    end
  endgenerate
  if (1) begin : gif
    leaf #(.W(8)) u_c (.clk(clk2), .d(din), .q(dout));
  end
  always_ff @(posedge clk) begin
    for (int k = 0; k < 8; k++) plain[k] <= din[k];
  end
  assign o4 = r;
endmodule
"""


@pytest.mark.parametrize("q", ["u_l.q", "g[0].u_l.q", "g.u_l.q", "gx", "g[1].gx", "r", "r[2]", "gq[1]", "dout", "u_c.q",
                               "gif.u_c.q", "o4"])
def test_names_in_generate_blocks_are_refused_not_guessed(tmp_path: Path, q: str) -> None:
    """Review of brief 50A: Vivado names cells in generate blocks after the block (g[0].u_l/...), so the flat names this
    index would have made were wrong; they are refused before any synthesis."""
    f = tmp_path / "gen.sv"
    f.write_text(GEN)
    r = RtlIndex.from_files([f], "top").resolve(q)
    assert not r.ok and r.pins == "" and any("generate block" in n for n in r.notes), r.as_dict()


def test_a_for_loop_inside_always_is_not_a_generate_block(tmp_path: Path) -> None:
    f = tmp_path / "gen.sv"
    f.write_text(GEN)
    r = RtlIndex.from_files([f], "top").resolve("plain")
    assert r.ok and r.pins == "plain_reg[*]/Q" and r.width == 8
