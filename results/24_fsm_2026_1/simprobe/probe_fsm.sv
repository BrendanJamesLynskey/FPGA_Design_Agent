// Probe FSM for the simulator coverage survey (brief 24): 4 states, one legal transition never taken by the bench.
module probe_fsm (input logic clk, input logic rst_n, input logic go, input logic fin, output logic busy);
  typedef enum logic [1:0] {IDLE, RUN, DONE, ERR} st_t;
  st_t state_q, state_d;
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) state_q <= IDLE; else state_q <= state_d;
  always_comb begin
    state_d = state_q;
    case (state_q)
      IDLE: if (go) state_d = RUN;
      RUN:  if (fin) state_d = DONE; else if (go) state_d = ERR;
      DONE: state_d = IDLE;
      ERR:  state_d = IDLE;
      default: state_d = IDLE;
    endcase
  end
  assign busy = (state_q == RUN);

  // user coverage, as each simulator may accept it
`ifdef WITH_COVERGROUP
  covergroup cg @(posedge clk);
    cp_state: coverpoint state_q;
  endgroup
  cg cg_i = new();
`endif
`ifdef WITH_COVERPROP
  C_run_done: cover property (@(posedge clk) disable iff (!rst_n) state_q == RUN ##1 state_q == DONE);
  C_idle_run: cover property (@(posedge clk) disable iff (!rst_n) state_q == IDLE ##1 state_q == RUN);
  C_run_err:  cover property (@(posedge clk) disable iff (!rst_n) state_q == RUN ##1 state_q == ERR);
`endif
`ifdef WITH_COVERPROP_IMPL
  C_run_done: cover property (@(posedge clk) disable iff (!rst_n) state_q == RUN && fin |=> state_q == DONE);
  C_idle_run: cover property (@(posedge clk) disable iff (!rst_n) state_q == IDLE && go |=> state_q == RUN);
  C_run_err:  cover property (@(posedge clk) disable iff (!rst_n) state_q == RUN && go && !fin |=> state_q == ERR);
`endif
endmodule
