// dsp_dot (brief 185): K-term dot product y = sum of a_k * b_k (all signed W bits), one result per clock, two structures.
//
// STYLE 0 (cascade, systolic): stage k computes P_k <= m_k + P_(k-1) (PCOUT to PCIN, no fabric adder), operand registers, multiplier register and
//         P register in every stage; stage k's operands are delayed by k clocks. Latency 2 + K clocks from the operands to y.
// STYLE 1 (tree): every product in its own slice (operand, multiplier and output register), then a binary adder tree in the fabric; the tree
//         has a register after every TR levels and after the last level. Latency 3 + the number of those registers.
module dsp_dot #(
    parameter int W     = 16,
    parameter int K     = 8,
    parameter int STYLE = 0,
    parameter int TR    = 1
) (
    input  logic                              clk,
    input  logic signed [K*W-1:0]             a,
    input  logic signed [K*W-1:0]             b,
    output logic signed [2*W+$clog2(K)-1:0]   y
);
    localparam int OW = 2 * W + $clog2(K);
    if (STYLE == 0) begin : g_cascade
        logic signed [OW-1:0] pq [K];
        for (genvar k = 0; k < K; k++) begin : g_k
            logic signed [W-1:0] ai, bi;
            if (k == 0) begin : g_s0
                assign ai = a[0 +: W];
                assign bi = b[0 +: W];
            end else begin : g_sk
                logic signed [W-1:0] sa [k];
                logic signed [W-1:0] sb [k];
                always_ff @(posedge clk) begin
                    sa[0] <= a[k*W +: W];
                    sb[0] <= b[k*W +: W];
                    for (int j = 1; j < k; j++) begin
                        sa[j] <= sa[j-1];
                        sb[j] <= sb[j-1];
                    end
                end
                assign ai = sa[k-1];
                assign bi = sb[k-1];
            end
            logic signed [W-1:0]   ar, br;
            logic signed [2*W-1:0] mr;
            always_ff @(posedge clk) begin
                ar <= ai;
                br <= bi;
                mr <= ar * br;
            end
            if (k == 0) begin : g_f
                always_ff @(posedge clk) pq[k] <= OW'(mr);
            end else begin : g_n
                always_ff @(posedge clk) pq[k] <= OW'(mr) + pq[k-1];
            end
        end
        assign y = pq[K-1];
    end else begin : g_tree
        logic signed [2*W-1:0] prod [K];
        for (genvar k = 0; k < K; k++) begin : g_p
            logic signed [W-1:0]   ar, br;
            logic signed [2*W-1:0] mr, pr;
            always_ff @(posedge clk) begin
                ar <= a[k*W +: W];
                br <= b[k*W +: W];
                mr <= ar * br;
                pr <= mr;
            end
            assign prod[k] = pr;
        end
        localparam int LV = $clog2(K);
        if (LV == 0) begin : g_k1
            assign y = OW'(prod[0]);
        end else begin : g_t
            for (genvar l = 0; l < LV; l++) begin : g_lv
                localparam int NIN  = (K + (1 << l) - 1) >> l;
                localparam int NOUT = (NIN + 1) / 2;
                localparam bit REG  = (((l + 1) % TR) == 0) || (l == LV - 1);
                logic signed [OW-1:0] s [NOUT];     // this level's sums (registered when REG)
                logic signed [OW-1:0] o [NOUT];
                for (genvar k = 0; k < NOUT; k++) begin : g_k
                    if (l == 0) begin : g_l0
                        if (2*k+1 < NIN) begin : g_two
                            assign s[k] = OW'(prod[2*k]) + OW'(prod[2*k+1]);
                        end else begin : g_one
                            assign s[k] = OW'(prod[2*k]);
                        end
                    end else begin : g_lx
                        if (2*k+1 < NIN) begin : g_two
                            assign s[k] = g_lv[l-1].o[2*k] + g_lv[l-1].o[2*k+1];
                        end else begin : g_one
                            assign s[k] = g_lv[l-1].o[2*k];
                        end
                    end
                    if (REG) begin : g_r
                        always_ff @(posedge clk) o[k] <= s[k];
                    end else begin : g_c
                        assign o[k] = s[k];
                    end
                end
            end
            assign y = g_lv[LV-1].o[0];
        end
    end
endmodule
