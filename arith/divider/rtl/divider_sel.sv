// divider_sel: selects one divider variant behind one packed stream interface (brief 139b). The testbench, the formal wrapper and the
// out-of-context wrapper all use it, so the same module is simulated, proved and (later) built.
//   VARIANT 0 restoring_iter, 1 nonrestoring_iter, 2 restoring_pipe, 3 nonrestoring_pipe. PIPE applies to 2 and 3 only.
//   in_data = {n, d}, out_data = {q, r}.
module divider_sel #(
    parameter int VARIANT = 0,
    parameter int W       = 8,
    parameter int PIPE    = 1
) (
    input  logic           clk,
    input  logic           rst,
    input  logic           in_valid,
    output logic           in_ready,
    input  logic [2*W-1:0] in_data,
    output logic           out_valid,
    output logic [2*W-1:0] out_data
);
    logic [W-1:0] q, r;
    assign out_data = {q, r};

    if (VARIANT == 0) begin : g_v
        div_restoring_iter #(.W(W)) u (.clk, .rst, .in_valid, .in_ready, .n(in_data[2*W-1:W]), .d(in_data[W-1:0]), .out_valid, .q, .r);
    end else if (VARIANT == 1) begin : g_v
        div_nonrestoring_iter #(.W(W)) u (.clk, .rst, .in_valid, .in_ready, .n(in_data[2*W-1:W]), .d(in_data[W-1:0]), .out_valid, .q, .r);
    end else if (VARIANT == 2) begin : g_v
        div_restoring_pipe #(.W(W), .PIPE(PIPE)) u (.clk, .rst, .in_valid, .in_ready, .n(in_data[2*W-1:W]), .d(in_data[W-1:0]), .out_valid, .q, .r);
    end else begin : g_v
        div_nonrestoring_pipe #(.W(W), .PIPE(PIPE)) u (.clk, .rst, .in_valid, .in_ready, .n(in_data[2*W-1:W]), .d(in_data[W-1:0]), .out_valid, .q, .r);
    end
endmodule
