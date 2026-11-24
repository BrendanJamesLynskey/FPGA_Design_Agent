// recip_sel: selects one reciprocal variant behind one packed stream interface (brief 139c).
//   VARIANT 0 table, 1 nr1 (table + 1 Newton step), 2 nr2 (table + 2). in_data = b (W bits, normalised), out_data = y (W + 1 bits).
module recip_sel #(
    parameter int VARIANT = 1,
    parameter int W       = 16,
    parameter int A       = 7
) (
    input  logic         clk,
    input  logic         rst,
    input  logic         in_valid,
    output logic         in_ready,
    input  logic [W-1:0] in_data,
    output logic         out_valid,
    output logic [W:0]   out_data
);
    if (VARIANT == 0) begin : g_v
        recip_table #(.W(W), .A(A)) u (.clk, .rst, .in_valid, .in_ready, .b(in_data), .out_valid, .y(out_data));
    end else begin : g_v
        recip_nr #(.W(W), .A(A), .IT(VARIANT)) u (.clk, .rst, .in_valid, .in_ready, .b(in_data), .out_valid, .y(out_data));
    end
endmodule
