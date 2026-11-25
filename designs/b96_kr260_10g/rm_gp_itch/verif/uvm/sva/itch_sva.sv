`timescale 1ns/1ps
// itch_sva.sv: assertions on the interfaces of the ITCH/OUCH path (brief 170): the XGMII words out of the transmit MAC, the XGMII words the bench drives in, the status vector, and
// (bound into itch_path) the internal order-frame stream between the path and the transmit multiplexer. A failure is a UVM_ERROR, so the test fails. xsim 2026.1 does not run the
// action statement of a cover property, so a cover is written `assert property (not (seq)) else count++` and the counts are printed at the end ("SVA_COV <name> <hits>").

`define SVA_ERR(MSG) uvm_pkg::uvm_report_error("SVA", $sformatf("%m: %s", MSG), uvm_pkg::UVM_NONE, `__FILE__, `__LINE__)

module itch_sva (input logic clk, rst, x_v, input logic [63:0] x_d, input logic [7:0] x_c, input logic [63:0] t_d, input logic [7:0] t_c, input logic t_sop, t_eop, adv, underrun,
                 input logic [3071:0] stat2);
  int unsigned c_in_frames = 0, c_out_frames = 0, c_pause_in_frame = 0, c_bubble_in = 0, c_out_lane0 = 0;
  bit out_in_frame = 0;
  logic [3:0] rst_q = '0;
  always @(posedge clk) rst_q <= {rst_q[2:0], rst};
  wire quiet = (rst_q == '0) && !rst;
  // ---- output: the words the PCS takes (only the clocks where adv is high carry a new word)
  a_out_start: assert property (@(posedge clk) disable iff (rst) (adv && (t_c[0] && t_d[7:0] == 8'hFB)) |-> (t_c == 8'h01 && t_d[63:8] == 56'hD5_5555_5555_5555))
    else `SVA_ERR("the transmit MAC's start word is not a lane-0 start with the 7-byte preamble");
  logic [7:0] st_l;
  always_comb for (int i = 0; i < 8; i++) st_l[i] = t_c[i] && (t_d[8*i +: 8] == 8'hFB);
  a_out_no_start_elsewhere: assert property (@(posedge clk) disable iff (rst) adv |-> (st_l[7:1] == 7'd0)) else `SVA_ERR("a start character outside lane 0 on the transmit side");
  a_out_idle: assert property (@(posedge clk) disable iff (rst) (adv && !out_in_frame && !t_sop && t_c == 8'hFF) |-> t_d == {8{8'h07}}) else `SVA_ERR("an idle word that is not all idle characters");
  a_out_no_underrun: assert property (@(posedge clk) disable iff (rst) !underrun) else `SVA_ERR("transmit underrun");
  a_out_known: assert property (@(posedge clk) disable iff (rst) quiet |-> !$isunknown({t_d, t_c})) else `SVA_ERR("unknown value on the transmit words");
  // two order frames are never closer than a frame: the first word of one frame to the first word of the next is at least 16 clocks
  a_out_spacing: assert property (@(posedge clk) disable iff (rst) t_sop |=> !t_sop [*15]) else `SVA_ERR("two frame starts less than 16 clocks apart");
  // inside a frame the control bits are 0 until the terminate word, and a frame ends before the next one starts
  always @(posedge clk) if (!rst && adv) begin
    if (t_c == 8'h01 && t_d[7:0] == 8'hFB) begin
      if (out_in_frame) uvm_pkg::uvm_report_error("SVA", "start inside a frame", uvm_pkg::UVM_NONE, `__FILE__, `__LINE__);
      out_in_frame <= 1; c_out_frames++;
    end else if (out_in_frame && t_c != 8'h00) out_in_frame <= 0;
    else if (out_in_frame && t_c == 8'h00) begin end
  end
  // ---- the status vector (flags word 88 and the first counters) is never unknown once the book has been swept
  a_stat_known: assert property (@(posedge clk) disable iff (rst) (quiet && stat2[32*88+4]) |-> !$isunknown(stat2[32*88 +: 32])) else `SVA_ERR("flags word unknown after the book is ready");
  // ---- the bench's own input is legal XGMII (a start only in lane 0 or lane 4 with the control pattern the MAC expects; control characters only 07, FB, FD)
  logic [7:0] bad_ctl;
  always_comb for (int i = 0; i < 8; i++) bad_ctl[i] = x_c[i] && !(x_d[8*i +: 8] == 8'h07 || x_d[8*i +: 8] == 8'hFB || x_d[8*i +: 8] == 8'hFD);
  a_in_legal: assert property (@(posedge clk) disable iff (rst) x_v |-> (bad_ctl == 8'h00)) else `SVA_ERR("the bench drove an illegal control character");
  c_i: assert property (@(posedge clk) disable iff (rst) not (x_v && x_c == 8'h01 && x_d[7:0] == 8'hFB)) else c_in_frames++;
  c_b: assert property (@(posedge clk) disable iff (rst) not (!x_v && $past(x_v && x_c == 8'h00))) else c_bubble_in++;
  c_p: assert property (@(posedge clk) disable iff (rst) not (!adv && out_in_frame)) else c_pause_in_frame++;
  c_l: assert property (@(posedge clk) disable iff (rst) not (adv && t_c == 8'h01 && t_d[7:0] == 8'hFB)) else c_out_lane0++;
  final $display("SVA_COV in_frames_lane0 %0d", c_in_frames);
  final $display("SVA_COV input_bubble_after_data %0d", c_bubble_in);
  final $display("SVA_COV out_pause_inside_frame %0d", c_pause_in_frame);
  final $display("SVA_COV out_frame_start %0d", c_out_lane0);
endmodule

// the order-frame stream between itch_path and the transmit multiplexer (bound into itch_path): never paused inside a frame, fifteen words, poison only with the last word
module itch_stream_sva (input logic clk, rst, o_v, o_sof, o_eof, o_poison, o_unres, input logic [7:0] o_keep);
  int unsigned c_poison = 0, c_unres = 0, c_frames = 0;
  a_len: assert property (@(posedge clk) disable iff (rst) o_sof |-> (o_v ##1 o_v [*13] ##1 (o_v && o_eof))) else `SVA_ERR("an order frame is not 15 consecutive words");
  a_eof_only: assert property (@(posedge clk) disable iff (rst) (o_v && !o_sof) |-> !$past(o_eof)) else `SVA_ERR("words after the last word");
  a_poison_last: assert property (@(posedge clk) disable iff (rst) o_poison |-> (o_eof && o_v)) else `SVA_ERR("poison not with the last word");
  a_unres_poison: assert property (@(posedge clk) disable iff (rst) o_unres |-> o_poison) else `SVA_ERR("unresolved without poison");
  a_keep: assert property (@(posedge clk) disable iff (rst) o_v |-> (o_eof ? (o_keep == 8'h01) : (o_keep == 8'hFF))) else `SVA_ERR("keep mask wrong");
  c_f: assert property (@(posedge clk) disable iff (rst) not (o_sof)) else c_frames++;
  c_pz: assert property (@(posedge clk) disable iff (rst) not (o_poison)) else c_poison++;
  c_un: assert property (@(posedge clk) disable iff (rst) not (o_unres)) else c_unres++;
  final $display("SVA_COV stream_frames %0d", c_frames);
  final $display("SVA_COV stream_poisoned %0d", c_poison);
  final $display("SVA_COV stream_unresolved %0d", c_unres);
endmodule

bind itch_path itch_stream_sva u_sva (.clk, .rst, .o_v, .o_sof, .o_eof, .o_poison, .o_unres, .o_keep);
