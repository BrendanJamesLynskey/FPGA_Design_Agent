// Brief 206: Altera power-up value arms, all in one top so one compile per family and INITV measures them together.
// Each arm has its own clock, so the Timing Analyzer reports an Fmax per arm. Ports other than the Q5 I/O arm and the
// clocks are virtual pins (q_project.tcl), so the arms are not limited by the package and see no I/O timing.
// INITV = 0 or 1 is the power-up value written as a declaration initialiser (Quartus reads it as Power-Up Level).

// Q1: plain register, output straight to a port
module q1_plain #(parameter bit INITV = 1'b1) (input logic clk, input logic [7:0] d, output logic [7:0] q);
  logic [7:0] r = {8{INITV}};
  always_ff @(posedge clk) r <= d;
  assign q = r;
endmodule

// Q2: synchronous reset to 0, power-up INITV
module q2_sreset0 #(parameter bit INITV = 1'b1) (input logic clk, rst, input logic [7:0] d, output logic [7:0] q);
  logic [7:0] r = {8{INITV}};
  always_ff @(posedge clk) if (rst) r <= '0; else r <= d;
  assign q = r;
endmodule

// Q3: asynchronous clear, power-up INITV
module q3_aclr #(parameter bit INITV = 1'b1) (input logic clk, rst, input logic [7:0] d, output logic [7:0] q);
  logic [7:0] r = {8{INITV}};
  always_ff @(posedge clk or posedge rst) if (rst) r <= '0; else r <= d;
  assign q = r;
endmodule

// Q4: asynchronous preset, power-up INITV (INITV=1 agrees with the preset, INITV=0 conflicts with it)
module q4_apre #(parameter bit INITV = 1'b1) (input logic clk, rst, input logic [7:0] d, output logic [7:0] q);
  logic [7:0] r = {8{INITV}};
  always_ff @(posedge clk or posedge rst) if (rst) r <= '1; else r <= d;
  assign q = r;
endmodule

// Q5: I/O registers (fast input and output register assignments in q_project.tcl), power-up INITV
module q5_io #(parameter bit INITV = 1'b1) (input logic clk, input logic [3:0] din, output logic [3:0] dout);
  logic [3:0] ireg = {4{INITV}}, oreg = {4{INITV}};
  always_ff @(posedge clk) begin ireg <= din; oreg <= ireg ^ {ireg[2:0], ireg[3]}; end
  assign dout = oreg;
endmodule

// Q6a: registers feeding a multiplier (input registers) and after it, power-up INITV (all ones)
module q6_mult #(parameter bit INITV = 1'b1) (input logic clk, input logic signed [17:0] a, b, output logic signed [35:0] p);
  logic signed [17:0] ar = {18{INITV}}, br = {18{INITV}};
  logic signed [35:0] pr = {36{INITV}};
  always_ff @(posedge clk) begin ar <= a; br <= b; pr <= ar * br; end
  assign p = pr;
endmodule

// Q6b: registers feeding a block RAM's write port, and the RAM's registered read output, power-up INITV
module q6_ram #(parameter bit INITV = 1'b1)
  (input logic clk, we, input logic [7:0] wa, ra, input logic [15:0] wd, output logic [15:0] q);
  (* ramstyle = "M9K, M10K, no_rw_check" *) logic [15:0] mem [0:255];
  logic        wer = INITV;
  logic [7:0]  war = {8{INITV}};
  logic [15:0] wdr = {16{INITV}};
  logic [15:0] rd  = {16{INITV}};
  always_ff @(posedge clk) begin
    wer <= we; war <= wa; wdr <= wd;
    if (wer) mem[war] <= wdr;
    rd <= mem[ra];
  end
  assign q = rd;
endmodule

// Q7: 64-bit register-to-register pipeline, three stages, no logic between, power-up INITV on every bit
module q7_pipe64 #(parameter bit INITV = 1'b1) (input logic clk, input logic [63:0] d, output logic [63:0] q);
  logic [63:0] s0 = {64{INITV}}, s1 = {64{INITV}}, s2 = {64{INITV}};
  always_ff @(posedge clk) begin s0 <= d; s1 <= s0; s2 <= s1; end
  assign q = s2;
endmodule

// Q8: 64-bit pipeline with a 4-input function between the stages (an inverter can fold into it), power-up INITV
module q8_logic64 #(parameter bit INITV = 1'b1) (input logic clk, input logic [63:0] d, output logic [63:0] q);
  logic [63:0] s0 = {64{INITV}}, s1 = {64{INITV}}, s2 = {64{INITV}};
  logic [63:0] f0, f1;
  always_comb for (int i = 0; i < 64; i++) begin
    f0[i] = (s0[i] ^ s0[(i+1)%64]) & s0[(i+2)%64] | s0[(i+3)%64];
    f1[i] = (s1[i] ^ s1[(i+5)%64]) & s1[(i+7)%64] | s1[(i+11)%64];
  end
  always_ff @(posedge clk) begin s0 <= d; s1 <= f0; s2 <= f1; end
  assign q = s2;
endmodule

module q_top #(parameter bit INITV = 1'b1) (
  input  logic        clk1, clk2, clk3, clk4, clk5, clk6, clk7, clk8, clk9, clk10,
  input  logic        rst,
  input  logic [7:0]  d1, d2, d3, d4,
  output logic [7:0]  q1, q2, q3, q4,
  input  logic [3:0]  io_din,
  output logic [3:0]  io_dout,
  input  logic signed [17:0] ma, mb,
  output logic signed [35:0] mp,
  input  logic        rwe, input logic [7:0] rwa, rra, input logic [15:0] rwd, output logic [15:0] rq,
  input  logic [63:0] d7, d8,
  output logic [63:0] q7, q8,
  input  logic        inc9, output logic [3:0] q9
);
  q1_plain   #(INITV) u_q1 (.clk(clk1), .d(d1), .q(q1));
  q2_sreset0 #(INITV) u_q2 (.clk(clk2), .rst, .d(d2), .q(q2));
  q3_aclr    #(INITV) u_q3 (.clk(clk3), .rst, .d(d3), .q(q3));
  q4_apre    #(INITV) u_q4 (.clk(clk4), .rst, .d(d4), .q(q4));
  q5_io      #(INITV) u_q5 (.clk(clk5), .din(io_din), .dout(io_dout));
  q6_mult    #(INITV) u_q6m (.clk(clk6), .a(ma), .b(mb), .p(mp));
  q6_ram     #(INITV) u_q6r (.clk(clk10), .we(rwe), .wa(rwa), .ra(rra), .wd(rwd), .q(rq));
  q7_pipe64  #(INITV) u_q7 (.clk(clk7), .d(d7), .q(q7));
  q8_logic64 #(INITV) u_q8 (.clk(clk8), .d(d8), .q(q8));
  x12_vhdl_int        u_q9 (.clk(clk9), .inc(inc9), .q(q9));
endmodule
