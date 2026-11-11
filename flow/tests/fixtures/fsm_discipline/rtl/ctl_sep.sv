// Reference burst controller, control separated from the counter (brief 24).
//   IDLE -> LOAD -> REQ (wait gnt) -> ADDR -> DATA x4 -> TURN -> WACK (ack | nack | 8-cycle timeout)
//   ack -> RESP, nack -> RETRY -> REQ, timeout -> ERR; RESP/ERR wait rsp_ready -> COOL x3 -> IDLE.
// 11 states and one 4-bit counter the FSM loads (ld/ldv) and runs (en); the FSM reads only the zero flag.
// Handshakes: cmd_valid/cmd_ready in, rsp_valid/rsp_ready out. Bus side: bus_req/gnt, ack/nack.
//   OUT: 0 combinational Moore decode of the state (cmd_ack is Mealy: state and cmd_valid),
//        1 registered decode of the state (one cycle later), 2 lookahead: registered decode of the NEXT state (no added latency,
//        cmd_ack comes one cycle later: a Mealy output cannot be registered ahead of its input)
//   ZREG: 1 registers the counter's zero flag (computed from the next count)
//   IN, RST: fsm_front.sv. USE_CE: the FSM and the counter advance only on `ce` (the slow-FSM pattern of brief 20).
module ctl_sep #(parameter int OUT = 0, parameter int IN = 0, parameter int RST = 0, parameter int ZREG = 0,
                 parameter int USE_CE = 0) (
  input  logic clk, input logic rst_n, input logic ce,
  input  logic cmd_valid, output logic cmd_ready, output logic cmd_ack,
  input  logic gnt, input logic ack, input logic nack,
  output logic bus_req, output logic bus_addr_v, output logic bus_valid, output logic bus_last,
  output logic rsp_valid, output logic rsp_err, input logic rsp_ready
);
  typedef enum logic [3:0] {IDLE, LOAD, REQ, ADDR, DATA, TURN, WACK, RETRY, RESP, ERR, COOL} st_t;
  st_t st = IDLE, d;
  logic cmd_valid_i, gnt_i, ack_i, nack_i, rsp_ready_i;
  fsm_in #(IN) u_i0 (clk, cmd_valid, cmd_valid_i);
  fsm_in #(IN) u_i1 (clk, gnt, gnt_i);
  fsm_in #(IN) u_i2 (clk, ack, ack_i);
  fsm_in #(IN) u_i3 (clk, nack, nack_i);
  fsm_in #(IN) u_i4 (clk, rsp_ready, rsp_ready_i);
  wire cen = (USE_CE != 0) ? ce : 1'b1;

  // ---- counter: loaded and run by the FSM, not part of it
  logic [3:0] cnt = 4'd0, cnt_d, ldv;
  logic       ld, en, zero, zero_d;
  assign cnt_d  = ld ? ldv : (en ? cnt - 4'd1 : cnt);
  assign zero_d = (cnt_d == 4'd0);
  always_ff @(posedge clk) if (cen) cnt <= cnt_d;
  generate
    if (ZREG != 0) begin : g_zq
      logic zq = 1'b1;                                   // cnt starts at 0
      always_ff @(posedge clk) if (cen) zq <= zero_d;
      assign zero = zq;
    end else begin : g_zc
      assign zero = (cnt == 4'd0);
    end
  endgenerate

`ifdef FORMAL_INV
  // the counter's range in the states that use it (the invariant an induction proof needs when the count lives outside the FSM)
  always @(posedge clk) begin
    if (st == DATA) assert (cnt <= 4'd3);
    if (st == WACK) assert (cnt <= 4'd7);
    if (st == COOL) assert (cnt <= 4'd2);
  end
`endif

  // ---- next state (the only place the transitions live)
  always_comb begin
    d = st; ld = 1'b0; en = 1'b0; ldv = 4'd0;
    case (st)
      IDLE:  if (cmd_valid_i) d = LOAD;
      LOAD:  d = REQ;
      REQ:   if (gnt_i) d = ADDR;
      ADDR:  begin d = DATA; ld = 1'b1; ldv = 4'd3; end
      DATA:  if (zero) d = TURN; else en = 1'b1;
      TURN:  begin d = WACK; ld = 1'b1; ldv = 4'd7; end
      WACK:  if (ack_i) d = RESP; else if (nack_i) d = RETRY; else if (zero) d = ERR; else en = 1'b1;
      RETRY: d = REQ;
      RESP:  if (rsp_ready_i) begin d = COOL; ld = 1'b1; ldv = 4'd2; end
      ERR:   if (rsp_ready_i) begin d = COOL; ld = 1'b1; ldv = 4'd2; end
      COOL:  if (zero) d = IDLE; else en = 1'b1;
      default: d = IDLE;
    endcase
  end

  // the state register, in the reset style RST (0 async, 1 sync over enable, 2 none, 3 async assert/sync release, 4 sync gated by the enable)
  logic arst_n;
  fsm_arst #(RST) u_arst (.clk, .rst_n, .a_n(arst_n));
  generate
    if (RST == 0 || RST == 3) begin : g_st_async
      always_ff @(posedge clk or negedge arst_n) if (!arst_n) st <= IDLE; else if (cen) st <= d;
    end else if (RST == 1) begin : g_st_sync
      always_ff @(posedge clk) if (!rst_n) st <= IDLE; else if (cen) st <= d;
    end else if (RST == 2) begin : g_st_none
      always_ff @(posedge clk) if (cen) st <= d;
    end else begin : g_st_gated
      always_ff @(posedge clk) if (cen) begin if (!rst_n) st <= IDLE; else st <= d; end
    end
  endgenerate

  // ---- outputs
  function automatic logic [6:0] dec(input st_t s, input logic z);
    dec = {s == IDLE, (s == REQ || s == ADDR || s == DATA), s == ADDR, s == DATA, (s == DATA) && z,
           (s == RESP || s == ERR), s == ERR};                      // cmd_ready bus_req addr_v valid last rsp_valid err
  endfunction
  logic [7:0] o;
  generate
    if (OUT == 0) begin : g_comb
      assign o = {dec(st, zero), 1'b0};
    end else if (OUT == 1) begin : g_reg
      fsm_reg #(.W(8), .INIT(8'h80), .RST(RST)) u_o (.clk, .rst_n, .ce(cen), .d({dec(st, zero), st == IDLE && cmd_valid_i}), .q(o));
    end else begin : g_look
      fsm_reg #(.W(8), .INIT(8'h80), .RST(RST)) u_o (.clk, .rst_n, .ce(cen), .d({dec(d, zero_d), d == LOAD}), .q(o));
    end
  endgenerate
  assign {cmd_ready, bus_req, bus_addr_v, bus_valid, bus_last, rsp_valid, rsp_err} = o[7:1];
  assign cmd_ack = (OUT == 0) ? (st == IDLE && cmd_valid_i) : o[0];
endmodule
