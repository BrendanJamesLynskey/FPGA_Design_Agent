// 64b/66b decoder, one registered stage, valid acts as clock enable.
// Registers use a synchronous reset; rst_in also gates the outputs
// combinationally so the outputs clear asynchronously as the spec requires.
module decoder_64b66b #(
    /* verilator lint_off UNUSEDPARAM */
    parameter int LATENCY_CYCLES = 1  // fixed 1-cycle latency; kept for interface compatibility
    /* verilator lint_on UNUSEDPARAM */
) (
    input  logic        clk_in,
    input  logic        rst_in,
    input  logic        decoder_data_valid_in,
    input  logic [65:0] decoder_data_in,
    output logic [63:0] decoder_data_out,
    output logic [7:0]  decoder_control_out,
    output logic        sync_error,
    output logic        decoder_error_out
);

  localparam logic [7:0] I = 8'h07;
  localparam logic [7:0] S = 8'hFB;
  localparam logic [7:0] T = 8'hFD;
  localparam logic [7:0] E = 8'hFE;
  localparam logic [7:0] Q = 8'h9C;

  logic [1:0]  sh;
  logic [7:0]  ty;
  logic [55:0] da;
  logic [7:0]  d0, d1, d2, d3, d4, d5, d6;

  logic [63:0] n_data;
  logic [7:0]  n_ctrl;
  logic        n_serr;
  logic        n_derr;

  logic [63:0] r_data;
  logic [7:0]  r_ctrl;
  logic        r_serr;
  logic        r_derr;

  assign sh = decoder_data_in[65:64];
  assign ty = decoder_data_in[63:56];
  assign da = decoder_data_in[55:0];
  assign d0 = da[7:0];
  assign d1 = da[15:8];
  assign d2 = da[23:16];
  assign d3 = da[31:24];
  assign d4 = da[39:32];
  assign d5 = da[47:40];
  assign d6 = da[55:48];

  always_comb begin
    n_data = 64'h0;
    n_ctrl = 8'h00;
    n_serr = 1'b0;
    n_derr = 1'b0;
    case (sh)
      2'b01: n_data = decoder_data_in[63:0];
      2'b10: begin
        case (ty)
          8'h1E: begin n_ctrl = 8'hFF; n_data = {E, E, E, E, E, E, E, E}; end
          8'h33: begin n_ctrl = 8'h1F; n_data = {d6, d5, d4, S, I, I, I, I}; end
          8'h78: begin n_ctrl = 8'h01; n_data = {d6, d5, d4, d3, d2, d1, d0, S}; end
          8'h87: begin n_ctrl = 8'hFE; n_data = {I, I, I, I, I, I, I, T}; end
          8'h99: begin n_ctrl = 8'hFE; n_data = {I, I, I, I, I, I, T, d0}; end
          8'hAA: begin n_ctrl = 8'hFC; n_data = {I, I, I, I, I, T, d1, d0}; end
          8'hB4: begin n_ctrl = 8'hF8; n_data = {I, I, I, I, T, d2, d1, d0}; end
          8'hCC: begin n_ctrl = 8'hF0; n_data = {I, I, I, T, d3, d2, d1, d0}; end
          8'hD2: begin n_ctrl = 8'hE0; n_data = {I, I, T, d4, d3, d2, d1, d0}; end
          8'hE1: begin n_ctrl = 8'hC0; n_data = {I, T, d5, d4, d3, d2, d1, d0}; end
          8'hFF: begin n_ctrl = 8'h80; n_data = {T, d6, d5, d4, d3, d2, d1, d0}; end
          8'h2D: begin n_ctrl = 8'h1F; n_data = {d6, d5, d4, Q, I, I, I, I}; end
          8'h4B: begin n_ctrl = 8'hF1; n_data = {I, I, I, I, d2, d1, d0, Q}; end
          8'h55: begin n_ctrl = 8'h11; n_data = {d6, d5, d4, Q, d2, d1, d0, Q}; end
          8'h66: begin n_ctrl = 8'h11; n_data = {d6, d5, d4, S, d2, d1, d0, Q}; end
          default: n_derr = 1'b1;
        endcase
      end
      default: n_serr = 1'b1;
    endcase
  end

  always_ff @(posedge clk_in) begin
    if (rst_in) begin
      r_data <= 64'h0;
      r_ctrl <= 8'h00;
      r_serr <= 1'b0;
      r_derr <= 1'b0;
    end else if (decoder_data_valid_in) begin
      r_data <= n_data;
      r_ctrl <= n_ctrl;
      r_serr <= n_serr;
      r_derr <= n_derr;
    end
  end

  assign decoder_data_out    = rst_in ? 64'h0 : r_data;
  assign decoder_control_out = rst_in ? 8'h00 : r_ctrl;
  assign sync_error          = rst_in ? 1'b0 : r_serr;
  assign decoder_error_out   = rst_in ? 1'b0 : r_derr;

endmodule
