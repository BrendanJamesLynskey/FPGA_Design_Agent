// lznorm_sel: selects one leading-zero / normaliser variant behind one packed stream interface (brief 139b).
//   VARIANT 0 tree_barrel, 1 loop_barrel, 2 stagewise_pipe (PIPE stages per register group), 3 tree_barrel_2st. in_data = x, out_data = {lz, y}.
module lznorm_sel #(
    parameter int VARIANT = 0,
    parameter int W       = 16,
    parameter int PIPE    = 1
) (
    input  logic                         clk,
    input  logic                         rst,
    input  logic                         in_valid,
    output logic                         in_ready,
    input  logic [W-1:0]                 in_data,
    output logic                         out_valid,
    output logic [W+$clog2(W+1)-1:0]     out_data
);
    logic [$clog2(W+1)-1:0] lz;
    logic [W-1:0]           y;
    assign out_data = {lz, y};

    if (VARIANT == 0) begin : g_v
        lznorm_tree_barrel #(.W(W)) u (.clk, .rst, .in_valid, .in_ready, .x(in_data), .out_valid, .lz, .y);
    end else if (VARIANT == 1) begin : g_v
        lznorm_loop_barrel #(.W(W)) u (.clk, .rst, .in_valid, .in_ready, .x(in_data), .out_valid, .lz, .y);
    end else if (VARIANT == 2) begin : g_v
        lznorm_stagewise_pipe #(.W(W), .PIPE(PIPE)) u (.clk, .rst, .in_valid, .in_ready, .x(in_data), .out_valid, .lz, .y);
    end else begin : g_v
        lznorm_tree_barrel_2st #(.W(W)) u (.clk, .rst, .in_valid, .in_ready, .x(in_data), .out_valid, .lz, .y);
    end
endmodule
