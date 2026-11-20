// itch_ouch_top.sv: standard-protocol trading path, phase 1 (brief 110).
//
// UDP payload words in (MoldUDP64 carrying Nasdaq TotalView-ITCH 5.0) -> mold_rx -> itch_dec -> book_core -> risk_glue -> ouch_enter ->
// OUCH 5.0 Enter Order frames (SoupBinTCP 3.00 Unsequenced Data) out on a stub port. No Ethernet, IP, UDP or TCP here (docs/phase2_integration.md).
// One clock (the 10G core's user clock, 161.1328125 MHz, 6.2061 ns); resets are synchronous. All configuration inputs are static while traffic runs.
// docs/itch_ouch.md is the datasheet: interfaces, parameters, behaviour a user could guess wrong, latencies.
module itch_ouch_top #(
    parameter int N_INST = 4,          // instruments watched (1 to 8)
    parameter int LEVELS = 8,          // price levels per side and instrument (4 or 8)
    parameter int ORD_AW = 8           // order table index bits: 2^ORD_AW live orders
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
    // configuration
    input  logic [N_INST*64-1:0] cfg_watch,
    input  logic [31:0]          cfg_thr, cfg_qty, cfg_max_qty, cfg_max_pos, cfg_band, cfg_px_off, cfg_minqty,
    input  logic [7:0]           cfg_tif, cfg_display, cfg_capacity, cfg_ise, cfg_cross, cfg_custtype,
    input  logic                 cfg_arm, cfg_kill, cfg_halt_on_gap, cfg_spec,
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
    output logic [45*32-1:0]     cnt                  // counter k = cnt[32*k +: 32], indices in itch_pkg
);
    import itch_pkg::*;
    localparam int IW = $clog2(N_INST > 1 ? N_INST : 2);

    // mold
    logic [383:0] m_w; logic [2:0] m_off; logic [31:0] m_seq; logic pk_end;
    logic gap_flag, untrusted, eos_seen, sess_lock;
    logic [13*32-1:0] cnt_m;
    mold_rx u_mold (.clk, .rst, .clr_cnt, .clr_flags, .s_v, .s_d, .s_sof, .s_eof, .s_keep, .s_err, .m_v, .m_w, .m_off, .m_len, .m_seq, .pk_end,
                    .gap_flag, .untrusted, .eos_seen, .sess_lock, .cnt(cnt_m));
    // decode
    logic [15:0] e_loc; logic [63:0] e_ref, e_nref, e_stock; logic e_sell; logic [31:0] e_sh, e_px, e_seq; logic [7:0] e_code;
    logic [11*32-1:0] cnt_d;
    itch_dec u_dec (.clk, .rst, .clr_cnt, .m_v, .m_w, .m_off, .m_len, .m_seq, .e_v, .e_k, .e_loc, .e_ref, .e_nref, .e_sell, .e_sh, .e_px, .e_stock, .e_code,
                    .e_seq, .cnt(cnt_d));
    // book
    logic spec_allow, spec_start, spec_fail, tu_cand, tu_spec, tu_gapblk, tu_inx, book_ready, gapblk_now;
    logic [IW-1:0] spec_inst; logic [31:0] spec_px, tu_cpx; logic [N_INST-1:0] inexact;
    logic [8*32-1:0] cnt_b;
    assign gapblk_now = untrusted || (cfg_halt_on_gap && gap_flag);
    book_core #(.N_INST(N_INST), .LEVELS(LEVELS), .ORD_AW(ORD_AW)) u_book (
        .clk, .rst, .clr_book, .clr_cnt, .cfg_watch, .cfg_thr, .spec_allow, .gapblk_now,
        .e_v, .e_k, .e_loc, .e_ref, .e_nref, .e_sell, .e_sh, .e_px, .e_stock, .e_code,
        .spec_start, .spec_inst, .spec_px, .spec_fail,
        .tu_v, .tu_inst, .tu_side, .tu_px, .tu_sz, .tu_ok, .tu_cpx, .tu_cand, .tu_spec, .tu_gapblk, .tu_inx,
        .tob_px, .tob_sz, .tob_ok, .inexact, .book_ready, .sys_code, .cnt(cnt_b));
    // decision and order
    logic go, go_spec, commit, abort, b_busy, b_late, spec_pend;
    logic [63:0] f_sym; logic [31:0] f_px, f_qty, f_ref;
    logic [13*32-1:0] cnt_r;
    risk_glue #(.N_INST(N_INST)) u_risk (
        .clk, .rst, .clr_cnt, .clr_pos, .clr_ref, .cfg_watch, .cfg_arm, .cfg_kill, .cfg_spec, .cfg_qty, .cfg_max_qty, .cfg_max_pos, .cfg_band, .cfg_px_off,
        .spec_start, .spec_inst, .spec_px, .spec_fail, .tu_v, .tu_inst, .tu_cpx, .tu_cand, .tu_spec, .tu_gapblk, .tu_inx, .tob_px, .tob_ok, .book_ready,
        .spec_allow, .go, .go_spec, .f_sym, .f_px, .f_qty, .f_ref, .commit, .abort, .b_busy, .b_late, .cnt(cnt_r));
    ouch_enter u_ouch (.clk, .rst, .go, .go_spec, .f_sym, .f_px, .f_qty, .f_ref, .commit, .abort, .cfg_tif, .cfg_display, .cfg_capacity, .cfg_ise, .cfg_cross,
                       .cfg_custtype, .cfg_minqty, .busy(b_busy), .late(b_late), .spec_pend, .o_v, .o_d, .o_sof, .o_eof, .o_keep, .o_abort);

    assign cnt = {cnt_r, cnt_b, cnt_d, cnt_m};
    always_comb begin
        flags = '0;
        flags[0] = gap_flag; flags[1] = untrusted; flags[2] = eos_seen; flags[3] = sess_lock; flags[4] = book_ready; flags[5] = b_busy;
        for (int i = 0; i < N_INST; i++) flags[8 + i] = inexact[i];
    end
    logic unused;
    assign unused = &{1'b0, pk_end, e_seq, m_seq, spec_pend};
endmodule
