// bad_top.sv: a deliberately broken design. It exists only to make Vivado
// write reports in which every gate fails, so that flow/tests/test_gates.py
// can check the parsers against real failing reports (not hand-made ones).
//   - a 32x32 multiply in one 2 ns cycle: negative setup slack
//   - a 1-bit crossing from clk_a to clk_b with no synchroniser: a critical CDC
//   - in_none has no input delay and out_none no output delay: unconstrained
//   - no pin locations or I/O standards: DRC errors (NSTD-1, UCIO-1)
module bad_top (
    input  logic        clk_a,
    input  logic        clk_b,
    input  logic        in_fp,       // false-pathed, but no input delay
    input  logic        in_none,     // no constraint at all
    input  logic [31:0] x,
    input  logic [31:0] y,
    output logic        out_none,
    output logic [63:0] p
);
    logic        a_q, b_q;
    logic [31:0] xq, yq;
    always_ff @(posedge clk_a) begin
        a_q <= in_fp ^ in_none;
        xq  <= x;
        yq  <= y;
        p   <= xq * yq;
    end
    always_ff @(posedge clk_b) b_q <= a_q;     // unsynchronised crossing
    assign out_none = b_q;
endmodule
