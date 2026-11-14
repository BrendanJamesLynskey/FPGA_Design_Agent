// Brief 70 Part 2b: Processor System Reset sequencing, measured black-box in xsim (the generated IP, default settings:
// external reset active low, auxiliary reset active high, four-stage low-pass filters). The bench drives stimulus and
// prints every output change with the clock-cycle count: EV|cycle|signal|value, and MARK|cycle|label at each stimulus
// step. run_psr.py turns the log into latencies. Clock period 10 ns; outputs sampled at the clock's rising edge.
`timescale 1ns/1ps
module tb_psr;
  // EXT_HIGH: 1 when the external reset input is active high (the generated IP's default), 0 when active low; run_psr.py sets it
  localparam bit EXT_HIGH = 1'b1;   // @EXT_HIGH@
  logic clk = 0;
  logic ext = !EXT_HIGH, aux = 0, dbg = 0, locked = 1;
  wire mb, bus_rst, per_rst;
  wire [0:0] ic_n, per_n;
  psr_dut dut (.slowest_sync_clk(clk), .ext_reset_in(ext), .aux_reset_in(aux), .mb_debug_sys_rst(dbg), .dcm_locked(locked),
               .mb_reset(mb), .bus_struct_reset(bus_rst), .peripheral_reset(per_rst),
               .interconnect_aresetn(ic_n), .peripheral_aresetn(per_n));
  always #5 clk = ~clk;
  int cyc = 0;
  always @(posedge clk) cyc <= cyc + 1;
  always @(mb)      $display("EV|%0d|mb_reset|%b", cyc, mb);
  always @(bus_rst) $display("EV|%0d|bus_struct_reset|%b", cyc, bus_rst);
  always @(per_rst) $display("EV|%0d|peripheral_reset|%b", cyc, per_rst);
  always @(ic_n)    $display("EV|%0d|interconnect_aresetn|%b", cyc, ic_n);
  always @(per_n)   $display("EV|%0d|peripheral_aresetn|%b", cyc, per_n);

  task automatic mark(input string s); $display("MARK|%0d|%s", cyc, s); endtask
  task automatic clks(input int n); repeat (n) @(posedge clk); endtask
  // drive an input for n cycles then return it to its inactive level
  task automatic pulse_ext(input int n, input string label);
    mark({label, "_begin"}); ext <= EXT_HIGH; clks(n); ext <= !EXT_HIGH; mark({label, "_end"});
  endtask
  task automatic pulse_aux(input int n, input string label);
    mark({label, "_begin"}); aux <= 1; clks(n); aux <= 0; mark({label, "_end"});
  endtask

  int widths [6] = '{1, 2, 3, 4, 5, 8};
  int awidths [3] = '{1, 4, 8};
  initial begin
    #1;
    $display("T0|bus_struct_reset=%b peripheral_reset=%b interconnect_aresetn=%b peripheral_aresetn=%b mb_reset=%b",
             bus_rst, per_rst, ic_n, per_n, mb);
    mark("power_up");            // no reset requested: the core's own power-on sequence runs
    clks(150);
    foreach (widths[i]) begin pulse_ext(widths[i], $sformatf("ext_%0d", widths[i])); clks(150); end
    foreach (awidths[i]) begin pulse_aux(awidths[i], $sformatf("aux_%0d", awidths[i])); clks(150); end
    mark("dbg_4_begin"); dbg <= 1; clks(4); dbg <= 0; mark("dbg_4_end"); clks(150);
    mark("locked_6_begin"); locked <= 0; clks(6); locked <= 1; mark("locked_6_end"); clks(150);
    // a second request while the sequence from the first is still running
    pulse_ext(8, "re_a"); clks(20); pulse_ext(8, "re_b"); clks(150);
    mark("end");
    $finish;
  end
endmodule
