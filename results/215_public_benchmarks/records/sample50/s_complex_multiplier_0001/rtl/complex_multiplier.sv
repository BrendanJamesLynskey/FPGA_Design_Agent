// Complex multiplier: signed 16-bit operands, 32-bit wrapped results,
// one-cycle latency, one result per cycle. The registers use a synchronous
// clear; the outputs are also gated by arst_n so they read 0 as soon as
// arst_n falls, without a clock edge (spec REQ-04).
module complex_multiplier (
    input  logic               clk,
    input  logic               arst_n,
    input  logic signed [15:0] a_real,
    input  logic signed [15:0] a_imag,
    input  logic signed [15:0] b_real,
    input  logic signed [15:0] b_imag,
    output logic        [31:0] result_real,
    output logic        [31:0] result_imag
);

  logic signed [31:0] p_rr, p_ii, p_ri, p_ir;
  logic        [31:0] q_real, q_imag;

  assign p_rr = a_real * b_real;
  assign p_ii = a_imag * b_imag;
  assign p_ri = a_real * b_imag;
  assign p_ir = a_imag * b_real;

  always_ff @(posedge clk) begin
    if (!arst_n) begin
      q_real <= 32'd0;
      q_imag <= 32'd0;
    end else begin
      q_real <= 32'(p_rr - p_ii);
      q_imag <= 32'(p_ri + p_ir);
    end
  end

  assign result_real = arst_n ? q_real : 32'd0;
  assign result_imag = arst_n ? q_imag : 32'd0;

endmodule
