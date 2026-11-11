// cocotb wrapper of the reference controller (brief 24): variant chosen by parameters; instance `dut`.
module tb_ctl #(parameter bit MONO = 0, parameter int OUT = 0, parameter int IN = 0, parameter int RST = 0) (
  input  logic clk, input logic rst_n,
  input  logic cmd_valid, output logic cmd_ready, output logic cmd_ack,
  input  logic gnt, input logic ack, input logic nack,
  output logic bus_req, output logic bus_addr_v, output logic bus_valid, output logic bus_last,
  output logic rsp_valid, output logic rsp_err, input logic rsp_ready
);
  generate
    if (MONO) begin : g
      ctl_mono #(.OUT(OUT), .IN(IN), .RST(RST)) dut (.ce(1'b1), .*);
    end else begin : g
      ctl_sep #(.OUT(OUT), .IN(IN), .RST(RST)) dut (.ce(1'b1), .*);
    end
  endgenerate
endmodule
