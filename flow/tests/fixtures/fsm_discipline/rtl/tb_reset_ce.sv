// Reset behaviour of the FSM when it advances only on an enable (brief 24): a one-clock reset pulse at each phase of a 1-in-4
// enable, for the reset styles RST = 0 (async), 1 (sync over the enable), 3 (async assert, sync release), 4 (sync, gated by the enable).
// Prints "RESET_CE rst=<R> phase=<p> reset_seen=<0|1>": 1 when the controller was back in IDLE (cmd_ready high) after the pulse.
module tb_reset_ce;
  logic clk = 0; always #5 clk = ~clk;
  logic [3:0] ph = 0;                         // enable phase counter: ce high when ph == 3 (registered, as top_ratio does)
  logic ce = 0;
  always_ff @(posedge clk) begin ph <= ph + 1; ce <= (ph == 4'd2) | (ph == 4'd6) | (ph == 4'd10) | (ph == 4'd14); end
  logic rst_n = 1;
  logic cmd_valid = 0;
  wire [3:0] ready;
  genvar g;
  for (g = 0; g < 4; g++) begin : d
    localparam int R = (g == 0) ? 0 : (g == 1) ? 1 : (g == 2) ? 3 : 4;
    logic cmd_ack, bus_req, bus_addr_v, bus_valid, bus_last, rsp_valid, rsp_err;
    ctl_sep #(.OUT(0), .IN(0), .RST(R), .USE_CE(1)) u (.clk, .rst_n, .ce, .cmd_valid, .cmd_ready(ready[g]), .cmd_ack, .gnt(1'b0), .ack(1'b0),
              .nack(1'b0), .bus_req, .bus_addr_v, .bus_valid, .bus_last, .rsp_valid, .rsp_err, .rsp_ready(1'b0));
  end
  integer p, i;
  task automatic try(input integer phase);
    begin
      cmd_valid = 1;                                   // leave IDLE and stay out of it (no gnt: the controller waits in REQ)
      repeat (24) @(posedge clk);
      cmd_valid = 0;
      if (ready != 4'b0000) $display("NOT_OUT_OF_IDLE %b", ready);
      while (ph[1:0] != phase[1:0]) @(posedge clk);    // align with the enable phase, then pulse reset for exactly one clock
      #1 rst_n = 0; @(posedge clk); #1 rst_n = 1;
      repeat (3) @(posedge clk);                       // a 3-clock look: a 1-in-4 enable has ticked at most once more
      #1 $display("RESET_CE phase=%0d async=%b sync_over_ce=%b async_assert_sync_release=%b sync_gated_by_ce=%b", phase, ready[0], ready[1], ready[2], ready[3]);
      // bring all four back to IDLE for the next phase
      #1 rst_n = 0; repeat (8) @(posedge clk); #1 rst_n = 1; repeat (8) @(posedge clk);
    end
  endtask
  initial begin
    repeat (3) @(posedge clk); #1 rst_n = 0; repeat (8) @(posedge clk); #1 rst_n = 1; repeat (8) @(posedge clk);
    for (p = 0; p < 4; p++) try(p);
    $finish;
  end
endmodule
