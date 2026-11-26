// Real/complex dot-product accumulator. One clock domain (clk_in).
// reset_in is active high. Registers use a synchronous reset; the outputs are
// additionally gated combinationally by reset_in so they clear asynchronously
// (REQ-10) without reset in a sensitivity list. Datapath registers are not reset.
module dot_product (
    input  logic        clk_in,
    input  logic        reset_in,
    input  logic        start_in,
    input  logic [7:0]  dot_length_in,
    input  logic [31:0] vector_a_in,
    input  logic        vector_a_valid_in,
    input  logic [31:0] vector_b_in,
    input  logic        vector_b_valid_in,
    input  logic        a_complex_in,
    input  logic        b_complex_in,
    output logic [31:0] dot_product_out,
    output logic        dot_product_valid_out,
    output logic        dot_product_error_out
);

  typedef enum logic [1:0] {
    IDLE    = 2'd0,
    COMPUTE = 2'd1,
    OUTPUT  = 2'd2,
    ERROR   = 2'd3
  } state_t;

  state_t state;

  // input registers (one clock before use)
  logic        start_r, av_r, bv_r;       // control: reset
  logic [7:0]  n_r;
  logic [31:0] a_r, b_r;
  logic        ac_r, bc_r;

  always_ff @(posedge clk_in) begin
    n_r  <= dot_length_in;
    a_r  <= vector_a_in;
    b_r  <= vector_b_in;
    ac_r <= a_complex_in;
    bc_r <= b_complex_in;
  end

  always_ff @(posedge clk_in) begin
    if (reset_in) begin
      start_r <= 1'b0;
      av_r    <= 1'b0;
      bv_r    <= 1'b0;
    end else begin
      start_r <= start_in;
      av_r    <= vector_a_valid_in;
      bv_r    <= vector_b_valid_in;
    end
  end

  // products (signed 16x16)
  logic signed [15:0] a_re, a_im, b_re, b_im;
  assign a_re = a_r[15:0];
  assign a_im = a_r[31:16];
  assign b_re = b_r[15:0];
  assign b_im = b_r[31:16];

  logic signed [31:0] p_rr, p_ii, p_ri, p_ir;
  assign p_rr = a_re * b_re;
  assign p_ii = a_im * b_im;
  assign p_ri = a_re * b_im;
  assign p_ir = a_im * b_re;

  // mode captured at start
  logic        mode_ac, mode_bc;
  logic [8:0]  length;
  logic [8:0]  cnt;
  logic signed [31:0] acc_re, acc_im;

  logic accept;
  assign accept = (state == COMPUTE) && av_r && bv_r;

  always_ff @(posedge clk_in) begin
    if (state == IDLE && start_r) begin
      acc_re  <= 32'sd0;
      acc_im  <= 32'sd0;
      mode_ac <= ac_r;
      mode_bc <= bc_r;
      length  <= (n_r == 8'd0) ? 9'd256 : {1'b0, n_r};
    end else if (accept) begin
      acc_re <= acc_re + p_rr - ((mode_ac && mode_bc) ? p_ii : 32'sd0);
      acc_im <= acc_im + (mode_bc ? p_ri : 32'sd0) + (mode_ac ? p_ir : 32'sd0);
    end
  end

  logic [31:0] out_q;
  logic        valid_q, err_q;

  always_ff @(posedge clk_in) begin
    if (reset_in) begin
      state   <= IDLE;
      cnt     <= 9'd0;
      out_q   <= 32'd0;
      valid_q <= 1'b0;
      err_q   <= 1'b0;
    end else begin
      out_q   <= 32'd0;
      valid_q <= 1'b0;
      err_q   <= 1'b0;
      case (state)
        IDLE: begin
          if (start_r) begin
            cnt   <= 9'd0;
            state <= COMPUTE;
          end
        end
        COMPUTE: begin
          if (!(av_r && bv_r)) begin
            state <= ERROR;
          end else begin
            cnt <= cnt + 9'd1;
            if ((cnt + 9'd1) >= length) state <= OUTPUT;
          end
        end
        OUTPUT: begin
          out_q   <= (mode_ac || mode_bc) ? {acc_im[15:0], acc_re[15:0]} : acc_re;
          valid_q <= 1'b1;
          state   <= IDLE;
        end
        ERROR: begin
          err_q <= 1'b1;
          state <= IDLE;
        end
        default: state <= IDLE;
      endcase
    end
  end

  assign dot_product_out       = reset_in ? 32'd0 : out_q;
  assign dot_product_valid_out = reset_in ? 1'b0 : valid_q;
  assign dot_product_error_out = reset_in ? 1'b0 : err_q;

endmodule
