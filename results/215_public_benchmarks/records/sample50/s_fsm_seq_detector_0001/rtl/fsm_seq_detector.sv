// Overlapping serial sequence detector for 10110001, registered one-cycle pulse.
/* verilator lint_off UNUSEDPARAM */
module fsm_seq_detector #(
    parameter int SEQ_LEN     = 8,
    parameter int STATE_WIDTH = 3
) (
    input  logic clk_in,
    input  logic rst_in,   // active high, asynchronous assert per spec
    input  logic seq_in,
    output logic seq_detected
);
/* verilator lint_on UNUSEDPARAM */

  typedef enum logic [2:0] {
    S0 = 3'd0,
    S1 = 3'd1,
    S2 = 3'd2,
    S3 = 3'd3,
    S4 = 3'd4,
    S5 = 3'd5,
    S6 = 3'd6,
    S7 = 3'd7
  } state_t;

  state_t cur_state, next_state;
  logic seq_detected_w;

  always_comb begin
    next_state = S0;
    case (cur_state)
      S0: if (seq_in) next_state = S1; else next_state = S0;
      S1: if (seq_in) next_state = S1; else next_state = S2;
      S2: if (seq_in) next_state = S3; else next_state = S0;
      S3: if (seq_in) next_state = S4; else next_state = S2;
      S4: if (seq_in) next_state = S1; else next_state = S5;
      S5: if (seq_in) next_state = S3; else next_state = S6;
      S6: if (seq_in) next_state = S1; else next_state = S7;
      S7: if (seq_in) next_state = S1; else next_state = S0;
      default: next_state = S0;
    endcase
  end

  assign seq_detected_w = (cur_state == S7) && seq_in;

  // Spec mandates asynchronous reset assert (REQ-05, REQ-06).
  always_ff @(posedge clk_in or posedge rst_in) begin
    if (rst_in) begin
      cur_state    <= S0;
      seq_detected <= 1'b0;
    end else begin
      cur_state    <= next_state;
      seq_detected <= seq_detected_w;
    end
  end

endmodule
