`timescale 1ns/1ps
// tb_itch_top.sv: the hardware top of the ITCH/OUCH UVM bench (brief 170). The design under test is `itch_unit` of build rm_gp_itch (sim/itch_unit.sv): the REAL receive MAC, the
// UDP adapter, brief 110's Mold/ITCH/book/risk/OUCH blocks, the order-frame builder, the transmit multiplexer and the REAL transmit MAC. The bench drives XGMII words into it and
// watches the XGMII words and the status vector that come out. PAUSE = 1 gives the transmit MAC the PCS gearbox's one-clock-in-33 pause; PAUSE = 0 never pauses.
module tb_itch_top #(parameter bit PAUSE = 1'b1);
  import uvm_pkg::*;
  import itch_uvm_pkg::*;
  `include "uvm_macros.svh"

  logic clk = 1'b0;
  always #3.103 clk = ~clk;

  itch_in_if  inif  (clk);
  itch_out_if outif (clk);
  itch_cfg_if cfgif (clk);

  itch_unit #(.PAUSE(PAUSE)) dut (.clk, .rst(cfgif.rst), .x_v(inif.x_v), .x_d(inif.x_d), .x_c(inif.x_c), .cfg(cfgif.cfg), .cfg2(cfgif.cfg2), .stat2(cfgif.stat2),
                                  .t_d(outif.t_d), .t_c(outif.t_c), .t_sop(outif.t_sop), .t_eop(outif.t_eop), .ts());
  assign outif.adv = dut.adv;
  assign outif.underrun = dut.underrun;

  itch_sva u_sva (.clk, .rst(cfgif.rst), .x_v(inif.x_v), .x_d(inif.x_d), .x_c(inif.x_c), .t_d(outif.t_d), .t_c(outif.t_c), .t_sop(outif.t_sop), .t_eop(outif.t_eop),
                  .adv(dut.adv), .underrun(dut.underrun), .stat2(cfgif.stat2));

  initial begin
    uvm_config_db#(virtual itch_in_if)::set(null, "*", "in_vif", inif);
    uvm_config_db#(virtual itch_out_if)::set(null, "*", "out_vif", outif);
    uvm_config_db#(virtual itch_cfg_if)::set(null, "*", "cfg_vif", cfgif);
    run_test();
  end
endmodule
