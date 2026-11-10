`timescale 1ns / 1ps
// tb_chk.sv: the checkers and the saturating record on one clock, driven directly by sim/chk_cocotb.py.
// rec_cnt is built with narrow fields (errors 4, events 4, lock-ups 3, relocks 3 bits) so saturation is quick.
module tb_chk (
    input  logic        clk,
    // rec_cnt
    input  logic        frz, sh, sin, e_err, e_ev, e_lock, e_relock,
    output logic        sout,
    // chk_words
    input  logic        w_valid, w_arm, w_hold,
    input  logic [15:0] w_w,
    output logic        w_err, w_ev, w_relock, w_lock,
    // chk_events
    input  logic        v_ev,
    input  logic [7:0]  v_ref,
    output logic        v_err, v_evo,
    // chk_count
    input  logic [11:0] c_v, c_raw,
    output logic        c_err, c_ev,
    // chk_coh
    input  logic [31:0] h_q,
    input  logic        h_rqs,
    output logic        h_err, h_ev
);
    rec_cnt #(.EW(4), .VW(4), .LW(3), .RW(3)) u_rec (.clk(clk), .frz(frz), .sh(sh), .sin(sin), .sout(sout),
        .e_err(e_err), .e_ev(e_ev), .e_lock(e_lock), .e_relock(e_relock));
    chk_words #(.WDB(6)) u_w (.clk(clk), .valid(w_valid), .w(w_w), .arm(w_arm), .hold(w_hold), .e_err(w_err),
        .e_ev(w_ev), .e_relock(w_relock), .e_lock(w_lock));
    chk_events #(.QUIET(8)) u_v (.clk(clk), .ev(v_ev), .ref_cnt(v_ref), .lvl_chk(1'b1), .e_err(v_err), .e_ev(v_evo));
    chk_count #(.MAXSTEP(2), .RAWCHK(1)) u_c (.clk(clk), .v(c_v), .raw(c_raw), .e_err(c_err), .e_ev(c_ev));
    chk_coh u_h (.clk(clk), .q(h_q), .rqs(h_rqs), .e_err(h_err), .e_ev(h_ev));
endmodule
