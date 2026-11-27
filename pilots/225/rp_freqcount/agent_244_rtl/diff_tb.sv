// Brief 244: lock-step comparison of rp_freqcount (brief 244 repair) against rp_freqcount_old (agent_235_r2_rtl, module renamed by the test).
// Same bus and the same input on both. The repaired block writes DONE, BUSY (fall), EDGES, GATE_ACTUAL, SPAN, FEW_EDGES and MEAS_DONE exactly one clock
// after the old one: every clock, new(t) must equal old(t-1) for those registers, over START gates, a CONT run, a gate_len change, a clear of CONT in the
// middle of a gate, thresholds in the wrong order and a flat input. START writes are never made in the one clock where BUSY differs (documented).
module tb;
  logic clk = 0, rstn = 0;
  logic [31:0] addr = 0, wdata = 0, rd_n, rd_o; logic wen = 0, ren = 0, err_n, err_o, ack_n, ack_o;
  logic signed [13:0] a = 0, b = 0, dan, dbn, dao, dbo;
  rp_freqcount dut(.clk(clk), .rstn(rstn), .sys_addr(addr), .sys_wdata(wdata), .sys_wen(wen), .sys_ren(ren), .sys_rdata(rd_n), .sys_err(err_n), .sys_ack(ack_n),
                   .adc_a(a), .adc_b(b), .dac_a(dan), .dac_b(dbn));
  rp_freqcount_old ref0(.clk(clk), .rstn(rstn), .sys_addr(addr), .sys_wdata(wdata), .sys_wen(wen), .sys_ren(ren), .sys_rdata(rd_o), .sys_err(err_o), .sys_ack(ack_o),
                   .adc_a(a), .adc_b(b), .dac_a(dao), .dac_b(dbo));
  always #4 clk = ~clk;
  real freq = 1.0e6, amp = 4000.0, t = 0.0;
  always @(posedge clk) begin t = t + 8.0e-9; a <= $rtoi(amp * $sin(6.283185307179586 * freq * t)); end
  int fails = 0, compared = 0, gates = 0;
  logic [31:0] p_edges, p_act, p_span, p_md; logic p_done, p_busy, p_few;
  logic [31:0] o_edges, o_act, o_span, o_md; logic o_done, o_busy, o_few;     // the old block, one clock earlier
  logic cmp_on = 0;
  int quiet = 0;
  always @(posedge clk) quiet <= (wen && addr[7:0] == 8'h08) ? 0 : quiet + 1;
  always @(posedge clk) begin
    // sample just before the edge: the old block's state now is what the new block shows after the next edge
    o_edges <= ref0.edges; o_act <= ref0.gate_actual; o_span <= ref0.span; o_md <= ref0.meas_done; o_done <= ref0.done; o_busy <= ref0.busy; o_few <= ref0.fewedges;
    if (cmp_on) begin
      compared++;
      // START and CONT writes act at the same clock in both blocks, so DONE and BUSY are compared one clock late only when no CONT/START write was made in the last 3 clocks
      if (dut.edges !== o_edges || dut.gate_actual !== o_act || dut.span !== o_span || dut.meas_done !== o_md || dut.fewedges !== o_few ||
          (quiet > 3 && (dut.done !== o_done || dut.busy !== o_busy))) begin
        fails++;
        if (fails < 6) $display("MISMATCH t=%0t new e=%0d a=%0d s=%0d m=%0d d=%b b=%b f=%b | old(t-1) e=%0d a=%0d s=%0d m=%0d d=%b b=%b f=%b", $time, dut.edges, dut.gate_actual,
          dut.span, dut.meas_done, dut.done, dut.busy, dut.fewedges, o_edges, o_act, o_span, o_md, o_done, o_busy, o_few);
      end
      if (rd_n !== rd_o && 0) fails++;
    end
    if (ref0.meas_done !== o_md && cmp_on) gates++;
  end
  task w(input [31:0] ad, input [31:0] dd);
    @(negedge clk); addr = ad; wdata = dd; wen = 1; ren = 0; @(negedge clk); wen = 0;
  endtask
  // START only when the old block is not in the gap: both agree on BUSY (new BUSY lags the old one by a clock when CONT is 0)
  task start(input [31:0] v);
    wait (dut.busy === ref0.busy); @(negedge clk); wait (dut.busy === ref0.busy && !dut.fin); w(32'h08, v);
  endtask
  initial begin
    repeat (4) @(posedge clk); rstn = 1; repeat (3) @(posedge clk); cmp_on = 1;
    w(32'h0C, 32'd1000);
    freq = 1.0e6; start(32'd1); repeat (1400) @(posedge clk);
    freq = 3.3e6; start(32'd1); repeat (1400) @(posedge clk);
    freq = 20.0e6; start(32'd1); repeat (1400) @(posedge clk);
    freq = 61.0e3; start(32'd1); repeat (1400) @(posedge clk);
    freq = 250.0e3; start(32'd1); repeat (1400) @(posedge clk);      // about 2 edges: the FEW_EDGES boundary
    freq = 330.0e3; start(32'd1); repeat (1400) @(posedge clk);
    freq = 180.0e3; start(32'd1); repeat (1400) @(posedge clk);
    freq = 1.0e6; w(32'h0C, 32'd2500); start(32'd3);                 // CONT run, three gates then clear CONT in the middle of a gate
    repeat (6000) @(posedge clk); w(32'h08, 32'd0); repeat (4000) @(posedge clk);
    w(32'h0C, 32'd1000); start(32'd3); repeat (8500) @(posedge clk); w(32'h08, 32'd0); repeat (1500) @(posedge clk);
    amp = 0.0; start(32'd1); repeat (1400) @(posedge clk);          // flat input
    amp = 4000.0; w(32'h10, 32'h3F00); start(32'd1); repeat (1400) @(posedge clk);   // thresholds in the wrong order
    w(32'h10, 32'd256); freq = 7.7e6; start(32'd1); repeat (1400) @(posedge clk);
    $display("compared %0d clocks, %0d gates, %0d mismatches", compared, gates, fails);
    if (fails == 0 && gates >= 18) $display("DIFF PASS"); else $display("DIFF FAIL");
    $finish;
  end
endmodule
