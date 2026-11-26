// Two-master FSM bus arbiter, req2 has priority.
// Reset: registers clear synchronously; state and grants are also forced
// to IDLE/0 combinationally while reset is high, so the reset takes effect
// without a clk edge (spec) with no reset in a sensitivity list (STD-RST-01).
// Waiver: the spec fixes the deliverable file name, which differs from the module name.
/* verilator lint_off DECLFILENAME */
module bus_arbiter #(
    parameter int STATE_WIDTH = 3,
    parameter logic [STATE_WIDTH-1:0] IDLE    = 0,
    parameter logic [STATE_WIDTH-1:0] GRANT_1 = 1,
    parameter logic [STATE_WIDTH-1:0] GRANT_2 = 2,
    parameter logic [STATE_WIDTH-1:0] CLEAR   = 3
) (
    input  logic reset,
    input  logic clk,
    input  logic req1,
    input  logic req2,
    output logic grant1,
    output logic grant2
);

  logic [STATE_WIDTH-1:0] state_q, state, next_state;
  logic grant1_q, grant2_q;

  assign state  = reset ? IDLE : state_q;
  assign grant1 = grant1_q & ~reset;
  assign grant2 = grant2_q & ~reset;

  always_comb begin
    next_state = IDLE;
    if (state == IDLE || state == CLEAR) begin
      if (req2) next_state = GRANT_2;
      else if (req1) next_state = GRANT_1;
      else next_state = IDLE;
    end else if (state == GRANT_1) begin
      if (req2) next_state = GRANT_2;
      else if (!req1) next_state = CLEAR;
      else next_state = GRANT_1;
    end else if (state == GRANT_2) begin
      next_state = req2 ? GRANT_2 : CLEAR;
    end
  end

  always_ff @(posedge clk) begin
    if (reset) begin
      state_q  <= IDLE;
      grant1_q <= 1'b0;
      grant2_q <= 1'b0;
    end else begin
      state_q  <= next_state;
      grant1_q <= (next_state == GRANT_1);
      grant2_q <= (next_state == GRANT_2);
    end
  end

endmodule
/* verilator lint_on DECLFILENAME */
