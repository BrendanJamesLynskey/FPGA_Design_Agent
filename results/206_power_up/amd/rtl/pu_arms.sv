// Brief 206: power-up (initial) value probes for Vivado. Each module is one arm of PLAN_AND_PREREGISTRATION.md.
// INITV = 0 or 1 selects the declaration initialiser; the pair measures what a power-up value of 1 costs.
// Initial values are written as declaration initialisers (the form UG901 and UG949 describe).

// X1: plain register, no reset
module x1_plain #(parameter bit INITV = 1'b1) (input logic clk, input logic [7:0] d, output logic [7:0] q);
  logic [7:0] r = {8{INITV}};
  always_ff @(posedge clk) r <= d;
  assign q = r;
endmodule

// X2: synchronous reset to 0, initial value INITV
module x2_sreset0 #(parameter bit INITV = 1'b1) (input logic clk, rst, input logic [7:0] d, output logic [7:0] q);
  logic [7:0] r = {8{INITV}};
  always_ff @(posedge clk) if (rst) r <= '0; else r <= d;
  assign q = r;
endmodule

// X3: synchronous set to 1, initial value INITV (pair: INITV=1 is the natural FDSE; INITV=0 is the opposite sense)
module x3_sset1 #(parameter bit INITV = 1'b0) (input logic clk, rst, input logic [7:0] d, output logic [7:0] q);
  logic [7:0] r = {8{INITV}};
  always_ff @(posedge clk) if (rst) r <= '1; else r <= d;
  assign q = r;
endmodule

// X4: asynchronous clear, initial value INITV
module x4_aclr #(parameter bit INITV = 1'b1) (input logic clk, rst, input logic [7:0] d, output logic [7:0] q);
  logic [7:0] r = {8{INITV}};
  always_ff @(posedge clk or posedge rst) if (rst) r <= '0; else r <= d;
  assign q = r;
endmodule

// X5: asynchronous preset, initial value INITV
module x5_apre #(parameter bit INITV = 1'b0) (input logic clk, rst, input logic [7:0] d, output logic [7:0] q);
  logic [7:0] r = {8{INITV}};
  always_ff @(posedge clk or posedge rst) if (rst) r <= '1; else r <= d;
  assign q = r;
endmodule

// X6: 64-bit register-to-register pipeline (three stages, no logic between), every bit initial INITV
module x6_pipe64 #(parameter bit INITV = 1'b1) (input logic clk, input logic [63:0] d, output logic [63:0] q);
  (* shreg_extract = "no" *) logic [63:0] s0 = {64{INITV}}, s1 = {64{INITV}}, s2 = {64{INITV}};
  always_ff @(posedge clk) begin s0 <= d; s1 <= s0; s2 <= s1; end
  assign q = s2;
endmodule

// X7: input and output registers packed into the IOB, initial INITV; RST_MODE 0 none, 1 sync reset to 0, 2 async clear.
module x7_iob #(parameter bit INITV = 1'b1, parameter int RST_MODE = 0)
  (input logic clk, rst, input logic [3:0] din, output logic [3:0] dout);
  (* IOB = "TRUE" *) logic [3:0] ireg = {4{INITV}};
  (* IOB = "TRUE" *) logic [3:0] oreg = {4{INITV}};
  logic [3:0] mid = '0;
  generate
    if (RST_MODE == 2) begin : g_async
      always_ff @(posedge clk or posedge rst) if (rst) begin ireg <= '0; oreg <= '0; end else begin ireg <= din; oreg <= mid; end
    end else if (RST_MODE == 1) begin : g_sync
      always_ff @(posedge clk) if (rst) begin ireg <= '0; oreg <= '0; end else begin ireg <= din; oreg <= mid; end
    end else begin : g_none
      always_ff @(posedge clk) begin ireg <= din; oreg <= mid; end
    end
  endgenerate
  always_ff @(posedge clk) mid <= ireg ^ {ireg[2:0], ireg[3]};
  assign dout = oreg;
endmodule

// X8: registers around a multiplier: A/B input registers, M register, P output register, all initial INITV (all ones).
module x8_dsp #(parameter bit INITV = 1'b1) (input logic clk, input logic signed [17:0] a, b, output logic signed [35:0] p);
  logic signed [17:0] ar = {18{INITV}}, br = {18{INITV}};
  logic signed [35:0] mr = {36{INITV}}, pr = {36{INITV}};
  always_ff @(posedge clk) begin ar <= a; br <= b; mr <= ar * br; pr <= mr; end
  assign p = pr;
endmodule

// X9: block RAM 1024 x 32, array initialised (non-zero pattern), read register and output register initial INITV pattern.
module x9_bram #(parameter bit INITV = 1'b1)
  (input logic clk, we, input logic [9:0] wa, ra, input logic [31:0] wd, output logic [31:0] q);
  (* ram_style = "block" *) logic [31:0] mem [0:1023];
  initial for (int i = 0; i < 1024; i++) mem[i] = 32'h1000_0000 + i;
  logic [31:0] rd = INITV ? 32'hA5A5_0F0F : 32'h0, oq = INITV ? 32'h3C3C_F0F0 : 32'h0;
  always_ff @(posedge clk) begin
    if (we) mem[wa] <= wd;
    rd <= mem[ra];
    oq <= rd;
  end
  assign q = oq;
endmodule

// X10: distributed RAM 32 x 8 with initial contents, and a 16-deep shift register with initial contents.
module x10_lutram_srl #(parameter bit INITV = 1'b1)
  (input logic clk, we, input logic [4:0] a, input logic [7:0] wd, input logic sin, output logic [7:0] rq, output logic sout);
  (* ram_style = "distributed" *) logic [7:0] mem [0:31];
  initial for (int i = 0; i < 32; i++) mem[i] = INITV ? 8'(8'hC0 + i) : 8'h00;
  always_ff @(posedge clk) if (we) mem[a] <= wd;
  assign rq = mem[a];
  (* shreg_extract = "yes" *) logic [15:0] sr = INITV ? 16'hBEEF : 16'h0;
  always_ff @(posedge clk) sr <= {sr[14:0], sin};
  assign sout = sr[15];
endmodule

// X11: UltraRAM (ram_style ultra), 4096 x 72, array initialised non-zero when INITV, output register initial INITV pattern.
module x11_uram #(parameter bit INITV = 1'b1)
  (input logic clk, we, input logic [11:0] wa, ra, input logic [71:0] wd, output logic [71:0] q);
  (* ram_style = "ultra" *) logic [71:0] mem [0:4095];
  initial if (INITV) for (int i = 0; i < 4096; i++) mem[i] = 72'h55_0000_0000_0000_0000 + i;
  logic [71:0] rd = INITV ? {72{1'b1}} : '0, oq = INITV ? {72{1'b1}} : '0;
  always_ff @(posedge clk) begin
    if (we) mem[wa] <= wd;
    rd <= mem[ra];
    oq <= rd;
  end
  assign q = oq;
endmodule

// ---- follow-up arms (amendment 2026-11-24, after X8/X9) ----
// X8b: only the P register non-zero; X8c: only the A/B input registers non-zero (INITV=1); INITV=0 is the all-zero baseline.
module x8b_dsp_p #(parameter bit INITV = 1'b1) (input logic clk, input logic signed [17:0] a, b, output logic signed [35:0] p);
  logic signed [17:0] ar = '0, br = '0;
  logic signed [35:0] mr = '0, pr = {36{INITV}};
  always_ff @(posedge clk) begin ar <= a; br <= b; mr <= ar * br; pr <= mr; end
  assign p = pr;
endmodule
module x8c_dsp_ab #(parameter bit INITV = 1'b1) (input logic clk, input logic signed [17:0] a, b, output logic signed [35:0] p);
  logic signed [17:0] ar = {18{INITV}}, br = {18{INITV}};
  logic signed [35:0] mr = '0, pr = '0;
  always_ff @(posedge clk) begin ar <= a; br <= b; mr <= ar * br; pr <= mr; end
  assign p = pr;
endmodule
// X9b: read and output registers with the same non-zero value; X9c: only the output register non-zero.
module x9bc_bram #(parameter bit INITV = 1'b1, parameter bit SAME = 1'b1)
  (input logic clk, we, input logic [9:0] wa, ra, input logic [31:0] wd, output logic [31:0] q);
  (* ram_style = "block" *) logic [31:0] mem [0:1023];
  initial for (int i = 0; i < 1024; i++) mem[i] = 32'h1000_0000 + i;
  logic [31:0] rd = (INITV && SAME) ? 32'h3C3C_F0F0 : 32'h0, oq = INITV ? 32'h3C3C_F0F0 : 32'h0;
  always_ff @(posedge clk) begin
    if (we) mem[wa] <= wd;
    rd <= mem[ra];
    oq <= rd;
  end
  assign q = oq;
endmodule
