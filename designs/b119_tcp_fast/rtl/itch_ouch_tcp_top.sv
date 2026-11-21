// itch_ouch_tcp_top.sv: brief 110's trading path with the TCP fast path in place of its stub port (brief 119, simulation only).
//
// The same blocks and wiring as itch_ouch_top of brief 110 (mold_rx, itch_dec, book_core, risk_glue), with `ouch_enter` replaced by `tcp_fast`, which
// has the same order-side ports and busy output and drives a complete Ethernet frame (113 bytes, no FCS) instead of the 59-byte packet. Observation
// outputs that brief 119 does not use (message, event, top-of-book records) are left out. The counter bus is the one of brief 110.
// Used by tests/b119_top_cocotb.py to show tcp_fast works behind the real risk logic: speculative start, abort, the order queue's view of `busy`.
module itch_ouch_tcp_top
    import itch_pkg::*;
#(
    parameter int N_INST = 4,
    parameter int LEVELS = 8,
    parameter int ORD_AW = 8
) (
    input  logic                 clk,
    input  logic                 rst,
    input  logic                 s_v,
    input  logic [63:0]          s_d,
    input  logic                 s_sof,
    input  logic                 s_eof,
    input  logic [7:0]           s_keep,
    input  logic                 s_err,
    input  logic [N_INST*64-1:0] cfg_watch,
    input  logic [31:0]          cfg_thr, cfg_qty, cfg_max_qty, cfg_max_pos, cfg_band, cfg_px_off, cfg_minqty,
    input  logic [7:0]           cfg_tif, cfg_display, cfg_capacity, cfg_ise, cfg_cross, cfg_custtype,
    input  logic                 cfg_arm, cfg_kill, cfg_halt_on_gap, cfg_spec,
    input  logic                 clr_cnt, clr_flags, clr_book, clr_pos, clr_ref,
    // segment out (to the MAC)
    output logic                 o_v,
    output logic [63:0]          o_d,
    output logic                 o_sof,
    output logic                 o_eof,
    output logic [7:0]           o_keep,
    output logic                 o_poison,
    output logic                 refuse_v,
    output logic [2:0]           refuse_code,
    output logic                 rec_v,
    output logic [31:0]          rec_seq,
    // software bus of the fast path
    input  logic                 sw_we,
    input  logic [4:0]           sw_waddr,
    input  logic [31:0]          sw_wdata,
    input  logic [4:0]           sw_raddr,
    output logic [31:0]          sw_rdata,
    // observation
    output logic [15:0]          flags,
    output logic [NC*32-1:0]     cnt
);
    localparam int IW = $clog2(N_INST > 1 ? N_INST : 2);

    logic m_v; logic [383:0] m_w; logic [2:0] m_off; logic [15:0] m_len; logic [31:0] m_seq; logic pk_end;
    logic gap_flag, untrusted, eos_seen, sess_lock;
    logic [13*32-1:0] cnt_m;
    mold_rx u_mold (.clk, .rst, .clr_cnt, .clr_flags, .s_v, .s_d, .s_sof, .s_eof, .s_keep, .s_err, .m_v, .m_w, .m_off, .m_len, .m_seq, .pk_end,
                    .gap_flag, .untrusted, .eos_seen, .sess_lock, .cnt(cnt_m));
    logic e_v; logic [2:0] e_k; logic [15:0] e_loc; logic [63:0] e_ref, e_nref, e_stock; logic e_sell; logic [31:0] e_sh, e_px, e_seq; logic [7:0] e_code;
    logic [11*32-1:0] cnt_d;
    itch_dec u_dec (.clk, .rst, .clr_cnt, .m_v, .m_w, .m_off, .m_len, .m_seq, .e_v, .e_k, .e_loc, .e_ref, .e_nref, .e_sell, .e_sh, .e_px, .e_stock, .e_code,
                    .e_seq, .cnt(cnt_d));
    logic spec_allow, spec_start, spec_fail, tu_v, tu_side, tu_ok, tu_cand, tu_spec, tu_gapblk, tu_inx, book_ready, gapblk_now;
    logic [IW-1:0] spec_inst, tu_inst; logic [31:0] spec_px, tu_cpx, tu_px, tu_sz; logic [N_INST-1:0] inexact;
    logic [N_INST*2*32-1:0] tob_px, tob_sz; logic [N_INST*2-1:0] tob_ok; logic [7:0] sys_code;
    logic [8*32-1:0] cnt_b;
    assign gapblk_now = untrusted || (cfg_halt_on_gap && gap_flag);
    book_core #(.N_INST(N_INST), .LEVELS(LEVELS), .ORD_AW(ORD_AW)) u_book (
        .clk, .rst, .clr_book, .clr_cnt, .cfg_watch, .cfg_thr, .spec_allow, .gapblk_now,
        .e_v, .e_k, .e_loc, .e_ref, .e_nref, .e_sell, .e_sh, .e_px, .e_stock, .e_code,
        .spec_start, .spec_inst, .spec_px, .spec_fail,
        .tu_v, .tu_inst, .tu_side, .tu_px, .tu_sz, .tu_ok, .tu_cpx, .tu_cand, .tu_spec, .tu_gapblk, .tu_inx,
        .tob_px, .tob_sz, .tob_ok, .inexact, .book_ready, .sys_code, .cnt(cnt_b));
    logic go, go_spec, commit, abort, b_busy, b_late;
    logic [63:0] f_sym; logic [31:0] f_px, f_qty, f_ref;
    logic [13*32-1:0] cnt_r;
    risk_glue #(.N_INST(N_INST)) u_risk (
        .clk, .rst, .clr_cnt, .clr_pos, .clr_ref, .cfg_watch, .cfg_arm, .cfg_kill, .cfg_spec, .cfg_qty, .cfg_max_qty, .cfg_max_pos, .cfg_band, .cfg_px_off,
        .spec_start, .spec_inst, .spec_px, .spec_fail, .tu_v, .tu_inst, .tu_cpx, .tu_cand, .tu_spec, .tu_gapblk, .tu_inx, .tob_px, .tob_ok, .book_ready,
        .spec_allow, .go, .go_spec, .f_sym, .f_px, .f_qty, .f_ref, .commit, .abort, .b_busy, .b_late, .cnt(cnt_r));
    logic [15:0] rec_len, rec_id;
    logic [511:0] rec_pay;
    tcp_fast u_tcp (.clk, .rst, .go, .go_spec, .f_sym, .f_px, .f_qty, .f_ref, .commit, .abort, .cfg_tif, .cfg_display, .cfg_capacity, .cfg_ise, .cfg_cross,
                    .cfg_custtype, .cfg_minqty, .busy(b_busy), .late(b_late), .refuse_v, .refuse_code, .o_v, .o_d, .o_sof, .o_eof, .o_keep, .o_poison,
                    .rec_v, .rec_seq, .rec_len, .rec_id, .rec_pay, .sw_we, .sw_waddr, .sw_wdata, .sw_raddr, .sw_rdata);

    assign cnt = {cnt_r, cnt_b, cnt_d, cnt_m};
    always_comb begin
        flags = '0;
        flags[0] = gap_flag; flags[1] = untrusted; flags[2] = eos_seen; flags[3] = sess_lock; flags[4] = book_ready; flags[5] = b_busy;
        for (int i = 0; i < N_INST; i++) flags[8 + i] = inexact[i];
    end
    logic unused;
    assign unused = &{1'b0, pk_end, e_seq, rec_len, rec_id, rec_pay, tu_side, tu_ok, tu_px, tu_sz, tob_sz};
endmodule
