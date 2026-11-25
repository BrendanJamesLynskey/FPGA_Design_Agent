// Brief 208: two clocks into one global clock mux, with the UG949 Fig. 101 paths switchable.
//   RELATED=0: clk0 and clk1 come from two input ports (unrelated clocks).
//   RELATED=1: one input port feeds an MMCM; clk0 = 100 MHz, clk1 = 150 MHz (related clocks).
//   INTERACT=1: path A (FD0 -> FDM, through DEPTH adds), path B (FD1 -> FDM), path C (FDM -> FD0) exist.
//   INTERACT=0: the two clocks meet only on the mux fanout.
//   MUXTYPE=0: BUFGMUX (select drives the CE pins); 1: BUFGMUX_CTRL (select drives the S pins).
//   US=1: UltraScale+ MMCM (MMCME4_BASE); US=0: 7 series (MMCME2_BASE).
module mux_top #(parameter RELATED = 0, parameter INTERACT = 1, parameter MUXTYPE = 0,
                 parameter US = 0, parameter DEPTH = 3) (
  input  wire clk0_p,     // RELATED=0: clock 0; RELATED=1: the MMCM reference
  input  wire clk1_p,     // RELATED=0: clock 1; RELATED=1: unused
  input  wire sel_in,
  output reg  dout0, output reg dout1, output reg doutm);

  wire clk0_raw, clk1_raw;
  generate if (RELATED) begin : g_rel
    wire fb;
    if (US) begin : g_us
      MMCME4_BASE #(.CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(9.0), .CLKOUT0_DIVIDE_F(9.0), .CLKOUT1_DIVIDE(6))
        u_mmcm (.CLKIN1(clk0_p), .CLKFBIN(fb), .CLKFBOUT(fb), .CLKOUT0(clk0_raw), .CLKOUT1(clk1_raw),
                .RST(1'b0), .PWRDWN(1'b0), .LOCKED(), .CLKFBOUTB(), .CLKOUT0B(), .CLKOUT1B(), .CLKOUT2(),
                .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(), .CLKOUT4(), .CLKOUT5(), .CLKOUT6());
    end else begin : g_7
      MMCME2_BASE #(.CLKIN1_PERIOD(10.0), .CLKFBOUT_MULT_F(9.0), .CLKOUT0_DIVIDE_F(9.0), .CLKOUT1_DIVIDE(6))
        u_mmcm (.CLKIN1(clk0_p), .CLKFBIN(fb), .CLKFBOUT(fb), .CLKOUT0(clk0_raw), .CLKOUT1(clk1_raw),
                .RST(1'b0), .PWRDWN(1'b0), .LOCKED(), .CLKFBOUTB(), .CLKOUT0B(), .CLKOUT1B(), .CLKOUT2(),
                .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(), .CLKOUT4(), .CLKOUT5(), .CLKOUT6());
    end
  end else begin : g_unrel
    assign clk0_raw = clk0_p;
    assign clk1_raw = clk1_p;
  end endgenerate

  wire clk0, clk1, clkm;
  BUFG u_bufg0 (.I(clk0_raw), .O(clk0));
  BUFG u_bufg1 (.I(clk1_raw), .O(clk1));

  reg sel_r = 1'b0;
  always @(posedge clk0) sel_r <= sel_in;

  generate if (MUXTYPE == 0) begin : g_bufgmux
    BUFGMUX u_mux (.I0(clk0_raw), .I1(clk1_raw), .S(sel_r), .O(clkm));
  end else begin : g_bufgmux_ctrl
    BUFGMUX_CTRL u_mux (.I0(clk0_raw), .I1(clk1_raw), .S(sel_r), .O(clkm));
  end endgenerate

  // FD0, FD1: one LFSR per source clock
  reg [31:0] r0 = 32'h1, r1 = 32'h1, rm = 32'h1, back = 32'h0;
  always @(posedge clk0) r0 <= {r0[30:0], r0[31] ^ r0[21] ^ r0[1] ^ r0[0]};
  always @(posedge clk1) r1 <= {r1[30:0], r1[31] ^ r1[21] ^ r1[1] ^ r1[0]};

  // path A: a chain of DEPTH 32-bit adds on FD0's output
  wire [31:0] a [0:DEPTH];
  assign a[0] = r0;
  genvar i;
  generate for (i = 0; i < DEPTH; i = i + 1) begin : g_add
    assign a[i+1] = a[i] + {a[i][15:0], a[i][31:16]} + 32'h9E3779B9;
  end endgenerate

  // FDM: registers on the muxed clock
  generate if (INTERACT) begin : g_int
    always @(posedge clkm) rm <= a[DEPTH] ^ r1 ^ {rm[30:0], rm[31]};   // paths A and B
    always @(posedge clk0) back <= rm;                                 // path C
  end else begin : g_noint
    always @(posedge clkm) rm <= {rm[30:0], rm[31] ^ rm[21] ^ rm[1] ^ rm[0]};
    always @(posedge clk0) back <= a[DEPTH];
  end endgenerate

  always @(posedge clk0) dout0 <= ^back;
  always @(posedge clk1) dout1 <= ^r1;
  always @(posedge clkm) doutm <= ^rm;
endmodule
