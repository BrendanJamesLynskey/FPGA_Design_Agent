// itch_ouch_top.sv: standard-protocol trading path, phase 1 (brief 110).
//
// UDP payload words in (MoldUDP64 carrying Nasdaq TotalView-ITCH 5.0) -> mold_rx -> itch_dec -> book_core -> risk_glue -> ouch_enter ->
// OUCH 5.0 Enter Order frames (SoupBinTCP 3.00 Unsequenced Data) out on a stub port. No Ethernet, IP, UDP or TCP here (docs/phase2_integration.md).
// One clock (the 10G core's user clock, 161.1328125 MHz, 6.2061 ns); resets are synchronous. All configuration inputs are static while traffic runs.
// docs/itch_ouch.md is the datasheet: interfaces, parameters, behaviour a user could guess wrong, latencies.
module itch_ouch_top
    import itch_pkg::*;
#(
    parameter int N_INST = 4,          // instruments watched (2 to 8)
    parameter int LEVELS = 8,          // price levels per side and instrument (4 or 8)
    parameter int ORD_AW = 8,          // order table index bits: 2^ORD_AW live orders
    parameter int NOTIONAL_MODE = 0,   // pre-trade notional check (brief 188): 0 none, 1 price times quantity, 2 price-band table written by software
    parameter int PARSE_INPLACE = 0,   // brief 191: 0 shift the message to byte 0 then decode, 1 decode it where it lies (eight fixed-lane decoders)
    parameter int ARB_AW = 5,          // brief 191: feed_arb's FIFO depth per feed, 2^ARB_AW words (it must hold the skew between the feeds when one is a packet ahead)
    parameter int DUAL_FEED = 0        // brief 191: 1 = a second payload stream (sb_*, the B feed) is arbitrated with the first (the A feed) by feed_arb before mold_rx
) (
    input  logic                 clk,
    input  logic                 rst,
    // UDP payload stream
    input  logic                 s_v,
    input  logic [63:0]          s_d,
    input  logic                 s_sof,
    input  logic                 s_eof,
    input  logic [7:0]           s_keep,
    input  logic                 s_err,
    // B feed (used only with DUAL_FEED 1; tie to 0 otherwise)
    input  logic                 sb_v,
    input  logic [63:0]          sb_d,
    input  logic                 sb_sof,
    input  logic                 sb_eof,
    input  logic [7:0]           sb_keep,
    input  logic                 sb_err,
    // configuration
    input  logic [N_INST*64-1:0] cfg_watch,
    input  logic [31:0]          cfg_thr, cfg_qty, cfg_max_qty, cfg_max_pos, cfg_band, cfg_px_off, cfg_minqty,
    input  logic [7:0]           cfg_tif, cfg_display, cfg_capacity, cfg_ise, cfg_cross, cfg_custtype,
    input  logic                 cfg_arm, cfg_kill, cfg_halt_on_gap, cfg_spec,
    input  logic [15:0]          cfg_holdoff,                   // brief 188: clocks an instrument is refused after an accepted order (0 = off)
    input  logic                 cfg_ref_sw,                    // brief 188: band reference 0 = own best bid, 1 = the software reference
    input  logic [31:0]          cfg_ref_px, cfg_ref_age,       // the software reference, and its largest age in clocks
    input  logic                 ref_load,                      // one clock: cfg_ref_px was written (the age restarts)
    input  logic [63:0]          cfg_max_notional,              // NOTIONAL_MODE 1
    input  logic [4:0]           cfg_nt_shift,                  // NOTIONAL_MODE 2
    input  logic [16*32-1:0]     cfg_nt_tbl,
    // clears (one clock)
    input  logic                 clr_cnt, clr_flags, clr_book, clr_pos, clr_ref,
    // order frame out (stub port)
    output logic                 o_v,
    output logic [63:0]          o_d,
    output logic                 o_sof,
    output logic                 o_eof,
    output logic [7:0]           o_keep,
    output logic                 o_abort,
    // observation
    output logic                 m_v,                 // MoldUDP64 message delivered (raw)
    output logic [15:0]          m_len,
    output logic                 e_v,                 // decoded ITCH event
    output logic [2:0]           e_k,
    output logic                 tu_v,                // top-of-book update record
    output logic [$clog2(N_INST > 1 ? N_INST : 2)-1:0] tu_inst,
    output logic                 tu_side,
    output logic [31:0]          tu_px, tu_sz,
    output logic                 tu_ok,
    output logic [N_INST*2*32-1:0] tob_px, tob_sz,
    output logic [N_INST*2-1:0]  tob_ok,
    output logic [15:0]          flags,               // 0 gap, 1 untrusted, 2 end of session, 3 session locked, 4 book ready, 5 frame busy, 8.. inexact per instrument
    output logic [7:0]           sys_code,
    output logic                 vd_v,                // brief 191: a candidate's verdict was formed in the previous clock
    output logic                 vd_pass,
    output logic [7:0]           vd_rej,              // the checks that failed (0 arm, 1 kill, 2 gap, 3 stale, 4 size, 5 position, 6 band, 7 hold-off), all of them
    output logic [7:0]           rej_seen,            // sticky OR of vd_rej since reset or clr_cnt
    output logic [7*32-1:0]      cnt_ab,              // feed_arb counters (DUAL_FEED 1; 0 otherwise): fwd_a fwd_b old_a old_b gap sess ovf
    output logic [NC*32-1:0]     cnt                  // counter k = cnt[32*k +: 32], indices in itch_pkg
);
    localparam int IW = $clog2(N_INST > 1 ? N_INST : 2);

    // mold
    logic [383:0] m_w; logic [2:0] m_off; logic [31:0] m_seq; logic pk_end;
    logic gap_flag, untrusted, eos_seen, sess_lock;
    logic [13*32-1:0] cnt_m;
    logic r_v, r_sof, r_eof, r_err; logic [63:0] r_d; logic [7:0] r_keep;          // the stream the parser sees
    if (DUAL_FEED != 0) begin : g_arb
        feed_arb #(.AW(ARB_AW)) u_arb (.clk, .rst, .clr_cnt, .a_v(s_v), .a_sof(s_sof), .a_eof(s_eof), .a_err(s_err), .a_d(s_d), .a_keep(s_keep),
                        .b_v(sb_v), .b_sof(sb_sof), .b_eof(sb_eof), .b_err(sb_err), .b_d(sb_d), .b_keep(sb_keep),
                        .o_v(r_v), .o_sof(r_sof), .o_eof(r_eof), .o_err(r_err), .o_d(r_d), .o_keep(r_keep), .cnt(cnt_ab));
    end else begin : g_direct
        assign r_v = s_v; assign r_sof = s_sof; assign r_eof = s_eof; assign r_err = s_err; assign r_d = s_d; assign r_keep = s_keep;
        assign cnt_ab = '0;
    end
    mold_rx u_mold (.clk, .rst, .clr_cnt, .clr_flags, .s_v(r_v), .s_d(r_d), .s_sof(r_sof), .s_eof(r_eof), .s_keep(r_keep), .s_err(r_err), .m_v, .m_w, .m_off, .m_len, .m_seq, .pk_end,
                    .gap_flag, .untrusted, .eos_seen, .sess_lock, .cnt(cnt_m));
    // decode
    logic [15:0] e_loc; logic [63:0] e_ref, e_nref, e_stock; logic e_sell; logic [31:0] e_sh, e_px, e_seq; logic [7:0] e_code;
    logic [11*32-1:0] cnt_d;
    itch_dec #(.PARSE_INPLACE(PARSE_INPLACE)) u_dec (.clk, .rst, .clr_cnt, .m_v, .m_w, .m_off, .m_len, .m_seq, .e_v, .e_k, .e_loc, .e_ref, .e_nref, .e_sell, .e_sh, .e_px, .e_stock, .e_code,
                    .e_seq, .cnt(cnt_d));
    // book
    logic [31:0] nt_px;                       // brief 188: early copy of the ladder-update price, book_core to risk_glue
    logic spec_allow, spec_start, spec_fail, tu_cand, tu_spec, tu_gapblk, tu_inx, book_ready, gapblk_now;
    logic [IW-1:0] spec_inst; logic [31:0] spec_px, tu_cpx; logic [N_INST-1:0] inexact;
    logic [8*32-1:0] cnt_b;
    assign gapblk_now = untrusted || (cfg_halt_on_gap && gap_flag);
    book_core #(.N_INST(N_INST), .LEVELS(LEVELS), .ORD_AW(ORD_AW)) u_book (
        .clk, .rst, .clr_book, .clr_cnt, .cfg_watch, .cfg_thr, .spec_allow, .gapblk_now,
        .e_v, .e_k, .e_loc, .e_ref, .e_nref, .e_sell, .e_sh, .e_px, .e_stock, .e_code,
        .spec_start, .spec_inst, .spec_px, .spec_fail,
        .tu_v, .tu_inst, .tu_side, .tu_px, .tu_sz, .tu_ok, .tu_cpx, .tu_cand, .tu_spec, .tu_gapblk, .tu_inx, .nt_px,
        .tob_px, .tob_sz, .tob_ok, .inexact, .book_ready, .sys_code, .cnt(cnt_b));
    // decision and order
    logic go, go_spec, commit, abort, b_busy, b_late, spec_pend;
    logic [63:0] f_sym; logic [31:0] f_px, f_qty, f_ref;
    logic [13*32-1:0] cnt_r;
    risk_glue #(.N_INST(N_INST), .NOTIONAL_MODE(NOTIONAL_MODE)) u_risk (
        .clk, .rst, .clr_cnt, .clr_pos, .clr_ref, .cfg_watch, .cfg_arm, .cfg_kill, .cfg_spec, .cfg_qty, .cfg_max_qty, .cfg_max_pos, .cfg_band, .cfg_px_off,
        .cfg_holdoff, .cfg_ref_sw, .cfg_ref_px, .cfg_ref_age, .ref_load, .cfg_max_notional, .cfg_nt_shift, .cfg_nt_tbl,
        .spec_start, .spec_inst, .spec_px, .spec_fail, .tu_v, .tu_inst, .tu_cpx, .tu_cand, .tu_spec, .tu_gapblk, .tu_inx, .nt_px, .tob_px, .tob_ok, .book_ready,
        .spec_allow, .go, .go_spec, .f_sym, .f_px, .f_qty, .f_ref, .commit, .abort, .b_busy, .b_late, .vd_v, .vd_pass, .vd_rej, .rej_seen, .cnt(cnt_r));
    ouch_enter u_ouch (.clk, .rst, .go, .go_spec, .f_sym, .f_px, .f_qty, .f_ref, .commit, .abort, .cfg_tif, .cfg_display, .cfg_capacity, .cfg_ise, .cfg_cross,
                       .cfg_custtype, .cfg_minqty, .busy(b_busy), .late(b_late), .spec_pend, .o_v, .o_d, .o_sof, .o_eof, .o_keep, .o_abort);

    assign cnt = {cnt_r, cnt_b, cnt_d, cnt_m};
    always_comb begin
        flags = '0;
        flags[0] = gap_flag; flags[1] = untrusted; flags[2] = eos_seen; flags[3] = sess_lock; flags[4] = book_ready; flags[5] = b_busy;
        for (int i = 0; i < N_INST; i++) flags[8 + i] = inexact[i];
    end
    logic unused;
    assign unused = &{1'b0, pk_end, e_seq, m_seq, spec_pend, (DUAL_FEED != 0) ? 1'b0 : (sb_v ^ sb_sof ^ sb_eof ^ sb_err ^ (^sb_d) ^ (^sb_keep))};
endmodule
