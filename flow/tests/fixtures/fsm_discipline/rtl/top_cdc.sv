// An input of the controller launched by another clock (brief 24, brief 16's CDC gate). `ack_a` is a pin in the aclk domain;
// the controller's `ack` input is that pin's registered copy (an aclk flop). IN selects what the controller's clock domain does with it:
//   0 uses it directly (a path from an aclk flop into clk logic), 1 one register (no second stage), 2 two ASYNC_REG registers.
module top_cdc #(parameter int IN = 1) (
  input  logic clk, input logic aclk, input logic rst_n,
  input  logic cmd_valid, output logic cmd_ready, output logic cmd_ack,
  input  logic gnt, input logic ack_a, input logic nack,
  output logic bus_req, output logic bus_addr_v, output logic bus_valid, output logic bus_last,
  output logic rsp_valid, output logic rsp_err, input logic rsp_ready
);
  logic ack = 1'b0;
  always_ff @(posedge aclk) ack <= ack_a;
  ctl_sep #(.OUT(0), .IN(IN), .RST(0), .ZREG(0), .USE_CE(0)) u_ctl (.clk, .rst_n, .ce(1'b1), .*);
endmodule
