`timescale 1ns/1ps
// pcs_mac_sva.sv: SystemVerilog assertions on the interfaces of the b96 PCS and MAC, bound into the RTL modules with `bind` (the RTL is not edited)
// (brief 112). A failure is reported as a UVM_ERROR (so the test fails); cover properties count their hits and print them at the end of the run
// ("SVA_COV <instance> <name> <hits>"), which the regression script collects. xsim 2026.1 does not run the action statement of a cover property
// (hits stay 0), so a cover is written as `assert property (not (sequence)) else count++`, which fires exactly when the sequence matches. Properties are on the interface of each module: the pause rhythm of
// pcs_tx, the source protocol and the frame strobes of mac64_tx, the lock/event contract of pcs_rx, the word and verdict strobes of mac64_rx.

`define SVA_ERR(MSG) uvm_pkg::uvm_report_error("SVA", $sformatf("%m: %s", MSG), uvm_pkg::UVM_NONE, `__FILE__, `__LINE__)

module pcs_tx_sva (input logic clk, rst, adv);
  int unsigned c_pause = 0, c_full_rhythm = 0;
  // a pause lasts one clock, and exactly 32 clocks without one follow it: one clock in 33
  a_single: assert property (@(posedge clk) disable iff (rst) !adv |=> adv) else `SVA_ERR("adv low for two clocks in a row");
  a_rhythm: assert property (@(posedge clk) disable iff (rst) !adv |=> (adv [*32] ##1 !adv)) else `SVA_ERR("the pause is not one clock in 33");
  c_p: assert property (@(posedge clk) disable iff (rst) not (!adv)) else c_pause++;
  c_r: assert property (@(posedge clk) disable iff (rst) not (!adv ##1 adv [*32] ##1 !adv)) else c_full_rhythm++;
  final $display("SVA_COV %m pause %0d", c_pause);
  final $display("SVA_COV %m full_33_clock_period %0d", c_full_rhythm);
endmodule

module mac64_tx_sva (input logic clk, rst, adv, s_valid, s_ready, s_last, input logic [63:0] s_data, input logic [2:0] s_nb1,
                     input logic sop, eop, underrun, input logic [63:0] x_d, input logic [7:0] x_c);
  int unsigned c_sop = 0, c_eop = 0, c_wait = 0;
  a_ready_adv: assert property (@(posedge clk) disable iff (rst) s_ready |-> adv) else `SVA_ERR("s_ready high while the PCS pauses");
  // the source offers a word and keeps it stable until s_ready (the MAC's stated contract, held by the UVM driver)
  a_stable: assert property (@(posedge clk) disable iff (rst) (s_valid && !s_ready) |=> (s_valid && $stable(s_data) && $stable(s_last) && $stable(s_nb1)))
    else `SVA_ERR("source word changed or dropped before s_ready");
  a_no_underrun: assert property (@(posedge clk) disable iff (rst) !underrun) else `SVA_ERR("underrun");
  a_sop: assert property (@(posedge clk) disable iff (rst) sop |-> (x_d[7:0] == 8'hFB && x_c == 8'h01)) else `SVA_ERR("sop without a start character in lane 0");
  a_eop: assert property (@(posedge clk) disable iff (rst) eop |-> (x_c != 8'h00 && x_c[7])) else `SVA_ERR("eop without a terminate word");
  a_sop_pulse: assert property (@(posedge clk) disable iff (rst) sop |=> !sop) else `SVA_ERR("sop held for two clocks");
  c_s: assert property (@(posedge clk) disable iff (rst) not (sop)) else c_sop++;
  c_e: assert property (@(posedge clk) disable iff (rst) not (eop)) else c_eop++;
  c_w: assert property (@(posedge clk) disable iff (rst) not (s_valid && !s_ready)) else c_wait++;
  final $display("SVA_COV %m sop %0d", c_sop);
  final $display("SVA_COV %m eop %0d", c_eop);
  final $display("SVA_COV %m source_waiting %0d", c_wait);
endmodule

module pcs_rx_sva (input logic clk, rst, lock, x_v, ev_lock, ev_loss, ev_slip, ev_sh_err, ev_type_err, ev_os);
  int unsigned c_lock = 0, c_loss = 0, c_slip = 0, c_sh = 0, c_type = 0, c_os = 0;
  // x_v is the lock as it stood when the block was taken, one clock before
  a_xv_lock: assert property (@(posedge clk) disable iff (rst) x_v |-> $past(lock)) else `SVA_ERR("x_v without lock one clock earlier");
  a_ev_lock: assert property (@(posedge clk) disable iff (rst) ev_lock |-> lock) else `SVA_ERR("ev_lock while not locked");
  a_ev_loss: assert property (@(posedge clk) disable iff (rst) ev_loss |-> (!lock && ev_slip)) else `SVA_ERR("ev_loss while locked, or without a slip");
  a_ev_slip: assert property (@(posedge clk) disable iff (rst) ev_slip |-> !lock) else `SVA_ERR("slip while locked");
  a_rise: assert property (@(posedge clk) disable iff (rst) $rose(lock) |-> ev_lock) else `SVA_ERR("lock rose without ev_lock");
  // the lock also falls when the receiver is reset (the clock after a reset edge, rst already released): no ev_loss then
  a_fall: assert property (@(posedge clk) disable iff (rst) $fell(lock) |-> (ev_loss || $past(rst))) else `SVA_ERR("lock fell without ev_loss and without a reset");
  a_excl: assert property (@(posedge clk) disable iff (rst) !(ev_lock && ev_loss)) else `SVA_ERR("ev_lock and ev_loss together");
  a_evx: assert property (@(posedge clk) disable iff (rst) (ev_sh_err || ev_type_err || ev_os) |-> $past(lock)) else `SVA_ERR("a block event without lock");
  c_l: assert property (@(posedge clk) disable iff (rst) not (ev_lock)) else c_lock++;
  c_ls: assert property (@(posedge clk) disable iff (rst) not (ev_loss)) else c_loss++;
  c_sl: assert property (@(posedge clk) disable iff (rst) not (ev_slip && !ev_loss)) else c_slip++;
  c_sh_: assert property (@(posedge clk) disable iff (rst) not (ev_sh_err)) else c_sh++;
  c_ty: assert property (@(posedge clk) disable iff (rst) not (ev_type_err)) else c_type++;
  c_o: assert property (@(posedge clk) disable iff (rst) not (ev_os)) else c_os++;
  final $display("SVA_COV %m lock %0d", c_lock);
  final $display("SVA_COV %m loss %0d", c_loss);
  final $display("SVA_COV %m hunting_slip %0d", c_slip);
  final $display("SVA_COV %m sh_err %0d", c_sh);
  final $display("SVA_COV %m type_err %0d", c_type);
  final $display("SVA_COV %m ordered_set %0d", c_os);
endmodule

module mac64_rx_sva (input logic clk, rst, m_v, m_sof, m_end, m_fcs_ok, m_err, rx_sop, input logic [3:0] m_nb);
  int unsigned c_good = 0, c_bad = 0, c_err = 0, c_both = 0;
  a_nb: assert property (@(posedge clk) disable iff (rst) m_v |-> (m_nb >= 4'd1 && m_nb <= 4'd8)) else `SVA_ERR("m_nb outside 1..8 with m_v");
  a_sof: assert property (@(posedge clk) disable iff (rst) m_sof |-> m_v) else `SVA_ERR("m_sof without m_v");
  // m_end (frame 1's verdict, two clocks after its terminate) and m_err (frame 2 aborted) can legitimately fall in the same clock: they belong to
  // different frames, so this is a cover, not a violation (the first version of this file asserted the opposite and t_xg found the counter-example)
  c_ee: assert property (@(posedge clk) disable iff (rst) not (m_end && m_err)) else c_both++;
  c_g: assert property (@(posedge clk) disable iff (rst) not (m_end && m_fcs_ok)) else c_good++;
  c_b: assert property (@(posedge clk) disable iff (rst) not (m_end && !m_fcs_ok)) else c_bad++;
  c_e: assert property (@(posedge clk) disable iff (rst) not (m_err)) else c_err++;
  final $display("SVA_COV %m frame_good_fcs %0d", c_good);
  final $display("SVA_COV %m frame_bad_fcs %0d", c_bad);
  final $display("SVA_COV %m abort %0d", c_err);
  final $display("SVA_COV %m end_and_abort_same_clock %0d", c_both);
endmodule

bind pcs_tx   pcs_tx_sva   u_sva (.*);
bind mac64_tx mac64_tx_sva u_sva (.*);
bind pcs_rx   pcs_rx_sva   u_sva (.*);
bind mac64_rx mac64_rx_sva u_sva (.*);
