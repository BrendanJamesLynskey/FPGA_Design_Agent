// Formal harness of the reference controller (brief 24): free inputs, one length property.
//   P_len: bus_valid is high for at most 4 consecutive cycles (a burst has 4 beats), P_last: bus_last only on the fourth beat,
//   P_err: rsp_err only with rsp_valid. `run` counts the consecutive bus_valid cycles; it is the harness's own history, so an
//   induction proof starts it from any value; the property it needs (a burst cannot start with more than 4 beats left) is a
//   fact about the machine: monolithic states carry it, a separate counter needs the invariant FORMAL_INV states.
module formal_ctl (input logic clk, input logic rst_n, input logic cmd_valid, input logic rsp_ready, input logic gnt, input logic ack, input logic nack);
  logic cmd_ready, cmd_ack, bus_req, bus_addr_v, bus_valid, bus_last, rsp_valid, rsp_err;
`ifdef MONO
  ctl_mono dut (.ce(1'b1), .*);
`else
  ctl_sep  dut (.ce(1'b1), .*);
`endif
  logic [2:0] run = 3'd0;
  always @(posedge clk) begin
    run <= bus_valid ? (run == 3'd7 ? run : run + 3'd1) : 3'd0;
    assert (!bus_valid || run <= 3'd3);                                    // P_len: no fifth beat
    assert (!bus_last || (bus_valid && run == 3'd3));                      // P_last: bus_last is on the fourth beat, and only there
    assert (!rsp_err || rsp_valid);                                        // P_err
`ifdef COVER
    cover (rsp_err);
    cover (run == 3'd3 && bus_valid && bus_last);
`endif
  end
endmodule
