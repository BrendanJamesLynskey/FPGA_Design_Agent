// lznorm_stagewise_pipe: normaliser as a log-shifter whose stage decisions ARE the leading-zero count (brief 139b).
//   K = ceil(log2 W) stages, the one with step 2**k shifts left by 2**k when the top 2**k bits of the (zero-padded) word are all zero
//   and sets bit k of the count. No separate count-then-shift: each stage depends only on the previous stage's top bits.
//   PIPE stages per register group; latency ceil(K / PIPE) (PIPE >= K is one combinational block and one register). One result per clock.
// Primitive use (intended, not yet measured): per stage a NOR over the top 2**k bits (LUT6 tree, one level up to 6 bits, two to 36) and a
// 2:1 mux per data bit (LUT6, or a LUT6_2 pair shared with the NOR); the stage's depth is two to three LUT levels, so a group of
// PIPE stages is about PIPE * 2.5 LUT levels; flip-flops per register group: the padded word (P bits) and the count bits found so far.
module lznorm_stagewise_pipe #(
    parameter int W    = 16,
    parameter int PIPE = 1
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
    localparam int S  = (K + PIPE - 1) / PIPE;

    logic [P-1:0] v_q  [S];
    logic [K-1:0] c_q  [S];               // stage bits found so far (bit k set: the stage with step 2**k shifted)
    logic [S-1:0] val_q;

    assign in_ready = 1'b1;

    for (genvar s = 0; s < S; s++) begin : g_stage
        localparam int HI = K - 1 - s * PIPE;                       // first (largest) step of this group is 2**HI
        localparam int IT = (HI + 1 < PIPE) ? (HI + 1) : PIPE;
        logic [P-1:0] v_i, v_c;
        logic [K-1:0] c_i, c_c;
        logic         val_i;
        if (s == 0) begin : g_first
            assign v_i   = {x, {(P - W){1'b0}}};
            assign c_i   = '0;
            assign val_i = in_valid;
        end else begin : g_next
            assign v_i   = v_q[s-1];
            assign c_i   = c_q[s-1];
            assign val_i = val_q[s-1];
        end
        always_comb begin : iterate
            logic [P-1:0] v_v;
            logic [K-1:0] c_v;
            v_v = v_i;
            c_v = c_i;
            for (int j = 0; j < IT; j++) begin
                if ((v_v >> (P - (1 << (HI - j)))) == '0) begin     // the top 2**(HI-j) bits are zero
                    v_v = v_v << (1 << (HI - j));
                    c_v[HI-j] = 1'b1;
                end
            end
            v_c = v_v;
            c_c = c_v;
        end
        always_ff @(posedge clk) begin
            v_q[s] <= v_c;
            c_q[s] <= c_c;
        end
        always_ff @(posedge clk) begin
            if (rst) val_q[s] <= 1'b0;
            else     val_q[s] <= val_i;
        end
    end

    assign out_valid = val_q[S-1];
    assign y         = v_q[S-1][P-1:P-W];
    assign lz        = v_q[S-1][P-1] ? LW'(c_q[S-1]) : LW'(W);      // after normalising the MSB is set exactly when x is not zero
    if (P > W) begin : g_unused
        logic unused;
        assign unused = &{1'b0, v_q[S-1][P-W-1:0]};
    end
endmodule
