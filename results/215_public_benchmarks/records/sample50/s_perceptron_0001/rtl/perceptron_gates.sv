// Microcoded perceptron trainer for AND/OR/NAND/NOR gates.
// Reset (rst_n, active low) asserts asynchronously as far as the outputs go:
// present_addr reads 0 as soon as rst_n is low (REQ-01). The registers are
// reset synchronously; a reset pulse that falls between clock edges is
// remembered in `pend` (the only flop with rst_n in its sensitivity list) and
// the next clock edge runs from the reset state (address 0).
/* verilator lint_off DECLFILENAME */
/* verilator lint_off SYNCASYNCNET */
module gate_target (
    input  logic [1:0]        gate_select,
    input  logic [1:0]        input_index,
    output logic signed [3:0] target
);
  always_comb begin
    case (gate_select)
      2'b00, 2'b11: target = (input_index == 2'd0) ? 4'sd1 : -4'sd1;
      default:      target = (input_index == 2'd3) ? -4'sd1 : 4'sd1;
    endcase
  end
endmodule

module perceptron_gates (
    input  logic              clk,
    input  logic              rst_n,
    input  logic signed [3:0] x1,
    input  logic signed [3:0] x2,
    input  logic              learning_rate,
    input  logic signed [3:0] threshold,
    input  logic [1:0]        gate_select,
    output logic signed [3:0] percep_w1,
    output logic signed [3:0] percep_w2,
    output logic signed [3:0] percep_bias,
    output logic [3:0]        present_addr,
    output logic              stop,
    output logic [2:0]        input_index,
    output logic signed [3:0] y_in,
    output logic signed [3:0] y,
    output logic signed [3:0] prev_percep_wt_1,
    output logic signed [3:0] prev_percep_wt_2,
    output logic signed [3:0] prev_percep_bias
);
  logic signed [3:0] target_c;
  logic signed [3:0] target_q;
  logic signed [3:0] u1, u2, ub;
  logic        [3:0] addr_q;
  logic              pend;

  // pending reset: set when rst_n falls, cleared by the first clock edge with rst_n high
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) pend <= 1'b1;
    else        pend <= 1'b0;
  end

  assign present_addr = rst_n ? addr_q : 4'd0;

  // address the microcode runs from at this edge
  logic [3:0] eff_addr;
  assign eff_addr = pend ? 4'd0 : addr_q;

  gate_target u_gt (
      .gate_select(gate_select),
      .input_index(input_index[1:0]),
      .target(target_c)
  );

  // y_in = bias + x1*w1 + x2*w2 (4-bit wrap)
  logic signed [3:0] p1, p2;
  logic signed [3:0] yin_c;
  assign p1    = 4'(x1 * percep_w1);
  assign p2    = 4'(x2 * percep_w2);
  assign yin_c = percep_bias + p1 + p2;

  logic signed [4:0] th_pos, th_neg, yin_ext;
  assign th_pos  = {threshold[3], threshold};
  assign th_neg  = -th_pos;
  assign yin_ext = {yin_c[3], yin_c};

  logic signed [3:0] y_c;
  always_comb begin
    if (yin_ext > th_pos) y_c = 4'sd1;
    else if (yin_ext < th_neg) y_c = -4'sd1;
    else y_c = 4'sd0;
  end

  // updates
  logic signed [3:0] nu1, nu2, nub;
  always_comb begin
    if (y != target_q) begin
      nu1 = learning_rate ? 4'(x1 * target_q) : 4'sd0;
      nu2 = learning_rate ? 4'(x2 * target_q) : 4'sd0;
      nub = learning_rate ? target_q : 4'sd0;
    end else begin
      nu1 = 4'sd0;
      nu2 = 4'sd0;
      nub = 4'sd0;
    end
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      addr_q           <= 4'd0;
      percep_w1        <= 4'sd0;
      percep_w2        <= 4'sd0;
      percep_bias      <= 4'sd0;
      input_index      <= 3'd0;
      prev_percep_wt_1 <= 4'sd0;
      prev_percep_wt_2 <= 4'sd0;
      prev_percep_bias <= 4'sd0;
      stop             <= 1'b0;
      y_in             <= 4'sd0;
      y                <= 4'sd0;
      target_q         <= 4'sd0;
      u1               <= 4'sd0;
      u2               <= 4'sd0;
      ub               <= 4'sd0;
    end else begin
      addr_q <= (eff_addr >= 4'd5) ? 4'd1 : eff_addr + 4'd1;
      case (eff_addr)
        4'd0: begin
          percep_w1        <= 4'sd0;
          percep_w2        <= 4'sd0;
          percep_bias      <= 4'sd0;
          input_index      <= 3'd0;
          prev_percep_wt_1 <= 4'sd0;
          prev_percep_wt_2 <= 4'sd0;
          prev_percep_bias <= 4'sd0;
          stop             <= 1'b0;
          u1               <= 4'sd0;
          u2               <= 4'sd0;
          ub               <= 4'sd0;
        end
        4'd1: begin
          y_in <= yin_c;
          y    <= y_c;
        end
        4'd2: target_q <= target_c;
        4'd3: begin
          if (!stop) begin
            u1          <= nu1;
            u2          <= nu2;
            ub          <= nub;
            percep_w1   <= percep_w1 + nu1;
            percep_w2   <= percep_w2 + nu2;
            percep_bias <= percep_bias + nub;
          end
        end
        4'd4: begin
          if (!stop) begin
            if (u1 == prev_percep_wt_1 && u2 == prev_percep_wt_2 && ub == prev_percep_bias)
              stop <= 1'b1;
            else begin
              prev_percep_wt_1 <= u1;
              prev_percep_wt_2 <= u2;
              prev_percep_bias <= ub;
            end
          end
        end
        4'd5: input_index <= {1'b0, input_index[1:0] + 2'd1};
        default: ;
      endcase
    end
  end
endmodule
/* verilator lint_on SYNCASYNCNET */
/* verilator lint_on DECLFILENAME */
