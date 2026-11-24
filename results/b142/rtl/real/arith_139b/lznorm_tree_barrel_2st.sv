// lznorm_tree_barrel_2st: lznorm_tree_barrel with a register between the count and the shifter (brief 139b). Latency 2.
// Primitive use (intended, not yet measured): as the tree version plus W + LW flip-flops (the word and the count); each stage is then
// roughly half the logic depth, at the price of the registers.
module lznorm_tree_barrel_2st #(
    parameter int W = 16
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
    logic          nz, v1;
    logic [LW-1:0] lz_c, lz_q;
    logic [W-1:0]  x_q;

    assign in_ready = 1'b1;
    assign xp = {x, {(P - W){1'b0}}};
    lzc_tree #(.P(P)) u_tree (.x(xp), .cnt, .nz);
    assign lz_c = nz ? LW'(cnt) : LW'(W);

    always_ff @(posedge clk) begin
        lz_q <= lz_c;
        x_q  <= x;
        lz   <= lz_q;
        y    <= x_q << lz_q;
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            v1        <= 1'b0;
            out_valid <= 1'b0;
        end else begin
            v1        <= in_valid;
            out_valid <= v1;
        end
    end
endmodule
