// itch_top.sv: brief 110's standard-protocol path (mold_rx -> itch_dec -> book_core -> risk_glue -> order frame) as brief 127 uses it inside the 10G core (simulation and build).
//
// The same blocks and wiring as itch_ouch_top.sv of brief 110 (they are instantiated unchanged from designs/b110_itch_ouch/rtl), with three differences:
//   1. the frame check verdict is a late strobe (`v_v`, `v_bad` from udp_strip), not `s_err` on the last word: mold_rx's s_err is tied low, and the flag `untrusted`
//      and the counter `pkt_err` are kept here instead. A candidate decoded in the few clocks before the verdict of its own frame is NOT blocked by it (110 specified
//      this case as undecided); the order it starts is poisoned downstream when the verdict is bad (itch_path),
//   2. the order builder is order_seg (a 113-byte Ethernet/IP/TCP frame around ouch_enter's packet, or tcp_fast's when #245 lands) and risk_glue's `busy` input is that
//      block's busy OR `tx_busy` (the transmit path still holds the last order),
//   3. the order side's `go`, `go_spec`, `commit`, `abort` and `late` are brought out (the poison logic and the latency stamps use them).
// Clock: the 10G core's user clock; resets synchronous. docs/itch_integration.md is the datasheet of the integration.
module itch_top
    import itch_pkg::*;
#(
    parameter int N_INST = 4,
    parameter int LEVELS = 8,
    parameter int ORD_AW = 8
) (
    input  logic                 clk,
    input  logic                 rst,
    // UDP payload stream from udp_strip
    input  logic                 s_v,
    input  logic [63:0]          s_d,
    input  logic                 s_sof,
    input  logic                 s_eof,
    input  logic [7:0]           s_keep,
    input  logic                 v_v,
    input  logic                 v_bad,
    // configuration (static while traffic runs)
    input  logic [N_INST*64-1:0] cfg_watch,
    input  logic [31:0]          cfg_thr, cfg_qty, cfg_max_qty, cfg_max_pos, cfg_band, cfg_px_off, cfg_minqty,
    input  logic [7:0]           cfg_tif, cfg_display, cfg_capacity, cfg_ise, cfg_cross, cfg_custtype,
    input  logic                 cfg_arm, cfg_kill, cfg_halt_on_gap, cfg_spec,
    input  logic [47:0]          tpl_my_mac, tpl_venue_mac,
    input  logic [31:0]          tpl_my_ip, tpl_venue_ip,
    input  logic [15:0]          tpl_sport, tpl_dport,
    input  logic [31:0]          tpl_seq0, tpl_ack,
    input  logic                 tpl_load,
    input  logic                 sw_we,
    input  logic [4:0]           sw_waddr,
    input  logic [31:0]          sw_wdata,
    input  logic [4:0]           sw_raddr,
    output logic [31:0]          sw_rdata,
    // clears (one clock)
    input  logic                 clr_cnt, clr_flags, clr_book, clr_pos, clr_ref,
    input  logic                 tx_busy,
    // order frame out
    output logic                 o_v,
    output logic [63:0]          o_d,
    output logic                 o_sof,
    output logic                 o_eof,
    output logic [7:0]           o_keep,
    output logic                 o_poison,
    output logic                 o_unres,
    // order side, for the poison logic and the stamps
    output logic                 go, go_spec, commit, abort, b_late,
    // observation
    output logic [15:0]          flags,
    output logic [NC*32-1:0]     cnt
);
    localparam int IW = $clog2(N_INST > 1 ? N_INST : 2);

    logic m_v; logic [383:0] m_w; logic [2:0] m_off; logic [15:0] m_len; logic [31:0] m_seq; logic pk_end;
    logic gap_flag, untrusted_m, eos_seen, sess_lock;
    logic [13*32-1:0] cnt_m;
    mold_rx u_mold (.clk, .rst, .clr_cnt, .clr_flags, .s_v, .s_d, .s_sof, .s_eof, .s_keep, .s_err(1'b0), .m_v, .m_w, .m_off, .m_len, .m_seq, .pk_end,
                    .gap_flag, .untrusted(untrusted_m), .eos_seen, .sess_lock, .cnt(cnt_m));
    // the late verdict: untrusted and pkt_err
    logic        untrusted;
    logic [31:0] c_err;
    always_ff @(posedge clk) begin
        if (rst) begin untrusted <= 1'b0; c_err <= '0; end
        else begin
            if (v_v && v_bad) begin untrusted <= 1'b1; c_err <= c_err + 32'd1; end
            if (clr_flags) untrusted <= 1'b0;
            if (clr_cnt) c_err <= '0;
        end
    end
    logic [13*32-1:0] cnt_m2;
    assign cnt_m2 = {c_err, cnt_m[12*32-1:0]};

    logic e_v; logic [2:0] e_k; logic [15:0] e_loc; logic [63:0] e_ref, e_nref, e_stock; logic e_sell; logic [31:0] e_sh, e_px, e_seq; logic [7:0] e_code;
    logic [11*32-1:0] cnt_d;
    itch_dec u_dec (.clk, .rst, .clr_cnt, .m_v, .m_w, .m_off, .m_len, .m_seq, .e_v, .e_k, .e_loc, .e_ref, .e_nref, .e_sell, .e_sh, .e_px, .e_stock, .e_code,
                    .e_seq, .cnt(cnt_d));
    logic spec_allow, spec_start, spec_fail, tu_v, tu_side, tu_ok, tu_cand, tu_spec, tu_gapblk, tu_inx, book_ready, gapblk_now;
    logic [IW-1:0] spec_inst, tu_inst; logic [31:0] spec_px, tu_cpx, tu_px, tu_sz; logic [N_INST-1:0] inexact;
    logic [N_INST*2*32-1:0] tob_px, tob_sz; logic [N_INST*2-1:0] tob_ok; logic [7:0] sys_code;
    logic [8*32-1:0] cnt_b;
    assign gapblk_now = untrusted || untrusted_m || (cfg_halt_on_gap && gap_flag);
    book_core #(.N_INST(N_INST), .LEVELS(LEVELS), .ORD_AW(ORD_AW)) u_book (
        .clk, .rst, .clr_book, .clr_cnt, .cfg_watch, .cfg_thr, .spec_allow, .gapblk_now,
        .e_v, .e_k, .e_loc, .e_ref, .e_nref, .e_sell, .e_sh, .e_px, .e_stock, .e_code,
        .spec_start, .spec_inst, .spec_px, .spec_fail,
        .tu_v, .tu_inst, .tu_side, .tu_px, .tu_sz, .tu_ok, .tu_cpx, .tu_cand, .tu_spec, .tu_gapblk, .tu_inx,
        .tob_px, .tob_sz, .tob_ok, .inexact, .book_ready, .sys_code, .cnt(cnt_b));
    logic b_busy, seg_busy, spec_pend;
    logic [63:0] f_sym; logic [31:0] f_px, f_qty, f_ref;
    logic [13*32-1:0] cnt_r;
    assign b_busy = seg_busy || tx_busy;
    risk_glue #(.N_INST(N_INST)) u_risk (
        .clk, .rst, .clr_cnt, .clr_pos, .clr_ref, .cfg_watch, .cfg_arm, .cfg_kill, .cfg_spec, .cfg_qty, .cfg_max_qty, .cfg_max_pos, .cfg_band, .cfg_px_off,
        .spec_start, .spec_inst, .spec_px, .spec_fail, .tu_v, .tu_inst, .tu_cpx, .tu_cand, .tu_spec, .tu_gapblk, .tu_inx, .tob_px, .tob_ok, .book_ready,
        .spec_allow, .go, .go_spec, .f_sym, .f_px, .f_qty, .f_ref, .commit, .abort, .b_busy, .b_late, .cnt(cnt_r));
    order_seg u_seg (.clk, .rst, .go, .go_spec, .f_sym, .f_px, .f_qty, .f_ref, .commit, .abort, .cfg_tif, .cfg_display, .cfg_capacity, .cfg_ise, .cfg_cross,
                     .cfg_custtype, .cfg_minqty, .tpl_my_mac, .tpl_venue_mac, .tpl_my_ip, .tpl_venue_ip, .tpl_sport, .tpl_dport, .tpl_seq0, .tpl_ack, .tpl_load,
                     .sw_we, .sw_waddr, .sw_wdata, .sw_raddr, .sw_rdata, .busy(seg_busy), .late(b_late), .spec_pend,
                     .o_v, .o_d, .o_sof, .o_eof, .o_keep, .o_poison, .o_unres);

    assign cnt = {cnt_r, cnt_b, cnt_d, cnt_m2};
    always_comb begin
        flags = '0;
        flags[0] = gap_flag; flags[1] = untrusted || untrusted_m; flags[2] = eos_seen; flags[3] = sess_lock; flags[4] = book_ready; flags[5] = b_busy;
        for (int i = 0; i < N_INST; i++) flags[8 + i] = inexact[i];
    end
    logic unused;
    assign unused = &{1'b0, pk_end, e_seq, m_seq, spec_pend, tu_side, tu_ok, tu_px, tu_sz, tob_sz, sys_code};
endmodule
