// divider_hr_sel: selects one high-radix divider variant behind one packed stream interface (brief 139c).
//   VARIANT 0 srt4_iter, 1 srt4_cpa, 2 srt4_pipe. PIPE applies to 2 only. in_data = {a, b}, out_data = {quo, rem} (quo 2K + 1 bits, rem W bits).
module divider_hr_sel #(
    parameter int VARIANT = 0,
    parameter int W       = 16,
    parameter int K       = 8,
    parameter int PIPE    = 1
) (
    input  logic             clk,
    input  logic             rst,
    input  logic             in_valid,
    output logic             in_ready,
    input  logic [2*W-1:0]   in_data,
    output logic             out_valid,
    output logic [2*K+W:0]   out_data
);
    logic [2*K:0] quo;
    logic [W-1:0] rem;
    assign out_data = {quo, rem};

    if (VARIANT == 0) begin : g_v
        divider_hr_iter #(.W(W), .K(K)) u (.clk, .rst, .in_valid, .in_ready, .a(in_data[2*W-1:W]), .b(in_data[W-1:0]), .out_valid, .quo, .rem);
    end else if (VARIANT == 1) begin : g_v
        divider_hr_cpa #(.W(W), .K(K)) u (.clk, .rst, .in_valid, .in_ready, .a(in_data[2*W-1:W]), .b(in_data[W-1:0]), .out_valid, .quo, .rem);
    end else begin : g_v
        divider_hr_pipe #(.W(W), .K(K), .PIPE(PIPE)) u (.clk, .rst, .in_valid, .in_ready, .a(in_data[2*W-1:W]), .b(in_data[W-1:0]), .out_valid, .quo, .rem);
    end
endmodule
