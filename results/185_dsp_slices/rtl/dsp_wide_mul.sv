// dsp_wide_mul (brief 185): a WA x WB signed multiply wider than one DSP slice, written three ways.
//
// STYLE 0: the `*` operator, with 1 operand register, 1 multiplier register and 1 output register (NA = 1; NA = 2 adds a second operand register);
//          Vivado chooses the decomposition (module dsp_mul_pipe at the full width).
// STYLE 1: hand-written cascade. a is cut into limbs of LA = 17 bits (low limbs unsigned, top limb signed, at most 18 bits: the narrow slice port),
//          b into limbs of LB bits (LB = 24 on DSP48E1 whose wide port is 25 bits; LB = 26 on DSP48E2, 27 bits). For each limb of b one chain
//          of slices computes P_i = a_i * b_j + (P_(i-1) >>> 17) (PCOUT to PCIN with the 17-bit shift); the low 17 bits shifted out at each stage are
//          collected, and the chains are added in the fabric with the shift LB * j. Operand, multiplier and output registers are written for every
//          stage (3 clocks per stage), operands are skewed by one clock per stage. Latency 2 + NAL clocks, plus 1 when there is more than one chain.
// STYLE 2: partial products in the fabric sum: the same NAL x NB limb products, each in its own slice (operand, multiplier, output register: 3 clocks),
//          then a binary adder tree with a register after every level. Latency 3 + ceil(log2(NAL * NB)).
// Latency is counted from the inputs a and b to p; one product per clock.
module dsp_wide_mul #(
    parameter int WA    = 32,
    parameter int WB    = 32,
    parameter int STYLE = 0,
    parameter int NA    = 1,      // STYLE 0: operand register depth (1 or 2)
    parameter int LB    = 24
) (
    input  logic                    clk,
    input  logic signed [WA-1:0]    a,
    input  logic signed [WB-1:0]    b,
    output logic signed [WA+WB-1:0] p
);
    localparam int LA   = 17;
    localparam int NAL  = (WA - 1 + LA - 1) / LA;           // limbs of a
    localparam int NBL  = (WB - 1 + LB - 1) / LB;           // limbs of b
    localparam int LAW  = LA + 1;                           // limb width on the narrow port
    localparam int LBW  = LB + 1;                           // limb width on the wide port
    localparam int PW   = WA + WB;

    // limb i of a (low limbs unsigned, zero-extended by one bit; top limb signed)
    function automatic logic signed [LAW-1:0] limb_a(input logic signed [WA-1:0] v, input int i);
        if (i == NAL - 1) limb_a = LAW'(v >>> (LA * i));
        else              limb_a = {1'b0, v[LA*i +: LA]};
    endfunction
    function automatic logic signed [LBW-1:0] limb_b(input logic signed [WB-1:0] v, input int j);
        if (j == NBL - 1) limb_b = LBW'(v >>> (LB * j));
        else              limb_b = {1'b0, v[LB*j +: LB]};
    endfunction

    if (STYLE == 0) begin : g_inferred
        dsp_mul_pipe #(.WA(WA), .WB(WB), .NA(NA), .NM(1), .NP(1), .RSTP(0)) u (.clk(clk), .rst(1'b0), .a(a), .b(b), .p(p));

    end else if (STYLE == 1) begin : g_cascade
        logic signed [PW-1:0] chain_val [NBL];
        for (genvar j = 0; j < NBL; j++) begin : g_chain
            logic signed [47:0] pq [NAL];                   // each stage's P register
            logic        [LA-1:0] low_al [NAL];             // low 17 bits of each stage, aligned to the last stage's clock
            for (genvar i = 0; i < NAL; i++) begin : g_stage
                // operands of stage i, skewed by i clocks
                logic signed [LAW-1:0] ai;
                logic signed [LBW-1:0] bj;
                if (i == 0) begin : g_s0
                    assign ai = limb_a(a, 0);
                    assign bj = limb_b(b, j);
                end else begin : g_sk
                    logic signed [LAW-1:0] sa [i];
                    logic signed [LBW-1:0] sb [i];
                    always_ff @(posedge clk) begin
                        sa[0] <= limb_a(a, i);
                        sb[0] <= limb_b(b, j);
                        for (int k = 1; k < i; k++) begin
                            sa[k] <= sa[k-1];
                            sb[k] <= sb[k-1];
                        end
                    end
                    assign ai = sa[i-1];
                    assign bj = sb[i-1];
                end
                logic signed [LAW-1:0] ar;
                logic signed [LBW-1:0] br;
                logic signed [LAW+LBW-1:0] mr;
                always_ff @(posedge clk) begin
                    ar <= ai;
                    br <= bj;
                    mr <= ar * br;
                end
                logic signed [47:0] prev;
                if (i == 0) begin : g_first
                    assign prev = '0;
                end else begin : g_next
                    assign prev = pq[i-1] >>> LA;
                end
                always_ff @(posedge clk) pq[i] <= 48'(mr) + prev;
                // low 17 bits of this stage, delayed (NAL - 1 - i) clocks to meet the last stage
                if (i == NAL - 1) begin : g_lastlow
                    assign low_al[i] = '0;
                end else begin : g_lowd
                    logic [LA-1:0] ld [NAL-1-i];
                    always_ff @(posedge clk) begin
                        ld[0] <= pq[i][LA-1:0];
                        for (int k = 1; k < NAL-1-i; k++) ld[k] <= ld[k-1];
                    end
                    assign low_al[i] = ld[NAL-2-i];
                end
            end
            logic signed [PW-1:0] v;
            always_comb begin
                v = PW'(pq[NAL-1]) <<< (LA * (NAL - 1));
                for (int i = 0; i < NAL - 1; i++) v = v | PW'({{(PW-LA){1'b0}}, low_al[i]} << (LA * i));
            end
            assign chain_val[j] = v;
        end
        if (NBL == 1) begin : g_one
            assign p = chain_val[0];
        end else begin : g_sum
            logic signed [PW-1:0] s;
            always_comb begin
                s = '0;
                for (int j = 0; j < NBL; j++) s = s + (chain_val[j] <<< (LB * j));
            end
            always_ff @(posedge clk) p <= s;
        end

    end else begin : g_fabric
        localparam int NT = NAL * NBL;
        localparam int LV = $clog2(NT);
        logic signed [PW-1:0] term [NT];
        for (genvar j = 0; j < NBL; j++) begin : g_j
            for (genvar i = 0; i < NAL; i++) begin : g_i
                logic signed [LAW-1:0] ar;
                logic signed [LBW-1:0] br;
                logic signed [LAW+LBW-1:0] mr, pr;
                always_ff @(posedge clk) begin
                    ar <= limb_a(a, i);
                    br <= limb_b(b, j);
                    mr <= ar * br;
                    pr <= mr;
                end
                assign term[j*NAL + i] = PW'(pr) <<< (LA * i + LB * j);
            end
        end
        if (LV == 0) begin : g_nt1
            assign p = term[0];
        end else begin : g_tree
            // level l has ceil(NT / 2^l) entries; every level is registered
            for (genvar l = 0; l < LV; l++) begin : g_lv
                localparam int NIN  = (NT + (1 << l) - 1) >> l;
                localparam int NOUT = (NIN + 1) / 2;
                logic signed [PW-1:0] o [NOUT];
                for (genvar k = 0; k < NOUT; k++) begin : g_k
                    if (l == 0) begin : g_l0
                        if (2*k+1 < NIN) begin : g_two
                            always_ff @(posedge clk) o[k] <= term[2*k] + term[2*k+1];
                        end else begin : g_one
                            always_ff @(posedge clk) o[k] <= term[2*k];
                        end
                    end else begin : g_lx
                        if (2*k+1 < NIN) begin : g_two
                            always_ff @(posedge clk) o[k] <= g_lv[l-1].o[2*k] + g_lv[l-1].o[2*k+1];
                        end else begin : g_one
                            always_ff @(posedge clk) o[k] <= g_lv[l-1].o[2*k];
                        end
                    end
                end
            end
            assign p = g_lv[LV-1].o[0];
        end
    end
endmodule
