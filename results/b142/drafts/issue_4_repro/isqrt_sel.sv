// isqrt_sel: selects one square-root variant behind one packed stream interface (brief 139b).
//   VARIANT 0 restoring_iter, 1 restoring_pipe, 2 nonrestoring_pipe. PIPE applies to 1 and 2. in_data = x, out_data = {root, rem}.
module isqrt_sel #(
    parameter int VARIANT = 0,
    parameter int W       = 16,
    parameter int PIPE    = 1
) (
    input  logic                    clk,
    input  logic                    rst,
    input  logic                    in_valid,
    output logic                    in_ready,
    input  logic [W-1:0]            in_data,
    output logic                    out_valid,
    output logic [(W+1)/2+(W+1)/2:0] out_data
);
    localparam int RW = (W + 1) / 2;
    logic [RW-1:0] root;
    logic [RW:0]   rem;
    assign out_data = {root, rem};

    if (VARIANT == 0) begin : g_v
        isqrt_restoring_iter #(.W(W)) u (.clk, .rst, .in_valid, .in_ready, .x(in_data), .out_valid, .root, .rem);
    end else if (VARIANT == 1) begin : g_v
        isqrt_restoring_pipe #(.W(W), .PIPE(PIPE)) u (.clk, .rst, .in_valid, .in_ready, .x(in_data), .out_valid, .root, .rem);
    end else begin : g_v
        isqrt_nonrestoring_pipe #(.W(W), .PIPE(PIPE)) u (.clk, .rst, .in_valid, .in_ready, .x(in_data), .out_valid, .root, .rem);
    end
endmodule
