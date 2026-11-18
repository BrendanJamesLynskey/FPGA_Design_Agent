// tiny_acc: a 8-bit accumulator with a non-zero reset value, for the brief 101 tests (a register set by reset, an adder, a registered input).
`default_nettype none
module tiny_acc (
    input  wire logic       clk,
    input  wire logic       rst,
    input  wire logic [7:0] d,
    output logic [7:0]      acc
);
    logic [7:0] d_q;
    always_ff @(posedge clk) begin
        d_q <= d;
        if (rst) acc <= 8'hA5;
        else acc <= acc + d_q;
    end
endmodule
