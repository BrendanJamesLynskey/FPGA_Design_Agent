// credit_chan.sv: a credit-based pipelined channel between two AXI4-Stream ports (brief 151, library entry; owner 2026-11-21:
// favour AMBA AXI). s_axis_* is an AXI4-Stream slave port, m_axis_* an AXI4-Stream master port; between them the beats cross LF
// plain register stages (valid and data, no ready), a receiver buffer of CREDITS entries, and the credits come back through LB
// register stages. So it is the bridge from AXI4-Stream (valid/ready) to a credit link and back, in one block.
//
// WHEN TO USE IT. Use a pipe_reg slice (valid/ready) wherever a ready loop of one to a few slices closes timing: it is the
// AXI way and every tool and checker knows it. Use this block only where valid/ready does not fit: a long pipeline of many
// stages (or a distance of several clock regions or an SLR) where a ready that has to travel back through every stage cannot
// close timing, or where the forward wires must be plain registers so they can be placed anywhere. The price: CREDITS
// entries of buffer (full throughput needs CREDITS >= LF + LB + 2), and an AXI4-Stream interface only at the two ends, the
// link between them is not AXI. Do not chain these blocks end to end for no reason: each adds a buffer and a latency of LF + 1.
// AXI4-Stream rules kept at both ports: m_axis_tvalid is a flop; a beat offered and not taken stays offered unchanged; tvalid
// is low during and at the first edge after reset; s_axis_tready is a flop.
// Sideband: TLAST_EN, TKEEP_EN (W/8 bits, W a multiple of 8), TUSER_W carry tlast, tkeep, tuser as one packed word; off means
// not carried (output 0, input ignored). Reset aresetn (active low, synchronous), clock aclk. No reset on data.
// Parameters of the link: LF forward register stages (0 = the beat goes straight into the receiver buffer), LB credit-return
// stages (0 = the credit is counted in the clock the beat leaves). Behaviour (model.py, README):
//   latency   a beat accepted into an empty channel is visible at m_axis_* LF + 1 clocks later
//   credit round trip   RTT = LF + LB + 2 clocks; throughput = min(1, CREDITS / RTT) beats per clock (sink always ready)
// Credit-core below is the same channel on a bare valid/ready/data word, with the formal properties.

module credit_chan #(
    parameter int W        = 32,
    parameter int CREDITS  = 8,
    parameter int LF       = 1,
    parameter int LB       = 1,
    parameter int TLAST_EN = 0,
    parameter int TKEEP_EN = 0,
    parameter int TUSER_W  = 0
) (
    input  logic                         aclk,
    input  logic                         aresetn,
    input  logic                         s_axis_tvalid,
    output logic                         s_axis_tready,
    input  logic [W-1:0]                 s_axis_tdata,
    input  logic                         s_axis_tlast,
    input  logic [(W/8 > 0 ? W/8 : 1)-1:0] s_axis_tkeep,
    input  logic [(TUSER_W > 0 ? TUSER_W : 1)-1:0] s_axis_tuser,
    output logic                         m_axis_tvalid,
    input  logic                         m_axis_tready,
    output logic [W-1:0]                 m_axis_tdata,
    output logic                         m_axis_tlast,
    output logic [(W/8 > 0 ? W/8 : 1)-1:0] m_axis_tkeep,
    output logic [(TUSER_W > 0 ? TUSER_W : 1)-1:0] m_axis_tuser
`ifdef FORMAL
    , output logic [W-1:0] f_in_o, f_out_o
`endif
);
    localparam int KW  = (W/8 > 0) ? W/8 : 1;
    localparam int PWL = (TLAST_EN != 0) ? 1 : 0;
    localparam int PWK = (TKEEP_EN != 0) ? KW : 0;
    localparam int PWU = (TUSER_W > 0) ? TUSER_W : 0;
    localparam int PW  = W + PWL + PWK + PWU;          // the packed word: {tuser, tkeep, tlast, tdata}
    generate
        if (TLAST_EN < 0 || TLAST_EN > 1) begin : g_bad_tl
            initial $error("credit_chan: TLAST_EN must be 0 or 1 (got %0d)", TLAST_EN);
        end
        if (TKEEP_EN < 0 || TKEEP_EN > 1 || (TKEEP_EN == 1 && (W % 8) != 0)) begin : g_bad_tk
            initial $error("credit_chan: TKEEP_EN must be 0 or 1, and W a multiple of 8 when it is 1 (got %0d, W %0d)", TKEEP_EN, W);
        end
        if (TUSER_W < 0 || TUSER_W > 64) begin : g_bad_tu
            initial $error("credit_chan: TUSER_W must be in 0..64 (got %0d)", TUSER_W);
        end
    endgenerate
    wire [PW-1:0] pin;
    wire [PW-1:0] pout;
    assign pin[0 +: W]  = s_axis_tdata;
    assign m_axis_tdata = pout[0 +: W];
    generate
        if (PWL != 0) begin : g_tl
            assign pin[W] = s_axis_tlast;
            assign m_axis_tlast = pout[W];
        end else begin : g_ntl
            assign m_axis_tlast = 1'b0;
        end
        if (PWK != 0) begin : g_tk
            assign pin[W+PWL +: (PWK > 0 ? PWK : 1)] = s_axis_tkeep[(PWK > 0 ? PWK : 1)-1:0];
            assign m_axis_tkeep = pout[W+PWL +: (PWK > 0 ? PWK : 1)];
        end else begin : g_ntk
            assign m_axis_tkeep = '0;
        end
        if (PWU != 0) begin : g_tu
            assign pin[W+PWL+PWK +: (PWU > 0 ? PWU : 1)] = s_axis_tuser[(PWU > 0 ? PWU : 1)-1:0];
            assign m_axis_tuser = pout[W+PWL+PWK +: (PWU > 0 ? PWU : 1)];
        end else begin : g_ntu
            assign m_axis_tuser = '0;
        end
    endgenerate
    credit_core #(.W(PW), .CREDITS(CREDITS), .LF(LF), .LB(LB)) core (.clk(aclk), .rst(!aresetn), .s_valid(s_axis_tvalid),
        .s_ready(s_axis_tready), .s_data(pin), .m_valid(m_axis_tvalid), .m_ready(m_axis_tready), .m_data(pout)
`ifdef FORMAL
        , .f_in_o, .f_out_o
`endif
        );
endmodule

module credit_core #(
    parameter int W       = 32,
    parameter int CREDITS = 8,
    parameter int LF      = 1,
    parameter int LB      = 1
) (
    input  logic         clk,
    input  logic         rst,
    input  logic         s_valid,
    output logic         s_ready,
    input  logic [W-1:0] s_data,
    output logic         m_valid,
    input  logic         m_ready,
    output logic [W-1:0] m_data
`ifdef FORMAL
    , output logic [W-1:0] f_in_o, f_out_o
`endif
);
    localparam int CW = $clog2(CREDITS + 1);
    localparam int PW = (CREDITS > 1) ? $clog2(CREDITS) : 1;

    generate
        if (W < 1 || W > 1024) begin : g_bad_w
            initial $error("credit_core: W must be in 1..1024 (got %0d)", W);
        end
        if (CREDITS < 1 || CREDITS > 1024) begin : g_bad_credits
            initial $error("credit_core: CREDITS must be in 1..1024 (got %0d)", CREDITS);
        end
        if (LF < 0 || LF > 8) begin : g_bad_lf
            initial $error("credit_core: LF must be in 0..8 (got %0d)", LF);
        end
        if (LB < 0 || LB > 8) begin : g_bad_lb
            initial $error("credit_core: LB must be in 0..8 (got %0d)", LB);
        end
    endgenerate

    // ---- sender: the credit counter and the registered ready ------------------------------------------------------
    logic [CW-1:0] credits;
    logic          credit_in;                 // a credit arrives from the return path in this clock
    wire           send = s_valid && s_ready;
    logic [CW-1:0] credits_next;
    always_comb begin
        credits_next = credits;
        if (send && !credit_in) credits_next = credits - CW'(1);
        else if (!send && credit_in) credits_next = credits + CW'(1);
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            credits <= CW'(CREDITS);
            s_ready <= 1'b0;
        end else begin
            credits <= credits_next;
            s_ready <= (credits_next != '0);
        end
    end

    // ---- forward wires: LF plain register stages (valid and data, no ready) ---------------------------------------
    // fv[0] / fd[0] are the sender's beat in the clock it is sent; fv[i] / fd[i] is that beat after i edges
    wire [LF:0]         fv;
    wire [(LF+1)*W-1:0] fd;
    assign fv[0]      = send;
    assign fd[0 +: W] = s_data;
    genvar i;
    generate
        for (i = 1; i <= LF; i++) begin : g_f
            logic         vq;
            logic [W-1:0] dq;
            always_ff @(posedge clk) begin
                if (rst) vq <= 1'b0;
                else     vq <= fv[i-1];
                dq <= fd[(i-1)*W +: W];
            end
            assign fv[i]      = vq;
            assign fd[i*W +: W] = dq;
        end
    endgenerate
    wire          f_valid = fv[LF];
    wire [W-1:0]  f_data  = fd[LF*W +: W];

    // ---- receiver: CREDITS entries, a read pointer, a write pointer, a valid flop ----------------------------------
    logic [W-1:0]  mem [0:CREDITS-1];
    logic [PW-1:0] wp, rp;
    logic [CW-1:0] cnt;
    wire           pop = m_valid && m_ready;
    logic [CW-1:0] cnt_next;
    always_comb begin
        cnt_next = cnt;
        if (f_valid && !pop) cnt_next = cnt + CW'(1);
        else if (!f_valid && pop) cnt_next = cnt - CW'(1);
    end
    assign m_data = mem[rp];
    always_ff @(posedge clk) begin
        if (rst) begin
            wp      <= '0;
            rp      <= '0;
            cnt     <= '0;
            m_valid <= 1'b0;
        end else begin
            cnt     <= cnt_next;
            m_valid <= (cnt_next != '0);
            if (f_valid) wp <= (wp == PW'(CREDITS - 1)) ? '0 : wp + PW'(1);
            if (pop)     rp <= (rp == PW'(CREDITS - 1)) ? '0 : rp + PW'(1);
        end
        if (f_valid) mem[wp] <= f_data;
    end

    // ---- credit return: LB plain register stages (one bit: a credit per beat taken) --------------------------------
    // bv[0] is the take in the clock it happens; bv[j] is that credit after j edges
    wire [LB:0] bv;
    assign bv[0]     = pop;
    assign credit_in = bv[LB];
    genvar j;
    generate
        for (j = 1; j <= LB; j++) begin : g_b
            logic cq;
            always_ff @(posedge clk) begin
                if (rst) cq <= 1'b0;
                else     cq <= bv[j-1];
            end
            assign bv[j] = cq;
        end
    endgenerate

`ifdef FORMAL
    // Properties for SymbiYosys (formal/credit.sby), proved by k-induction: the credits conserve (credits held by the
    // sender + beats on the forward wires + beats in the receiver + credits on the return path = CREDITS), so the
    // receiver never overflows or underflows and the credit counter stays in 0..CREDITS. With the source numbering its
    // beats 0, 1, 2 ... (the wrapper), every beat on a forward stage or in the buffer holds the number its place in the
    // stream implies: nothing lost, repeated or reordered.
    logic f_init = 1'b1;
    always_ff @(posedge clk) f_init <= rst;
    logic [W-1:0] f_in, f_out;
    assign f_in_o  = f_in;
    assign f_out_o = f_out;
    always_ff @(posedge clk) begin
        if (rst) begin f_in <= '0; f_out <= '0; end
        else begin
            if (send) f_in <= f_in + W'(1);
            if (pop)  f_out <= f_out + W'(1);
        end
    end
    // beats on the forward stages 1..LF and credits on the return stages 1..LB, by running sums (generate, not loops)
    wire [32*(LF+1)-1:0] f_fsum;
    wire [32*(LB+1)-1:0] f_rsum;
    assign f_fsum[0 +: 32] = 32'd0;
    assign f_rsum[0 +: 32] = 32'd0;
    genvar gs;
    generate
        for (gs = 1; gs <= LF; gs++) begin : g_fs
            assign f_fsum[gs*32 +: 32] = f_fsum[(gs-1)*32 +: 32] + 32'(fv[gs]);
        end
        for (gs = 1; gs <= LB; gs++) begin : g_rs
            assign f_rsum[gs*32 +: 32] = f_rsum[(gs-1)*32 +: 32] + 32'(bv[gs]);
        end
    endgenerate
    wire [31:0] f_fwd = f_fsum[LF*32 +: 32];
    wire [31:0] f_ret = f_rsum[LB*32 +: 32];
    always_ff @(posedge clk) if (!f_init && !rst) begin
        cc_conserve: assert (32'(credits) + f_fwd + 32'(cnt) + f_ret == 32'(CREDITS));
        cc_credits_max: assert (credits <= CW'(CREDITS));
        cc_cnt_max: assert (cnt <= CW'(CREDITS));
        cc_ready: assert (s_ready == (credits != '0));
        cc_valid: assert (m_valid == (cnt != '0));
        cc_no_overflow: assert (!(f_valid && cnt == CW'(CREDITS) && !pop));
        cc_ptr_range: assert (32'(rp) < CREDITS && 32'(wp) < CREDITS);
        cc_ptr_gap: assert (32'(wp) == (32'(rp) + 32'(cnt)) % CREDITS);
        cc_count: assert (W'(f_in - f_out) == W'(f_fwd + 32'(cnt)));
        cc_flight__ante: cover (f_fwd != 32'd0 || f_ret != 32'd0);        // credits or beats are in flight: the conservation sum has more than one term
        cc_buffered__ante: cover (cnt != '0);
        cc_spent__ante: cover (credits == '0);                           // the sender has spent every credit: s_ready is low for want of one
        cc_full__ante: cover (cnt == CW'(CREDITS));                       // the receiver buffer is full: the overflow check is at its limit
        cc_wrap__ante: cover (cnt != '0 && 32'(rp) + 32'(cnt) >= CREDITS); // the stored beats wrap round the end of the buffer
    end
    // forward stages: stage k's beat has `cnt` beats in the buffer and the valid stages above it ahead of it
    wire [(LF+1)*W-1:0] f_ab;
    wire [LF:0] f_fwd_ok;
    wire [CREDITS-1:0] f_buf_ok;
    assign f_fwd_ok[0] = 1'b1;
    assign f_ab[LF*W +: W] = '0;
    genvar gi;
    generate
        for (gi = 0; gi < LF; gi++) begin : g_ab
            assign f_ab[gi*W +: W] = f_ab[(gi+1)*W +: W] + W'(fv[gi+1]);
        end
        for (gi = 1; gi <= LF; gi++) begin : g_fwd_inv
            assign f_fwd_ok[gi] = !fv[gi] || (fd[gi*W +: W] == f_out + W'(cnt) + f_ab[gi*W +: W]);
        end
        // the j-th beat in the buffer, counting from the read pointer, holds beat number f_out + j
        for (gi = 0; gi < CREDITS; gi++) begin : g_buf_inv
            wire [31:0] f_idx = (32'(rp) + gi >= CREDITS) ? (32'(rp) + gi - CREDITS) : (32'(rp) + gi);
            assign f_buf_ok[gi] = !(gi < 32'(cnt)) || (mem[f_idx] == f_out + W'(gi));
        end
    endgenerate
    // one assertion over every stage and every buffer entry (a label inside a generate loop would be created once per iteration and clash)
    always_ff @(posedge clk) if (!f_init && !rst) begin
        cc_fwd_data: assert (&f_fwd_ok);
        cc_buf_data: assert (&f_buf_ok);
        cc_fwd_data__ante: cover (|(fv >> 1));
        cc_buf_data__ante: cover (cnt != '0);
    end
`endif
endmodule
