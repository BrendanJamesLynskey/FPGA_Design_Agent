// Reference burst controller, monolithic: the same behaviour with the counter folded into the states (brief 24).
// DATA x4 -> D3..D0, WACK (8-cycle timeout) -> W7..W0, COOL x3 -> C2..C0: 23 states, no counter. Parameters as ctl_sep.
module ctl_mono #(parameter int OUT = 0, parameter int IN = 0, parameter int RST = 0, parameter int ZREG = 0,
                  parameter int USE_CE = 0) (
  input  logic clk, input logic rst_n, input logic ce,
  input  logic cmd_valid, output logic cmd_ready, output logic cmd_ack,
  input  logic gnt, input logic ack, input logic nack,
  output logic bus_req, output logic bus_addr_v, output logic bus_valid, output logic bus_last,
  output logic rsp_valid, output logic rsp_err, input logic rsp_ready
);
  typedef enum logic [4:0] {IDLE, LOAD, REQ, ADDR, D3, D2, D1, D0, TURN, W7, W6, W5, W4, W3, W2, W1, W0,
                            RETRY, RESP, ERR, C2, C1, C0} st_t;
  st_t st = IDLE, d;
  logic cmd_valid_i, gnt_i, ack_i, nack_i, rsp_ready_i;
  fsm_in #(IN) u_i0 (clk, cmd_valid, cmd_valid_i);
  fsm_in #(IN) u_i1 (clk, gnt, gnt_i);
  fsm_in #(IN) u_i2 (clk, ack, ack_i);
  fsm_in #(IN) u_i3 (clk, nack, nack_i);
  fsm_in #(IN) u_i4 (clk, rsp_ready, rsp_ready_i);
  wire cen = (USE_CE != 0) ? ce : 1'b1;

  always_comb begin
    d = st;
    case (st)
      IDLE:  if (cmd_valid_i) d = LOAD;
      LOAD:  d = REQ;
      REQ:   if (gnt_i) d = ADDR;
      ADDR:  d = D3;
      D3:    d = D2;
      D2:    d = D1;
      D1:    d = D0;
      D0:    d = TURN;
      TURN:  d = W7;
      W7:    if (ack_i) d = RESP; else if (nack_i) d = RETRY; else d = W6;
      W6:    if (ack_i) d = RESP; else if (nack_i) d = RETRY; else d = W5;
      W5:    if (ack_i) d = RESP; else if (nack_i) d = RETRY; else d = W4;
      W4:    if (ack_i) d = RESP; else if (nack_i) d = RETRY; else d = W3;
      W3:    if (ack_i) d = RESP; else if (nack_i) d = RETRY; else d = W2;
      W2:    if (ack_i) d = RESP; else if (nack_i) d = RETRY; else d = W1;
      W1:    if (ack_i) d = RESP; else if (nack_i) d = RETRY; else d = W0;
      W0:    if (ack_i) d = RESP; else if (nack_i) d = RETRY; else d = ERR;
      RETRY: d = REQ;
      RESP:  if (rsp_ready_i) d = C2;
      ERR:   if (rsp_ready_i) d = C2;
      C2:    d = C1;
      C1:    d = C0;
      C0:    d = IDLE;
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

  function automatic logic [6:0] dec(input st_t s);
    dec = {s == IDLE, (s == REQ || s == ADDR || s == D3 || s == D2 || s == D1 || s == D0), s == ADDR,
           (s == D3 || s == D2 || s == D1 || s == D0), s == D0, (s == RESP || s == ERR), s == ERR};
  endfunction
  logic [7:0] o;
  generate
    if (OUT == 0) begin : g_comb
      assign o = {dec(st), 1'b0};
    end else if (OUT == 1) begin : g_reg
      fsm_reg #(.W(8), .INIT(8'h80), .RST(RST)) u_o (.clk, .rst_n, .ce(cen), .d({dec(st), st == IDLE && cmd_valid_i}), .q(o));
    end else begin : g_look
      fsm_reg #(.W(8), .INIT(8'h80), .RST(RST)) u_o (.clk, .rst_n, .ce(cen), .d({dec(d), d == LOAD}), .q(o));
    end
  endgenerate
  assign {cmd_ready, bus_req, bus_addr_v, bus_valid, bus_last, rsp_valid, rsp_err} = o[7:1];
  assign cmd_ack = (OUT == 0) ? (st == IDLE && cmd_valid_i) : o[0];
endmodule
