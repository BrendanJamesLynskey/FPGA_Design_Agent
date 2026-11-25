`timescale 1ps/1ps
// Brief 208 (e): the safe-switch protocol of designs/clk_switch_safe.v with the unisim BUFGCTRL.
module tb_safe_switch;
  reg clk_ref = 0, i0 = 0, i1 = 0, run0 = 1, run1 = 1, req = 0;
  always #4000 clk_ref = ~clk_ref;          // 125 MHz reference
  always #5000 if (run0) i0 = ~i0;          // 100 MHz
  always #7000 if (run1) i1 = ~i1;          // ~71 MHz
  wire o, cur, busy, err, rst;
  clk_switch_safe dut (.clk_ref(clk_ref), .clk0(i0), .clk1(i1), .req_sel(req), .clk_out(o), .cur_sel(cur),
                       .busy(busy), .err(err), .rst_out(rst));
  integer runts = 0, n = 0, errs = 0, ign_seen = 0; time t = 0;
  always @(o) begin if ($time - t < 4900 && $time > 1000) begin runts = runts + 1; $display("RUNT %0d ps at %0t", $time - t, $time); end t = $time; end
  always @(posedge err) errs = errs + 1;
  always @(posedge dut.ign0 or posedge dut.ign1) ign_seen = ign_seen + 1;
  task count(input time w); begin n = 0; fork : f forever @(posedge o) n = n + 1; #w disable f; join end endtask
  initial begin
    #200000;
    req = 1; #600000 count(140000);
    $display("SCEN p1_both_running cur=%0d edges_in_140ns=%0d runts=%0d ignore_raised=%0d", cur, n, runts, ign_seen);
    req = 0; #600000;
    @(negedge i1); run1 = 0;                // the selected clock is I0; now stop I1 (not selected): request I1 -> refused
    #300000 req = 1; #300000;
    $display("SCEN p2_switch_to_dead_refused cur=%0d errs=%0d busy=%0d", cur, errs, busy);
    req = 0; run1 = 1; #400000;
    @(posedge i0); run0 = 0;                // the selected clock I0 stops HIGH; request I1
    #300000 req = 1; #600000 count(140000);
    $display("SCEN p3_leave_stopped_clock cur=%0d edges_in_140ns=%0d runts=%0d ignore_raised=%0d", cur, n, runts, ign_seen);
    $finish;
  end
endmodule
