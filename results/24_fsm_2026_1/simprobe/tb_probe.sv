module tb_probe;
  logic clk = 0, rst_n = 0, go = 0, fin = 0; wire busy;
  probe_fsm dut (.*);
  always #5 clk = ~clk;
  initial begin
    repeat (3) @(posedge clk); rst_n <= 1;
    @(posedge clk); go <= 1; @(posedge clk); go <= 0;   // IDLE -> RUN
    repeat (2) @(posedge clk); fin <= 1; @(posedge clk); fin <= 0;   // RUN -> DONE -> IDLE
    repeat (3) @(posedge clk);
    $display("PROBE_DONE");
    $finish;
  end
  // the bench never takes RUN -> ERR (go while RUN): that transition and state ERR are never reached
endmodule
