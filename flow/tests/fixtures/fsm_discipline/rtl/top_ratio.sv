// The slow-FSM pattern (brief 20) around the reference controller: one fast clock, a one-in-N enable `ce` from a free-running
// counter, the FSM and its counter advance only on ce. N is a power of two. (The enable is registered: it is a flop output.)
module top_ratio #(parameter int N = 4, parameter int RST = 0) (
  input  logic clk, input logic rst_n,
  input  logic cmd_valid, output logic cmd_ready, output logic cmd_ack,
  input  logic gnt, input logic ack, input logic nack,
  output logic bus_req, output logic bus_addr_v, output logic bus_valid, output logic bus_last,
  output logic rsp_valid, output logic rsp_err, input logic rsp_ready
);
  localparam int CW = (N > 1) ? $clog2(N) : 1;
  logic [CW-1:0] tcnt = '0;
  logic ce = 1'b0;
  always_ff @(posedge clk) begin
    tcnt <= tcnt + 1'b1;
    ce   <= (N == 1) ? 1'b1 : (tcnt == CW'(N - 2));
  end
  ctl_sep #(.OUT(0), .IN(0), .RST(RST), .ZREG(0), .USE_CE(1)) u_ctl (.*);
endmodule
