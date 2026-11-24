// ddr2_props.sv (brief 141): the JEDEC timing rules, and the liveness and ordering properties, of ddr2_sched, attached by bind (ddr2_bind.sv); the RTL is not edited.
//
// Form. Yosys's free SystemVerilog front end (yosys-slang, OSS CAD Suite) reads only clocked Boolean assertions, no |-> or ##: so each rule is written as the Boolean check an SVA compiler would build
// from  `cmd_v && cmd_op == ACT |-> age_pre >= T_RP`  over a monitor register (a saturating "clocks since the last X"). The SVA text is in the comments marked SVA: for a commercial tool.
//
// Independence. The RTL enforces the rules with down-counters loaded at each command. The monitor knows nothing of those counters: it watches only the registered command output (cmd_v, cmd_op, cmd_bank)
// and keeps, for each kind of event, the number of clocks since it last happened (saturating at 255), and the open/closed state of each bank. A rule is "the age of the earlier event is at least N when the later
// command is on the bus". The rule constants are written here again from the data sheet (derived from the same parameters; the bench tb_ddr2.sv derives them from nanoseconds separately).
//
// Age convention: an event on the bus in clock t sets its age to 1 in clock t+1, so at a later command in clock t' the age holds t' - t.
// Assumptions: A1 reset only at step 0 (a reset in the middle would forget the open banks of a real part); A2 en rises once and stays (the part is initialised once); neither is used by a proof of a rule except to define the start.
// Property groups, so that a proof can be run on the rules alone (run_formal.py defines FV_NO_<group> for the others): R the JEDEC timing rules, D refresh debt, O ordering, B bounded response, I the helper invariants that tie the RTL's counters to the monitor's ages (they make the proof of R inductive).
`define FV_ON(NAME, EXPR) always_comb NAME: assert (first || (EXPR));
`ifdef FV_NO_R
`define FVR(NAME, EXPR)
`else
`define FVR(NAME, EXPR) `FV_ON(NAME, EXPR)
`endif
`ifdef FV_NO_D
`define FVD(NAME, EXPR)
`else
`define FVD(NAME, EXPR) `FV_ON(NAME, EXPR)
`endif
`ifdef FV_NO_O
`define FVO(NAME, EXPR)
`else
`define FVO(NAME, EXPR) `FV_ON(NAME, EXPR)
`endif
`ifdef FV_NO_I
`define FVI(NAME, EXPR)
`else
`define FVI(NAME, EXPR) `FV_ON(NAME, EXPR)
`endif
`ifdef FV_NO_B
`define FVB(NAME, EXPR)
`else
`define FVB(NAME, EXPR) `FV_ON(NAME, EXPR)
`endif
`define FVC(NAME, EXPR) always_comb NAME: cover (!first && (EXPR));
module ddr2_props #(
    parameter int NB_ = 8, parameter int QD = 4, parameter int BW = 3, parameter int RW = 13, parameter int CB = 7, parameter int TW = 6,
    parameter int T_RCD = 6, parameter int T_RP = 6, parameter int T_RPA = 7, parameter int T_RAS = 16, parameter int T_RC = 22, parameter int T_RRD = 4, parameter int T_FAW = 20,
    parameter int T_WR = 6, parameter int T_WTR = 3, parameter int T_RTP = 3, parameter int T_RFC = 51, parameter int T_REFI = 3120,
    parameter int RL = 6, parameter int WL = 5, parameter int BL2 = 4, parameter int AGE_LIM = 64, parameter int REF_POST = 4,
    parameter int BOUND = 100
) (
    input logic clk, rst, en,
    input logic req_v, req_rdy, req_wr, ref_defer,
    input logic [BW-1:0] a_bank, input logic [RW-1:0] a_row, input logic [CB-1:0] a_col,
    input logic cmd_v, input logic [2:0] cmd_op, input logic [BW-1:0] cmd_bank,
    input logic [QD-1:0] v, input logic [QD-1:0] w, input logic [QD-1:0][QD-1:0] dep, input logic [QD-1:0][BW-1:0] q_bank, input logic [QD-1:0][RW-1:0] q_row, input logic [QD-1:0][CB-1:0] q_col,
    input logic d_v, input logic [2:0] d_op, input logic [$clog2(QD)-1:0] d_slot, free_i,
    input logic [3:0] debt, input logic [$clog2(T_REFI+1)-1:0] tick,
    input logic [NB_-1:0] open_q,
    input logic [NB_-1:0][7:0] c_col, c_pre, c_rc, c_rp,
    input logic [3:0][7:0] c_faw,
    input logic ref_latched,
    input logic [7:0] c_rrd, c_rd, c_wr, c_rfc
);
    localparam int NB = 1 << BW;
    localparam logic [2:0] ACT = 3'd1, RD = 3'd2, WR = 3'd3, PRE = 3'd4, PREA = 3'd5, REF = 3'd6;
    localparam int RTW = RL + BL2 + 1 - WL;
    localparam int R2P = BL2 - 2 + ((T_RTP > 2) ? T_RTP : 2);
    localparam int W2P = WL + BL2 + T_WR;
    localparam int W2R = WL + BL2 + T_WTR;
    localparam int IW  = $clog2(QD);

    function automatic logic [7:0] inc(input logic [7:0] a);
        return (a == 8'd255) ? a : a + 8'd1;
    endfunction

    // ---------------------------------------------------------------- assumptions
    logic first = 1'b1;
    logic en_seen = 1'b0;
    always_ff @(posedge clk) begin
        first <= 1'b0;
        if (en) en_seen <= 1'b1;
    end
    always_comb begin
        if (first) assume (rst);                       // A1: reset at the first step
        if (!first) assume (!rst);                     //     and never again
        if (en_seen) assume (en);                      // A2: en stays high once high
        if (first) assume (!en);                       //     and starts low
    end

    // ---------------------------------------------------------------- monitor state
    logic [NB-1:0]  m_open = '0;
    logic [NB-1:0]  m_pa = '0;                         // the last precharge of the bank was a PRECHARGE ALL
    logic [NB-1:0][7:0] g_act, g_pre, g_rd, g_wr;
    logic [7:0]     g_act_any = 8'd255, g_rd_any = 8'd255, g_wr_any = 8'd255, g_ref = 8'd255;
    logic [3:0][7:0] g_hist;
    initial begin
        for (int b = 0; b < NB; b++) begin g_act[b] = 8'd255; g_pre[b] = 8'd255; g_rd[b] = 8'd255; g_wr[b] = 8'd255; end
        for (int k = 0; k < 4; k++) g_hist[k] = 8'd255;
    end

    wire cv     = cmd_v && !first;                      // step 0 is before the first clock edge: the DUT's registers have not been reset yet, so nothing at step 0 is read
    wire act_c  = cv && cmd_op == ACT;
    wire rd_c   = cv && cmd_op == RD;
    wire wr_c   = cv && cmd_op == WR;
    wire pre_c  = cv && cmd_op == PRE;
    wire prea_c = cv && cmd_op == PREA;
    wire ref_c  = cv && cmd_op == REF;

    always_ff @(posedge clk) begin
        for (int b = 0; b < NB; b++) begin
            g_act[b] <= inc(g_act[b]); g_pre[b] <= inc(g_pre[b]); g_rd[b] <= inc(g_rd[b]); g_wr[b] <= inc(g_wr[b]);
        end
        g_act_any <= inc(g_act_any); g_rd_any <= inc(g_rd_any); g_wr_any <= inc(g_wr_any); g_ref <= inc(g_ref);
        for (int k = 0; k < 4; k++) g_hist[k] <= inc(g_hist[k]);
        if (act_c) begin
            m_open[cmd_bank] <= 1'b1; g_act[cmd_bank] <= 8'd1; g_act_any <= 8'd1;
            g_hist[0] <= 8'd1; g_hist[1] <= inc(g_hist[0]); g_hist[2] <= inc(g_hist[1]); g_hist[3] <= inc(g_hist[2]);
        end
        if (rd_c) begin g_rd[cmd_bank] <= 8'd1; g_rd_any <= 8'd1; end
        if (wr_c) begin g_wr[cmd_bank] <= 8'd1; g_wr_any <= 8'd1; end
        if (pre_c) begin m_open[cmd_bank] <= 1'b0; g_pre[cmd_bank] <= 8'd1; m_pa[cmd_bank] <= 1'b0; end
        if (prea_c) begin m_open <= '0; m_pa <= '1; for (int b = 0; b < NB; b++) g_pre[b] <= 8'd1; end
        if (ref_c) g_ref <= 8'd1;
    end

    // ---------------------------------------------------------------- the timing rules, checked on the command bus
    //  SVA:  a_act_tRP:  assert property (@(posedge clk) cmd_v && cmd_op == ACT |-> g_pre[cmd_bank] >= (m_pa[cmd_bank] ? T_RPA : T_RP));   (and so on, one per rule)
    wire [BW-1:0] cb = cmd_bank;
    `FVR(r_act_closed,    !(act_c) || !m_open[cb])
    `FVR(r_act_trp,       !(act_c) || (g_pre[cb] >= 8'(m_pa[cb] ? T_RPA : T_RP)))
    `FVR(r_act_trc,       !(act_c) || (g_act[cb] >= 8'(T_RC)))
    `FVR(r_act_trrd,      !(act_c) || (g_act_any >= 8'(T_RRD)))
    `FVR(r_act_tfaw,      !(act_c) || (g_hist[3] >= 8'(T_FAW)))            // the fifth ACTIVATE, counting back four, is at least tFAW after the first of them
    `FVR(r_act_trfc,      !(act_c) || (g_ref >= 8'(T_RFC)))
    `FVR(r_col_open,      !(rd_c || wr_c) || m_open[cb])
    `FVR(r_col_trcd,      !(rd_c || wr_c) || (g_act[cb] >= 8'(T_RCD)))
    `FVR(r_col_trfc,      !(rd_c || wr_c) || (g_ref >= 8'(T_RFC)))
    `FVR(r_rd_ccd,        !(rd_c) || (g_rd_any >= 8'(BL2)))
    `FVR(r_rd_twtr,       !(rd_c) || (g_wr_any >= 8'(W2R)))
    `FVR(r_wr_ccd,        !(wr_c) || (g_wr_any >= 8'(BL2)))
    `FVR(r_wr_rtw,        !(wr_c) || (g_rd_any >= 8'(RTW)))
    `FVR(r_pre_open,      !(pre_c) || m_open[cb])
    `FVR(r_pre_tras,      !(pre_c) || (g_act[cb] >= 8'(T_RAS)))
    `FVR(r_pre_trtp,      !(pre_c) || (g_rd[cb] >= 8'(R2P)))
    `FVR(r_pre_twr,       !(pre_c) || (g_wr[cb] >= 8'(W2P)))
    generate for (genvar b = 0; b < NB; b++) begin : g_pa
        `FVR(r_prea_tras, !(prea_c && m_open[b]) || (g_act[b] >= 8'(T_RAS)))
        `FVR(r_prea_trtp, !(prea_c && m_open[b]) || (g_rd[b] >= 8'(R2P)))
        `FVR(r_prea_twr,  !(prea_c && m_open[b]) || (g_wr[b] >= 8'(W2P)))
        `FVR(r_ref_closed,!(ref_c) || !m_open[b])
        `FVR(r_ref_trp,   !(ref_c) || (g_pre[b] >= 8'(m_pa[b] ? T_RPA : T_RP)))
    end endgenerate
    `FVR(r_ref_trfc,      !(ref_c) || (g_ref >= 8'(T_RFC)))
    `FVR(r_any_trfc,      !(cv && cmd_op != REF) || (g_ref >= 8'(T_RFC)))
    `FVR(r_op_legal,      !(cv) || (cmd_op >= ACT && cmd_op <= REF))


    // ---------------------------------------------------------------- helper invariants (group I): each RTL down-counter c that enforces a rule of N clocks after an event is, at every clock, at least N - 1 - (age of the event as the bus shows it)
    //  The RTL decides in clock d and loads c with N - 1; the command is on the bus in clock d + 1 (the monitor's age of it is still the old one that clock, so the effective age there is 0), after which c counts down as the age counts up.
    //  Hence  age_eff >= N  or  c + age_eff + 1 >= N.  These say nothing about the rules themselves; they are the facts about the RTL's counters from which each rule follows in one step.
    function automatic logic inv_ok(input logic [7:0] c, input logic [7:0] age, input logic ev, input int n);
        logic [7:0] ae;
        ae = ev ? 8'd0 : age;
        return (ae >= 8'(n)) || (({1'b0, c} + {1'b0, ae} + 9'd1) >= 9'(n));
    endfunction
    generate for (genvar b = 0; b < NB; b++) begin : g_inv
        wire ev_act = act_c && cmd_bank == BW'(b);
        wire ev_rd  = rd_c  && cmd_bank == BW'(b);
        wire ev_wr  = wr_c  && cmd_bank == BW'(b);
        wire ev_pre = (pre_c && cmd_bank == BW'(b)) || prea_c;
        wire pa_eff = prea_c ? 1'b1 : ((pre_c && cmd_bank == BW'(b)) ? 1'b0 : m_pa[b]);
        `FVI(i_col_trcd, inv_ok(c_col[b], g_act[b], ev_act, T_RCD))
        `FVI(i_rc_trc,   inv_ok(c_rc[b],  g_act[b], ev_act, T_RC))
        `FVI(i_pre_tras, inv_ok(c_pre[b], g_act[b], ev_act, T_RAS))
        `FVI(i_pre_trtp, inv_ok(c_pre[b], g_rd[b],  ev_rd,  R2P))
        `FVI(i_pre_twr,  inv_ok(c_pre[b], g_wr[b],  ev_wr,  W2P))
        `FVI(i_rp_trp,   inv_ok(c_rp[b],  g_pre[b], ev_pre, pa_eff ? T_RPA : T_RP))
        wire open_after = prea_c ? 1'b0 : ((pre_c && cmd_bank == BW'(b)) ? 1'b0 : ((act_c && cmd_bank == BW'(b)) ? 1'b1 : m_open[b]));
        `FVI(i_open_state, open_q[b] == open_after)
    end endgenerate
    // tFAW: each of the last four ACTIVATEs still inside the window (effective age at most tFAW - 2) holds its own non-zero RTL timer, so the number of non-zero timers is at least their count
    wire [7:0] e0 = act_c ? 8'd0 : g_hist[0];
    wire [7:0] e1 = act_c ? g_hist[0] : g_hist[1];
    wire [7:0] e2 = act_c ? g_hist[1] : g_hist[2];
    wire [7:0] e3 = act_c ? g_hist[2] : g_hist[3];
    // for the i-th newest of those ACTIVATEs still inside the window, at least i + 1 timers hold a value not below its remaining life (T_FAW - 1 - effective age): the i-th newest has the i-th longest remaining life
    function automatic logic [2:0] faw_cnt(input logic [7:0] ae);
        logic [2:0] n;
        n = 3'd0;
        for (int k = 0; k < 4; k++) if (({1'b0, c_faw[k]} + {1'b0, ae} + 9'd1) >= 9'(T_FAW)) n = n + 3'd1;
        return n;
    endfunction
    `FVI(i_faw0, !(({1'b0, e0} + 9'd1) < 9'(T_FAW)) || faw_cnt(e0) >= 3'd1)
    `FVI(i_faw1, !(({1'b0, e1} + 9'd1) < 9'(T_FAW)) || faw_cnt(e1) >= 3'd2)
    `FVI(i_faw2, !(({1'b0, e2} + 9'd1) < 9'(T_FAW)) || faw_cnt(e2) >= 3'd3)
    `FVI(i_faw3, !(({1'b0, e3} + 9'd1) < 9'(T_FAW)) || faw_cnt(e3) >= 3'd4)
    `FVI(i_rrd,          inv_ok(c_rrd, g_act_any, act_c, T_RRD))
    `FVI(i_rd_ccd,       inv_ok(c_rd, g_rd_any, rd_c, BL2))
    `FVI(i_rd_twtr,      inv_ok(c_rd, g_wr_any, wr_c, W2R))
    `FVI(i_wr_ccd,       inv_ok(c_wr, g_wr_any, wr_c, BL2))
    `FVI(i_wr_rtw,       inv_ok(c_wr, g_rd_any, rd_c, RTW))
    `FVI(i_rfc,          inv_ok(c_rfc, g_ref, ref_c, T_RFC))
    `FVI(i_latched_debt, !ref_latched || (debt != 4'd0))                 // a refresh in progress has a refresh due: the debt only falls when the REFRESH command is issued, which also ends the refresh in progress
    `FVI(i_rfc_closed,   (c_rfc == 8'd0) || (open_q == '0))              // while the REFRESH timer runs every bank is closed (REFRESH needs them closed, ACTIVATE waits for the timer): so a column or PRECHARGE command cannot fall inside tRFC

    // ---------------------------------------------------------------- refresh: never starved, never spurious
    `FVD(l_debt_bound,    debt <= 4'(REF_POST + 2))                         // at most the postponement allowance plus the one falling due plus the one that fell due during the forced sequence
    `FVD(l_ref_has_debt,  !(d_v && !first && d_op == REF) || (debt != 4'd0))          // a REFRESH is issued only when one is due (no underflow of the debt)

    // ---------------------------------------------------------------- ordering: B never overtakes an older A to the same burst address when either is a write (tracked by slot, chosen freely by the solver)
    (* anyseq *) logic pickA;
    (* anyseq *) logic pickB;
    logic           haveA = 1'b0, haveB = 1'b0, wrA = 1'b0, usedA = 1'b0, usedB = 1'b0;   // one pair per run: any pair of requests can be the one the solver picks
    logic [IW-1:0]  slA = '0, slB = '0;
    logic [BW+RW+CB-1:0] adA = '0;
    wire enq = req_v && req_rdy && !first;
    wire [BW+RW+CB-1:0] adr_now = {a_bank, a_row, a_col};
    wire col_c = d_v && !first && (d_op == RD || d_op == WR);
    always_ff @(posedge clk) begin
        if (enq && !haveA && !usedA && pickA) begin haveA <= 1'b1; usedA <= 1'b1; slA <= free_i; wrA <= req_wr; adA <= adr_now; end
        else if (enq && haveA && !haveB && !usedB && pickB && adr_now == adA && (wrA || req_wr)) begin haveB <= 1'b1; usedB <= 1'b1; slB <= free_i; end
        if (col_c && haveA && d_slot == slA) haveA <= 1'b0;
        if (col_c && haveB && d_slot == slB) haveB <= 1'b0;
    end
    // helper invariants for the ordering proof: the tracked requests are in the queue, and B waits for A through the dependency vector (set at B's enqueue because A was in the queue, to the same address, with a write between them)
    `FVI(i_ord_used, (!haveA || usedA) && (!haveB || (usedA && usedB)))      // B is only ever tracked after A, and each is picked once
    `FVI(i_ord_a,  !haveA || (v[slA] && w[slA] == wrA && {q_bank[slA], q_row[slA], q_col[slA]} == adA))
    `FVI(i_ord_b,  !haveB || v[slB])
    `FVI(i_ord_ab, !(haveA && haveB) || (dep[slB][slA] && slA != slB))
    `FVO(o_no_overtake,   !(col_c && haveB && d_slot == slB) || !haveA)
    `FVC(cov_order_pending, haveA && haveB)

    // ---------------------------------------------------------------- bounded response: a tracked request is served (its READ or WRITE issued) within BOUND clocks of entering the queue
    (* anyseq *) logic pickT;
    logic           haveT = 1'b0, usedT = 1'b0;
    logic [IW-1:0]  slT = '0;
    logic [15:0]    ageT = '0;
    always_ff @(posedge clk) begin
        if (haveT) ageT <= ageT + 16'd1;
        if (enq && !haveT && !usedT && pickT) begin haveT <= 1'b1; usedT <= 1'b1; slT <= free_i; ageT <= 16'd0; end
        if (col_c && haveT && d_slot == slT) haveT <= 1'b0;
    end
    `FVI(i_ord_range, int'(slA) < QD && int'(slB) < QD && int'(slT) < QD)      // the tracked slot numbers are real slots (QD need not be a power of two)
    `FVB(l_bounded,       !haveT || (ageT <= 16'(BOUND)))

    // ---------------------------------------------------------------- covers: the proofs are not vacuous
    `FVC(cov_act, act_c)
    `FVC(cov_col, rd_c || wr_c)
    `FVC(cov_rd, rd_c)
    `FVC(cov_wr, wr_c)
    `FVC(cov_pre, pre_c)
    `FVC(cov_prea, prea_c)
    `FVC(cov_ref, ref_c)
    `FVC(cov_rd_after_wr, rd_c && g_wr_any < 8'(W2R + 3))
    `FVC(cov_wr_after_rd, wr_c && g_rd_any < 8'(RTW + 3))
    `FVC(cov_tracked_served, haveT && col_c && d_slot == slT)
    `FVC(cov_debt_any,  debt >= 4'd1)
    `FVC(cov_debt_pending,  debt >= 4'd2)
endmodule
