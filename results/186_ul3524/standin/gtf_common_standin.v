// GTF_COMMON_STANDIN: our own behavioural stand-in for the common block (QPLL) of the UltraScale+ GTF transceiver.
// Written for brief 186 (owner decision 33) from public documentation only: UG576 chapter 2 (Equation 2-3 PLL output
// frequency = reference x N / M, Table 2-12 and 2-13 for N, M; port behaviour of QPLL0/1 lock, reset, power-down,
// reference selection). No AMD source was copied or decompiled; the port names are those of the primitive.
//
// What it does: selects a reference clock (QPLLnREFCLKSEL), measures its period, and after reset release plus a
// fixed number of reference cycles raises QPLLnLOCK and drives QPLLnOUTCLK at f_ref x N / M (50 % duty, phase
// derived from the reference edge) and QPLLnOUTREFCLK as the selected reference. Reset or power-down drops
// lock and stops the output clock low. DRP answers every access with DRPRDY one DRPCLK later and reads zero.
// What it does NOT model: PLL jitter, lock time, VCO band choice, fractional-N (SDM), calibration, DRP registers,
// rate switching, refclk-lost and feedback-lost detection (the lost flags stay 0), monitor outputs (0), the
// second PLL's differences from the first (both use the same model). Validity: fixed integer N, M from the
// parameters (the attribute QPLLn_FBDIV, as the Wizard uses; the QPLLnFBDIV port is "reserved, set to 0" in UG576).
`timescale 1fs/1fs
module GTF_COMMON_STANDIN #(
  parameter integer QPLL0_FBDIV = 64,
  parameter integer QPLL0_REFCLK_DIV = 1,
  parameter integer QPLL1_FBDIV = 64,
  parameter integer QPLL1_REFCLK_DIV = 1,
  parameter integer LOCK_REFCLKS = 256   // reference cycles from reset release to lock
)(
  input wire  BGBYPASSB,
  input wire  BGMONITORENB,
  input wire  BGPDB,
  input wire  BGRCALOVRDENB,
  input wire  DRPCLK,
  input wire  DRPEN,
  input wire  DRPWE,
  input wire  GTGREFCLK0,
  input wire  GTGREFCLK1,
  input wire  GTNORTHREFCLK00,
  input wire  GTNORTHREFCLK01,
  input wire  GTNORTHREFCLK10,
  input wire  GTNORTHREFCLK11,
  input wire  GTREFCLK00,
  input wire  GTREFCLK01,
  input wire  GTREFCLK10,
  input wire  GTREFCLK11,
  input wire  GTSOUTHREFCLK00,
  input wire  GTSOUTHREFCLK01,
  input wire  GTSOUTHREFCLK10,
  input wire  GTSOUTHREFCLK11,
  input wire  QPLL0CLKRSVD0,
  input wire  QPLL0CLKRSVD1,
  input wire  QPLL0LOCKDETCLK,
  input wire  QPLL0LOCKEN,
  input wire  QPLL0PD,
  input wire  QPLL0RESET,
  input wire  QPLL1CLKRSVD0,
  input wire  QPLL1CLKRSVD1,
  input wire  QPLL1LOCKDETCLK,
  input wire  QPLL1LOCKEN,
  input wire  QPLL1PD,
  input wire  QPLL1RESET,
  input wire  RCALENB,
  input wire  SDM0RESET,
  input wire  SDM0TOGGLE,
  input wire  SDM1RESET,
  input wire  SDM1TOGGLE,
  input wire [15:0] DRPADDR,
  input wire [15:0] DRPDI,
  input wire [1:0] SDM0WIDTH,
  input wire [1:0] SDM1WIDTH,
  input wire [24:0] SDM0DATA,
  input wire [24:0] SDM1DATA,
  input wire [2:0] QPLL0REFCLKSEL,
  input wire [2:0] QPLL1REFCLKSEL,
  input wire [4:0] BGRCALOVRD,
  input wire [4:0] QPLLRSVD2,
  input wire [4:0] QPLLRSVD3,
  input wire [7:0] PMARSVD0,
  input wire [7:0] PMARSVD1,
  input wire [7:0] QPLL0FBDIV,
  input wire [7:0] QPLL1FBDIV,
  input wire [7:0] QPLLRSVD1,
  input wire [7:0] QPLLRSVD4,
  output wire  DRPRDY,
  output wire  QPLL0FBCLKLOST,
  output wire  QPLL0LOCK,
  output wire  QPLL0OUTCLK,
  output wire  QPLL0OUTREFCLK,
  output wire  QPLL0REFCLKLOST,
  output wire  QPLL1FBCLKLOST,
  output wire  QPLL1LOCK,
  output wire  QPLL1OUTCLK,
  output wire  QPLL1OUTREFCLK,
  output wire  QPLL1REFCLKLOST,
  output wire  REFCLKOUTMONITOR0,
  output wire  REFCLKOUTMONITOR1,
  output wire [14:0] SDM0TESTDATA,
  output wire [14:0] SDM1TESTDATA,
  output wire [15:0] DRPDO,
  output wire [1:0] RXRECCLK0SEL,
  output wire [1:0] RXRECCLK1SEL,
  output wire [3:0] SDM0FINALOUT,
  output wire [3:0] SDM1FINALOUT,
  output wire [7:0] PMARSVDOUT0,
  output wire [7:0] PMARSVDOUT1,
  output wire [7:0] QPLLDMONITOR0,
  output wire [7:0] QPLLDMONITOR1);

  // reference selection (UG576 QPLLnREFCLKSEL: 001 GTREFCLK0, 010 GTREFCLK1, 011 GTNORTHREFCLK0, 100 GTNORTHREFCLK1,
  // 101 GTSOUTHREFCLK0, 110 GTSOUTHREFCLK1, 111 GTGREFCLK)
  function sel0(input [2:0] s, input a, input b, input c, input d, input e, input f, input g);
    case (s) 3'b001: sel0=a; 3'b010: sel0=b; 3'b011: sel0=c; 3'b100: sel0=d; 3'b101: sel0=e; 3'b110: sel0=f; 3'b111: sel0=g; default: sel0=1'b0; endcase
  endfunction
  wire ref0 = sel0(QPLL0REFCLKSEL, GTREFCLK00, GTREFCLK01, GTNORTHREFCLK00, GTNORTHREFCLK01, GTSOUTHREFCLK00, GTSOUTHREFCLK01, GTGREFCLK0);
  wire ref1 = sel0(QPLL1REFCLKSEL, GTREFCLK10, GTREFCLK11, GTNORTHREFCLK10, GTNORTHREFCLK11, GTSOUTHREFCLK10, GTSOUTHREFCLK11, GTGREFCLK1);

  qpll_standin #(.N(QPLL0_FBDIV), .M(QPLL0_REFCLK_DIV), .LOCK_REFCLKS(LOCK_REFCLKS)) u_q0 (
    .ref_clk(ref0), .reset(QPLL0RESET), .pd(QPLL0PD), .outclk(QPLL0OUTCLK), .outrefclk(QPLL0OUTREFCLK), .lock(QPLL0LOCK));
  qpll_standin #(.N(QPLL1_FBDIV), .M(QPLL1_REFCLK_DIV), .LOCK_REFCLKS(LOCK_REFCLKS)) u_q1 (
    .ref_clk(ref1), .reset(QPLL1RESET), .pd(QPLL1PD), .outclk(QPLL1OUTCLK), .outrefclk(QPLL1OUTREFCLK), .lock(QPLL1LOCK));

  assign QPLL0FBCLKLOST = 1'b0;  assign QPLL0REFCLKLOST = 1'b0;
  assign QPLL1FBCLKLOST = 1'b0;  assign QPLL1REFCLKLOST = 1'b0;
  assign REFCLKOUTMONITOR0 = 1'b0; assign REFCLKOUTMONITOR1 = 1'b0;
  assign SDM0TESTDATA = 15'd0; assign SDM1TESTDATA = 15'd0;
  assign RXRECCLK0SEL = 2'd0;  assign RXRECCLK1SEL = 2'd0;
  assign SDM0FINALOUT = 4'd0;  assign SDM1FINALOUT = 4'd0;
  assign PMARSVDOUT0 = 8'd0;   assign PMARSVDOUT1 = 8'd0;
  assign QPLLDMONITOR0 = 8'd0; assign QPLLDMONITOR1 = 8'd0;

  // DRP: ready one DRPCLK after an enable; data reads 0
  reg drprdy_q = 1'b0;
  always @(posedge DRPCLK) drprdy_q <= DRPEN;
  assign DRPRDY = drprdy_q;
  assign DRPDO = 16'd0;
endmodule

// One PLL: output frequency = reference x N / M.
module qpll_standin #(parameter integer N = 64, parameter integer M = 1, parameter integer LOCK_REFCLKS = 256)(
  input  wire ref_clk, input wire reset, input wire pd,
  output reg  outclk, output wire outrefclk, output reg lock);
  assign outrefclk = ref_clk;
  real t_last, t_ref;            // reference edge times and measured period, in fs
  real half;
  integer n_edges, run_edges;
  reg    run;
  initial begin outclk = 1'b0; lock = 1'b0; t_last = 0.0; t_ref = 0.0; n_edges = 0; run_edges = 0; run = 1'b0; end
  // measure the reference period and count cycles since reset release
  always @(posedge ref_clk) begin
    if (n_edges > 0) t_ref = $realtime - t_last;
    t_last = $realtime;
    n_edges = n_edges + 1;
    if (reset || pd || n_edges < 3) run_edges = 0; else run_edges = run_edges + 1;
    if (!reset && !pd && n_edges >= 3 && run_edges == 1) begin
      half = t_ref * M / N / 2.0;
      run = 1'b1;
    end
    if (run_edges >= LOCK_REFCLKS) lock <= 1'b1;
  end
  always @(posedge reset or posedge pd) begin run = 1'b0; lock <= 1'b0; run_edges = 0; end
  // output clock: starts on a reference edge, runs while 'run' is set
  always @(posedge run) begin
    outclk = 1'b1;
    while (run) begin #(half) outclk = ~outclk; end
    outclk = 1'b0;
  end
endmodule
