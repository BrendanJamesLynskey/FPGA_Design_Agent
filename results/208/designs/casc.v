// Brief 208 (d): BUFGCTRL clock-mux trees fed by seven MMCM outputs (100 MHz reference, VCO 900 MHz).
//   MODE=0: balanced 4:1 (UG949 Fig. 67): two first-level BUFGCTRLs into one.
//   MODE=1: balanced 3:1 (the Fig. 67 equivalent): one first-level BUFGCTRL and one direct input.
//   MODE=2: linear chain of N BUFGCTRLs (N+1 inputs, reusing the seven clocks in turn); N=7 is UG949 Fig. 69 (8:1).
// Every BUFGCTRL selects on S (CE tied high, IGNORE tied low), the glitch-free style. The selects come from ports.
module casc #(parameter MODE = 0, parameter N = 7, parameter US = 0) (
  input  wire clk_in, input wire [31:0] sel, output reg dout);
  wire [6:0] c;
  wire fb;
  generate if (US) begin : g_us
    MMCME4_BASE #(.CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(9.0), .CLKOUT0_DIVIDE_F(9.0), .CLKOUT1_DIVIDE(6),
                  .CLKOUT2_DIVIDE(8), .CLKOUT3_DIVIDE(10), .CLKOUT4_DIVIDE(12), .CLKOUT5_DIVIDE(15), .CLKOUT6_DIVIDE(18))
      u_mmcm (.CLKIN1(clk_in), .CLKFBIN(fb), .CLKFBOUT(fb), .CLKOUT0(c[0]), .CLKOUT1(c[1]), .CLKOUT2(c[2]),
              .CLKOUT3(c[3]), .CLKOUT4(c[4]), .CLKOUT5(c[5]), .CLKOUT6(c[6]), .RST(1'b0), .PWRDWN(1'b0), .LOCKED(),
              .CLKFBOUTB(), .CLKOUT0B(), .CLKOUT1B(), .CLKOUT2B(), .CLKOUT3B());
  end else begin : g_7
    MMCME2_BASE #(.CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(9.0), .CLKOUT0_DIVIDE_F(9.0), .CLKOUT1_DIVIDE(6),
                  .CLKOUT2_DIVIDE(8), .CLKOUT3_DIVIDE(10), .CLKOUT4_DIVIDE(12), .CLKOUT5_DIVIDE(15), .CLKOUT6_DIVIDE(18))
      u_mmcm (.CLKIN1(clk_in), .CLKFBIN(fb), .CLKFBOUT(fb), .CLKOUT0(c[0]), .CLKOUT1(c[1]), .CLKOUT2(c[2]),
              .CLKOUT3(c[3]), .CLKOUT4(c[4]), .CLKOUT5(c[5]), .CLKOUT6(c[6]), .RST(1'b0), .PWRDWN(1'b0), .LOCKED(),
              .CLKFBOUTB(), .CLKOUT0B(), .CLKOUT1B(), .CLKOUT2B(), .CLKOUT3B());
  end endgenerate

  wire clkm;
  generate if (MODE == 0) begin : g_bal4
    wire l1a, l1b;
    BUFGCTRL u_l1a (.I0(c[0]), .I1(c[1]), .S0(~sel[0]), .S1(sel[0]), .CE0(1'b1), .CE1(1'b1), .IGNORE0(1'b0), .IGNORE1(1'b0), .O(l1a));
    BUFGCTRL u_l1b (.I0(c[2]), .I1(c[3]), .S0(~sel[1]), .S1(sel[1]), .CE0(1'b1), .CE1(1'b1), .IGNORE0(1'b0), .IGNORE1(1'b0), .O(l1b));
    BUFGCTRL u_l2  (.I0(l1a),  .I1(l1b),  .S0(~sel[2]), .S1(sel[2]), .CE0(1'b1), .CE1(1'b1), .IGNORE0(1'b0), .IGNORE1(1'b0), .O(clkm));
  end else if (MODE == 1) begin : g_bal3
    wire l1a;
    BUFGCTRL u_l1a (.I0(c[0]), .I1(c[1]), .S0(~sel[0]), .S1(sel[0]), .CE0(1'b1), .CE1(1'b1), .IGNORE0(1'b0), .IGNORE1(1'b0), .O(l1a));
    BUFGCTRL u_l2  (.I0(l1a),  .I1(c[2]), .S0(~sel[2]), .S1(sel[2]), .CE0(1'b1), .CE1(1'b1), .IGNORE0(1'b0), .IGNORE1(1'b0), .O(clkm));
  end else begin : g_chain
    wire [N:0] s;
    assign s[0] = c[0];
    genvar k;
    for (k = 0; k < N; k = k + 1) begin : g_st
      BUFGCTRL u_st (.I0(s[k]), .I1(c[(k + 1) % 7]), .S0(~sel[k]), .S1(sel[k]), .CE0(1'b1), .CE1(1'b1),
                     .IGNORE0(1'b0), .IGNORE1(1'b0), .O(s[k+1]));
    end
    assign clkm = s[N];
  end endgenerate

  reg [15:0] cnt = 16'h0;
  always @(posedge clkm) cnt <= cnt + 16'h1;
  always @(posedge clkm) dout <= ^cnt;
endmodule
