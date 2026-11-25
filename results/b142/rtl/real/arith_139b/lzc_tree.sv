// lzc_tree: leading-zero count of a P-bit word (P a power of two, 2 or more) by recursive halving (brief 139b), combinational.
//   cnt = number of leading zeros when the word is non-zero; nz = the word is non-zero. For a zero word cnt is not meaningful.
// Primitive use (intended, not yet measured): each level is a 2:1 mux on the upper-half non-zero flag; a 6-input LUT absorbs about two
// levels, so the depth is about log2(P)/2 LUT levels plus routing; no carry chain.
module lzc_tree #(
    parameter int P = 8
) (
    input  logic [P-1:0]         x,
    output logic [$clog2(P)-1:0] cnt,
    output logic                 nz
);
    if (P == 2) begin : g_leaf
        assign cnt = ~x[1];
        assign nz  = x[1] | x[0];
    end else begin : g_node
        localparam int H = P / 2;
        logic [$clog2(H)-1:0] c_hi, c_lo;
        logic                 nz_hi, nz_lo;
        lzc_tree #(.P(H)) u_hi (.x(x[P-1:H]), .cnt(c_hi), .nz(nz_hi));
        lzc_tree #(.P(H)) u_lo (.x(x[H-1:0]), .cnt(c_lo), .nz(nz_lo));
        assign nz  = nz_hi | nz_lo;
        assign cnt = nz_hi ? {1'b0, c_hi} : {1'b1, c_lo};
    end
endmodule
