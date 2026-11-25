`timescale 1ns/1ps
// itch_ifs.sv: the interfaces of the ITCH/OUCH UVM bench (brief 170). One clock (the 10G core's user clock, 161.13 MHz).
//   itch_in_if   the XGMII words into the receive MAC (x_v, x_d, x_c): a gearbox-style valid, 64 data bits, 8 control bits (1 = control character)
//   itch_out_if  the XGMII words out of the transmit MAC (t_d, t_c) and the PCS pause strobe `adv` (the PCS takes a word only in clocks where adv is high)
//   itch_cfg_if  reset, the static configuration vector, the host vector CFG2 (registers and command words) and the status vector STAT2 (counters and flags)

interface itch_in_if (input logic clk);
  logic        x_v = 1'b0;
  logic [63:0] x_d = '0;
  logic [7:0]  x_c = 8'hFF;
  longint unsigned cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;
  clocking cb @(posedge clk);
    default input #1step output #1;
    inout x_v, x_d, x_c;
  endclocking
endinterface

interface itch_out_if (input logic clk);
  logic [63:0] t_d;
  logic [7:0]  t_c;
  logic        t_sop, t_eop, adv, underrun;
  longint unsigned cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;
  clocking cb @(posedge clk);
    default input #1step output #1;
    input t_d, t_c, t_sop, t_eop, adv, underrun;
  endclocking
endinterface

interface itch_cfg_if (input logic clk);
  logic          rst = 1'b1;
  logic [420:0]  cfg = '0;
  logic [1023:0] cfg2 = '0;
  logic [3071:0] stat2;
  longint unsigned cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;
  clocking cb @(posedge clk);
    default input #1step output #1;
    output rst, cfg, cfg2;
    input  stat2;
  endclocking
  function automatic bit [31:0] stat_word(int i);
    return stat2[32*i +: 32];
  endfunction
endinterface
