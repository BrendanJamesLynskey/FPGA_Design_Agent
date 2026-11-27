"""Brief 246 (house rule 2026-11-27): an asynchronous reset on internal registers is asked once and accepted only on an emphatic confirmation, recorded
verbatim as the STD-RST-01 waiver; a reset that arrives asynchronously from the board is taken through a reset synchroniser at the boundary (STD-RST-02)."""
from pathlib import Path

import yaml

from agent.graph.interview import (ASYNC_RESET_QUESTION, apply_async_reset_answer, ensure_async_reset_question)
from flow import standards_check as sc

ARCH = {"schema": "fpga-design-agent/architecture/v1", "blocks": [{"name": "m", "function": "x"}], "interfaces": [],
        "clock_domains": [{"name": "sys", "clock": "clk", "freq_mhz": 100}], "crossings": [],
        "predicted_resources": {"lut": [1, 10], "ff": [1, 10], "bram_tile": 0, "dsp": 0}}
ASYNC_RTL = """module m (input logic clk, input logic rst_n, input logic d, output logic q);
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) q <= 1'b0; else q <= d;
    end
endmodule
"""


def _design(tmp_path: Path, rtl: str, spec_reset: dict | None = None, arch: dict | None = None) -> Path:
    d = tmp_path / "designs" / "x"
    (d / "rtl").mkdir(parents=True)
    (d / "rtl" / "m.sv").write_text(rtl)
    (d / "architecture.yaml").write_text(yaml.safe_dump({**ARCH, **(arch or {})}))
    (d / "build.yaml").write_text("top: m\npart: p\nsources: [designs/x/rtl/*.sv]\nconstraints: [designs/x/design.xdc]\n")
    if spec_reset is not None:
        (d / "spec.yaml").write_text(yaml.safe_dump({"reset": spec_reset}))
    return d


def _fail(d: Path, tmp_path: Path) -> dict:
    return {r["id"]: r for r in sc.evaluate(d, tmp_path, stages=("rtl",))["rules"] if r["status"] == "fail"}


# ---- the interview ----------------------------------------------------------------------------------------------

def test_a_request_for_an_async_reset_is_asked_once_with_the_cost_and_a_synchronous_default() -> None:
    spec, added = ensure_async_reset_question("A counter with an asynchronous active-low reset, 8 bits.", {})
    assert added and len(spec["open_questions"]) == 1
    q = spec["open_questions"][0]
    assert "UG949" in q["question"] and "STD-RST-01" in q["question"] and "timing" in q["question"] and "CONFIRM ASYNC RESET" in q["question"]
    assert q["default"].startswith("No.") and "synchronous" in q["default"]
    assert ensure_async_reset_question("asynchronous reset", spec)[1] is False                      # once
    assert ensure_async_reset_question("A counter with a synchronous reset.", {})[1] is False         # not asked when not wanted
    assert ensure_async_reset_question("The board's reset button is debounced.", {})[1] is False
    assert ensure_async_reset_question("async reset", {"reset": {"port": "rst", "async_waivers": [{"registers": ["q"]}]}})[1] is False


def _resolved(answer: str, status: str = "answered", by: str = "human") -> dict:
    return {"reset": {"port": "rst_n"}, "resolved_questions": [{"question": ASYNC_RESET_QUESTION, "answer": answer, "status": status, "by": by}]}


def test_an_emphatic_confirmation_is_recorded_verbatim_as_the_waiver() -> None:
    ans = "CONFIRM ASYNC RESET: q, cnt - the fabric reset must clear them with no clock running"
    out = apply_async_reset_answer(_resolved(ans))
    w = out["reset"]["async_waivers"]
    assert w == [{"rule": "STD-RST-01", "registers": ["q", "cnt"], "confirmation": ans, "by": "human"}]
    assert out["reset"]["port"] == "rst_n"
    assert apply_async_reset_answer(out) == out                                                          # idempotent


def test_a_plain_yes_the_default_or_an_oracle_records_no_waiver() -> None:
    for ans, st, by in (("yes", "answered", "human"), ("Yes, asynchronous reset please", "answered", "human"),
                        ("CONFIRM ASYNC RESET: q - x", "defaulted", "default"), ("CONFIRM ASYNC RESET: q - x", "answered", "oracle"),
                        ("CONFIRM ASYNC RESET", "answered", "human")):
        out = apply_async_reset_answer(_resolved(ans, st, by))
        assert "async_waivers" not in (out.get("reset") or {}), (ans, st, by)


# ---- the standards check ---------------------------------------------------------------------------------------

def test_an_internal_async_reset_fails_unless_the_user_confirmed_it_emphatically(tmp_path: Path) -> None:
    assert "STD-RST-01" in _fail(_design(tmp_path / "a", ASYNC_RTL, {"port": "rst_n"}), tmp_path / "a")
    ok = {"port": "rst_n", "async_waivers": [{"registers": ["q"], "confirmation": "CONFIRM ASYNC RESET: q - the clock may stop"}]}
    d = _design(tmp_path / "b", ASYNC_RTL, ok)
    assert "STD-RST-01" not in _fail(d, tmp_path / "b")
    weak = {"port": "rst_n", "async_waivers": [{"registers": ["q"], "confirmation": "yes please"}]}
    assert "STD-RST-01" in _fail(_design(tmp_path / "c", ASYNC_RTL, weak), tmp_path / "c")
    other = {"port": "rst_n", "async_waivers": [{"registers": ["zzz"], "confirmation": "CONFIRM ASYNC RESET: zzz - x"}]}
    assert "STD-RST-01" in _fail(_design(tmp_path / "e", ASYNC_RTL, other), tmp_path / "e")        # it names other registers


SYNC_TOP = """module m (input logic clk, input logic rst_n_in, input logic d, output logic q);
    logic rst_s;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(2), .RST_ACTIVE_HIGH(0)) u_rst (.dest_arst(rst_s), .dest_clk(clk), .src_arst(rst_n_in));
    always_ff @(posedge clk) begin
        if (!rst_s) q <= 1'b0; else q <= d;
    end
endmodule
"""
DIRECT_TOP = """module m (input logic clk, input logic rst_n_in, input logic d, output logic q);
    always_ff @(posedge clk) begin
        if (!rst_n_in) q <= 1'b0; else q <= d;
    end
endmodule
"""
SUB_TOP = """module m (input logic clk, input logic rst_n_in, input logic d, output logic q);
    sub u_sub (.clk(clk), .rst_n(rst_n_in), .d(d), .q(q));
endmodule
module sub (input logic clk, input logic rst_n, input logic d, output logic q);
    always_ff @(posedge clk) begin
        if (!rst_n) q <= 1'b0; else q <= d;
    end
endmodule
"""
BOARD = {"port": "rst_n_in", "asynchronous_input": True}


def test_a_board_async_reset_must_go_through_a_synchroniser_at_the_boundary(tmp_path: Path) -> None:
    assert "STD-RST-02" not in _fail(_design(tmp_path / "a", SYNC_TOP, BOARD), tmp_path / "a")
    for name, rtl in (("b", DIRECT_TOP), ("c", SUB_TOP)):
        f = _fail(_design(tmp_path / name, rtl, BOARD), tmp_path / name)
        assert "STD-RST-02" in f, name
    # not declared asynchronous: the rule does not apply (a testbench-driven synchronous reset keeps its cycle timing)
    assert "STD-RST-02" not in _fail(_design(tmp_path / "d", DIRECT_TOP, {"port": "rst_n_in"}), tmp_path / "d")
    # a synchroniser module declared in architecture.yaml counts
    arch = {"reset": {"synchronisers": ["my_rst_gen"]}}
    rtl = SYNC_TOP.replace("xpm_cdc_async_rst #(.DEST_SYNC_FF(2), .RST_ACTIVE_HIGH(0)) u_rst", "my_rst_gen u_rst")
    assert "STD-RST-02" not in _fail(_design(tmp_path / "e", rtl, BOARD, arch), tmp_path / "e")
