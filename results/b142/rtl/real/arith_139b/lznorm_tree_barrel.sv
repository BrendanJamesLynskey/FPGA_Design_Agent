// lznorm_tree_barrel: leading-zero count by a tree, then a barrel shifter, in one clock (brief 139b). Latency 1.
//   lz = leading zeros of x (W when x = 0); y = x << lz truncated to W bits.
// Primitive use (intended, not yet measured): the count tree (lzc_tree) feeds a log2(W)-stage barrel shifter built of 2:1 / 4:1 muxes
// (LUT6 pairs, MUXF7/F8 for the 4:1 and 8:1 steps on 7-series); the count must be complete before the shifter starts, so the path is
// tree levels plus shifter levels. No carry chain, no DSP.
module lznorm_tree_barrel #(
    parameter int W = 16                  // 2 or more
) (
    input  logic                    clk,
    input  logic                    rst,
    input  logic                    in_valid,
    output logic                    in_ready,
    input  logic [W-1:0]            x,
    output logic                    out_valid,
    output logic [$clog2(W+1)-1:0]  lz,
    output logic [W-1:0]            y
);
    localparam int K  = $clog2(W);
    localparam int P  = 1 << K;
    localparam int LW = $clog2(W + 1);

    logic [P-1:0]  xp;
    logic [K-1:0]  cnt;
    logic          nz;
    logic [LW-1:0] lz_c;

    assign in_ready = 1'b1;
    assign xp = {x, {(P - W){1'b0}}};
    lzc_tree #(.P(P)) u_tree (.x(xp), .cnt, .nz);
    assign lz_c = nz ? LW'(cnt) : LW'(W);

    always_ff @(posedge clk) begin
        if (rst) out_valid <= 1'b0;
        else     out_valid <= in_valid;
    end
    always_ff @(posedge clk) begin
        lz <= lz_c;
        y  <= x << lz_c;
    end
endmodule
