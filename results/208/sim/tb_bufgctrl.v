`timescale 1ps/1ps
// Brief 208 (e): the unisim BUFGCTRL / BUFGMUX / BUFGMUX_CTRL models under clock switching, including a stopped input.
// I0: 10 ns period. I1: 14 ns period. A monitor prints every pulse on O shorter than the shortest input half period
// (5 ns): a runt pulse (glitch). Each scenario prints a summary line "SCEN <name> ..." that the README quotes.
module tb_bufgctrl;
  reg i0 = 0, i1 = 0;
  reg run0 = 1, run1 = 1;
  reg stop0_val = 0;
  always #5000 if (run0) i0 = ~i0; else i0 = stop0_val;
  always #7000 if (run1) i1 = ~i1;

  reg s = 0;          // select: 0 = I0, 1 = I1
  reg ign0 = 0, ign1 = 0;
  wire o_ctrl, o_mux, o_muxc;
  BUFGCTRL u_ctrl (.I0(i0), .I1(i1), .S0(~s), .S1(s), .CE0(1'b1), .CE1(1'b1), .IGNORE0(ign0), .IGNORE1(ign1), .O(o_ctrl));
  BUFGMUX      u_mux  (.I0(i0), .I1(i1), .S(s), .O(o_mux));
  BUFGMUX_CTRL u_muxc (.I0(i0), .I1(i1), .S(s), .O(o_muxc));

  // pulse monitors
  integer runt_ctrl = 0, runt_mux = 0, runt_muxc = 0, edges_ctrl = 0;
  time t_ctrl = 0, t_mux = 0, t_muxc = 0;
  always @(o_ctrl) begin edges_ctrl = edges_ctrl + 1;
    if ($time - t_ctrl < 4900 && $time > 1000) begin runt_ctrl = runt_ctrl + 1; $display("RUNT BUFGCTRL %0d ps pulse ending at %0t (O=%b)", $time - t_ctrl, $time, o_ctrl); end
    t_ctrl = $time; end
  always @(o_mux) begin
    if ($time - t_mux < 4900 && $time > 1000) begin runt_mux = runt_mux + 1; $display("RUNT BUFGMUX %0d ps pulse ending at %0t (O=%b)", $time - t_mux, $time, o_mux); end
    t_mux = $time; end
  always @(o_muxc) begin
    if ($time - t_muxc < 4900 && $time > 1000) begin runt_muxc = runt_muxc + 1; $display("RUNT BUFGMUX_CTRL %0d ps pulse ending at %0t (O=%b)", $time - t_muxc, $time, o_muxc); end
    t_muxc = $time; end

  // count O edges in a window to see whether the output follows I1 after a switch
  integer n_ctrl, n_mux, n_muxc;
  task count_edges(input time win);
    begin n_ctrl = 0; n_mux = 0; n_muxc = 0;
      fork : f
        forever @(posedge o_ctrl) n_ctrl = n_ctrl + 1;
        forever @(posedge o_mux)  n_mux  = n_mux + 1;
        forever @(posedge o_muxc) n_muxc = n_muxc + 1;
        #win disable f;
      join
    end
  endtask

  initial begin
    #100000;                          // settle on I0
    // e1: both clocks running, switch I0 -> I1 at an arbitrary time (not aligned to either clock)
    #3300 s = 1;
    #100000 count_edges(140000);      // 10 periods of I1 expected
    $display("SCEN e1_switch_running rising_edges_in_140ns ctrl=%0d mux=%0d muxc=%0d runts ctrl=%0d mux=%0d muxc=%0d",
             n_ctrl, n_mux, n_muxc, runt_ctrl, runt_mux, runt_muxc);
    // back to I0
    s = 0; #100000;
    // e2a: I0 (selected) stops LOW, then switch to I1
    @(negedge i0); run0 = 0; stop0_val = 0; #20000;
    s = 1; #50000 count_edges(140000);
    $display("SCEN e2a_i0_stopped_low_then_switch rising_edges_in_140ns ctrl=%0d mux=%0d muxc=%0d (10 = switched, 0 = locked up)", n_ctrl, n_mux, n_muxc);
    // e2c: same state, now assert IGNORE0 (the BUFGCTRL only): the switch completes at once
    ign0 = 1; #50000 count_edges(140000);
    $display("SCEN e2c_ignore0_asserted rising_edges_in_140ns ctrl=%0d (BUFGMUX/BUFGMUX_CTRL have no IGNORE pin: mux=%0d muxc=%0d)", n_ctrl, n_mux, n_muxc);
    ign0 = 0;
    // restart I0, return to I0
    run0 = 1; #100000 s = 0; #100000;
    // e2b: I0 stops HIGH, then switch to I1
    @(posedge i0); run0 = 0; stop0_val = 1; #20000;
    s = 1; #50000 count_edges(140000);
    $display("SCEN e2b_i0_stopped_high_then_switch rising_edges_in_140ns ctrl=%0d mux=%0d muxc=%0d", n_ctrl, n_mux, n_muxc);
    ign0 = 1; #50000 count_edges(140000);
    $display("SCEN e2d_ignore0_after_high_stop rising_edges_in_140ns ctrl=%0d", n_ctrl);
    ign0 = 0; run0 = 1; #100000 s = 0; #100000;
    // e3: select changes 10 ps before a rising edge of I0 and of I1 (inside any setup window), 20 times at random phases
    repeat (20) begin
      @(posedge i1); #6990 s = ~s;     // 10 ps before I1's falling edge, which the BUFGCTRL S path samples
      #37000;
    end
    $display("SCEN e3_select_near_edges runts ctrl=%0d mux=%0d muxc=%0d", runt_ctrl, runt_mux, runt_muxc);
    $finish;
  end
endmodule
