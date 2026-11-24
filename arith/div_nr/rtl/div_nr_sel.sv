// div_nr_sel: selects one reciprocal-multiply divider behind one packed stream interface (brief 139c).
//   VARIANT 0 newton, 1 goldschmidt. in_data = {a, b} (each W bits, normalised), out_data = q (W bits, approximately a * 2**(W-1) / b).
module div_nr_sel #(
    parameter int VARIANT = 0,
    parameter int W       = 16,
    parameter int A       = 7,
    parameter int IT      = 2
) (
    input  logic           clk,
    input  logic           rst,
    input  logic           in_valid,
    output logic           in_ready,
    input  logic [2*W-1:0] in_data,
    output logic           out_valid,
    output logic [W-1:0]   out_data
);
    if (VARIANT == 0) begin : g_v
        div_nr_newton #(.W(W), .A(A), .IT(IT)) u (.clk, .rst, .in_valid, .in_ready, .a(in_data[2*W-1:W]), .b(in_data[W-1:0]), .out_valid, .q(out_data));
    end else begin : g_v
        div_nr_gs #(.W(W), .A(A), .IT(IT)) u (.clk, .rst, .in_valid, .in_ready, .a(in_data[2*W-1:W]), .b(in_data[W-1:0]), .out_valid, .q(out_data));
    end
endmodule
