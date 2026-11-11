// The reference controller on real pins (Nexys A7-100T, brief 24): to see which flops the tool packs into the I/O blocks and
// what a clock-to-output costs for combinational, registered and lookahead outputs.
module top_io #(parameter int OUT = 0, parameter int IN = 0) (
  input  logic clk, input logic rst_n,
  input  logic cmd_valid, output logic cmd_ready, output logic cmd_ack,
  input  logic gnt, input logic ack, input logic nack,
  output logic bus_req, output logic bus_addr_v, output logic bus_valid, output logic bus_last,
  output logic rsp_valid, output logic rsp_err, input logic rsp_ready
);
  ctl_sep #(.OUT(OUT), .IN(IN), .RST(1), .ZREG(0), .USE_CE(0)) u_ctl (.ce(1'b1), .*);
endmodule
