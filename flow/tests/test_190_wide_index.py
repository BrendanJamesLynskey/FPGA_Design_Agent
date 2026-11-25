"""Brief 190, item 17: the advisory fast-path check for data-dependent wide shifts and indexes (flow/checks/wide_index.py)."""
from __future__ import annotations

from pathlib import Path

from flow import checks as C
from flow.checks import wide_index as W

SRC = """
// fda:fast_path
module fast #(parameter int W = 64, parameter int LOG = $clog2(W)) (
    input  logic            clk,
    input  logic [W-1:0]    din,
    input  logic [LOG-1:0]  sh,
    input  logic [7:0]      narrow,
    output logic [W-1:0]    dout,
    output logic [7:0]      pick
);
    logic [W-1:0] mem [16];
    logic [W-1:0] a, b, c, d, e;
    always_comb begin
        a = din >> sh;                       // flagged: shift of a 64-bit vector by a signal
        b = din << 3;                        // constant amount
        c = din >> W / 2;                    // parameters only
        d = 64'd1 << sh;                     // a literal left operand (a decoder)
        e = {W{1'b0}};
        pick = din[sh*8 +: 8];               // flagged: indexed part-select by a signal
        for (int i = 0; i < 4; i++) e[i*8 +: 8] = din[i*8 +: 8];   // loop variable: constant after unrolling
    end
    logic [7:0] n2;
    assign n2 = narrow >> sh;                // 8-bit vector: below the threshold
    logic bit1;
    assign bit1 = din[sh];                   // flagged: bit-select of a 64-bit vector
    logic [W-1:0] r;
    assign r = mem[sh];                      // a RAM read, not a barrel shifter
    // a >> sh in a comment is ignored
endmodule

module slow (input logic [63:0] x, input logic [5:0] s, output logic [63:0] y);
    assign y = x >> s;                       // not declared fast-path: not examined
endmodule
"""


def test_flags_the_three_wide_variable_cases_and_nothing_else() -> None:
    fs, n_mod, unj = W.findings(SRC, set(), "fast.sv")
    assert n_mod == 1 and unj == 0
    assert sorted((f["code"], f["vector"], f["width"]) for f in fs) == [("FAST-INDEX-01", "din", 64), ("FAST-INDEX-01", "din", 64), ("FAST-SHIFT-01", "din", 64)]
    assert all(f["blocking"] is False and f["module"] == "fast" and f["where"].startswith("fast.sv:") for f in fs)
    lines = SRC.splitlines()
    for f in fs:                                          # the line number points at the flagged text
        assert "sh" in lines[int(f["where"].split(":")[1]) - 1]


def test_declared_by_name_and_all_modules_option() -> None:
    plain = SRC.replace("// fda:fast_path", "")
    assert W.findings(plain, set(), "x.sv")[1:] == (0, 0)
    fs, n, _ = W.findings(plain, {"slow"}, "x.sv")
    assert n == 1 and [f["module"] for f in fs] == ["slow"] and fs[0]["code"] == "FAST-SHIFT-01"
    assert W.findings(plain, set(), "x.sv", all_modules=True)[1] == 2


def test_threshold_and_unjudged_widths() -> None:
    t = "// fda:fast_path\nmodule m (input logic [15:0] v, input logic [3:0] s, input logic [`WIDE-1:0] u, output logic [15:0] y, output logic z);\n" \
        "assign y = v >> s;\nassign z = u[s];\nendmodule\n"
    assert W.findings(t, set())[0] == []                  # 16 bits is under the default threshold of 32
    fs, _, unj = W.findings(t, set(), min_width=16)
    assert [f["vector"] for f in fs] == ["v"] and unj == 1    # the macro-sized vector is counted, not judged


def test_width_evaluation() -> None:
    env = W._params("parameter int N = 40; localparam M = N * 2; localparam K = $clog2(N);")
    assert env == {"N": 40, "M": 80, "K": 6}
    assert W._eval("N+M-1", env) == 119 and W._eval("UNKNOWN-1", env) is None and W._eval("8'hFF", {}) == 255


def test_registry_entry_is_advisory_and_reads_the_architecture_declaration(tmp_path: Path) -> None:
    d = tmp_path / "d"
    (d / "rtl").mkdir(parents=True)
    (d / "build.yaml").write_text("top: slow\nsources: [d/rtl/t.sv]\n")
    (d / "rtl" / "t.sv").write_text(SRC.replace("// fda:fast_path", ""))
    run = C.CHECKS["fastpath"].run
    r = run(C.Ctx(design=d, scope="rtl", root=tmp_path))
    assert r["findings"] == [] and "no module declared" in r["parts"]["modules"]
    (d / "architecture.yaml").write_text("fast_path: [fast]\n")
    r = run(C.Ctx(design=d, scope="rtl", root=tmp_path))
    assert len(r["findings"]) == 3 and all(f["tool"] == "fastpath" and not f["blocking"] and f["severity"] == "advisory" for f in r["findings"])
    assert C.CHECKS["fastpath"].kind == "source" and set(C.CHECKS["fastpath"].scopes) == {"rtl", "synth", "route"}


def test_the_b110_decoder_shift_is_found_when_the_module_is_declared() -> None:
    """The measured trial: b110's itch_dec aligns a message with a 384-bit shift by the byte offset."""
    f = Path(__file__).resolve().parents[2] / "designs" / "b110_itch_ouch" / "rtl" / "itch_dec.sv"
    fs, n, _ = W.findings(f.read_text(), {"itch_dec"}, "itch_dec.sv")
    assert n == 1 and [(x["code"], x["vector"], x["width"]) for x in fs] == [("FAST-SHIFT-01", "m_w", 384)]
