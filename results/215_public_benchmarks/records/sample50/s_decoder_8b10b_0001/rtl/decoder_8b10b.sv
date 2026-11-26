// 8b10b control-symbol decoder: 24 valid K codewords, everything else 0/0.
// Outputs are registered (latency 1 clk_in cycle). reset_in clears the
// outputs without a clock edge (REQ-09/10): the registers take a synchronous
// reset and the outputs are gated by reset_in, so no reset is in a
// sensitivity list.
module decoder_8b10b (
  input  wire       clk_in,
  input  wire       reset_in,
  input  wire [9:0] decoder_in,
  output wire [7:0] decoder_out,
  output wire       control_out
);

  logic [7:0] dec_val;
  logic       dec_ctl;
  logic [7:0] val_q;
  logic       ctl_q;

  always_comb begin
    dec_val = 8'h00;
    dec_ctl = 1'b1;
    case (decoder_in)
      // K.28.0 - K.28.7, RD- (abcdei = 001111)
      10'b0011110100: dec_val = 8'h1C;
      10'b0011111001: dec_val = 8'h3C;
      10'b0011110101: dec_val = 8'h5C;
      10'b0011110011: dec_val = 8'h7C;
      10'b0011110010: dec_val = 8'h9C;
      10'b0011111010: dec_val = 8'hBC;
      10'b0011110110: dec_val = 8'hDC;
      10'b0011111000: dec_val = 8'hFC;
      // K.28.0 - K.28.7, RD+ (abcdei = 110000)
      10'b1100001011: dec_val = 8'h1C;
      10'b1100000110: dec_val = 8'h3C;
      10'b1100001010: dec_val = 8'h5C;
      10'b1100001100: dec_val = 8'h7C;
      10'b1100001101: dec_val = 8'h9C;
      10'b1100000101: dec_val = 8'hBC;
      10'b1100001001: dec_val = 8'hDC;
      10'b1100000111: dec_val = 8'hFC;
      // K.23.7, K.27.7, K.29.7, K.30.7 (RD-)
      10'b1110101000: dec_val = 8'hF7;
      10'b1101101000: dec_val = 8'hFB;
      10'b1011101000: dec_val = 8'hFD;
      10'b0111101000: dec_val = 8'hFE;
      // same, RD+
      10'b0001010111: dec_val = 8'hF7;
      10'b0010010111: dec_val = 8'hFB;
      10'b0100010111: dec_val = 8'hFD;
      10'b1000010111: dec_val = 8'hFE;
      default: dec_ctl = 1'b0;
    endcase
  end

  always_ff @(posedge clk_in) begin
    if (reset_in) begin
      val_q <= 8'h00;
      ctl_q <= 1'b0;
    end else begin
      val_q <= dec_val;
      ctl_q <= dec_ctl;
    end
  end

  assign decoder_out = reset_in ? 8'h00 : val_q;
  assign control_out = reset_in ? 1'b0  : ctl_q;

endmodule
