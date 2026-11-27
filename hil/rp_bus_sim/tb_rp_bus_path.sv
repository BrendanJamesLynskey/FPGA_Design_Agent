// Brief 243: the bus path of the patched Red Pitaya top, from the PS-side master to the user blocks in slots 6 and 7, as tools/rp_shell.py wires them.
// Vendor parts (the interconnect, its clock-crossing bridge, the stubs) are the pinned vendor files; the two slot instances come from rp_shell.slot_instance
// through `include "slots.svh" (written by hil/rp_bus_sim/run_xsim.py), so the test cannot drift from the patch.
// The master drives the bus as the vendor's AXI slave does: addr and wdata held, a one-cycle wen or ren pulse, then waits for ack (32 cycles at most).
// The PS clock (fclk0) and the shell clock (adc_clk) are the same 125 MHz from different buffers: here an offset of `PHASE ns (0.5 to 7.5).
module tb_rp_bus_path;
  logic fclk = 0, adc_clk = 0, frstn = 0, adc_rstn = 0;
  always #4 fclk = ~fclk;
  initial begin #`PHASE; forever #4 adc_clk = ~adc_clk; end
  sys_bus_if ps_sys (.clk(fclk), .rstn(frstn));
  sys_bus_if sys [8-1:0] (.clk(adc_clk), .rstn(adc_rstn));
  sys_bus_interconnect #(.SN(8), .SW(20)) sys_bus_interconnect (.pll_locked_i(1'b1), .bus_m(ps_sys), .bus_s(sys));
  for (genvar i = 0; i < 6; i++) begin : g_stub
    sys_bus_stub s (sys[i]);
  end
  logic signed [13:0] adc_dat [2];
  logic signed [13:0] user_dac [2], user6_dac [2];
  initial begin adc_dat[0] = 14'sd100; adc_dat[1] = -14'sd50; end
  `include "slots.svh"

  initial begin ps_sys.wen = 0; ps_sys.ren = 0; ps_sys.addr = 0; ps_sys.wdata = 0; end
  int errors = 0;
  task automatic access(input bit w, input [31:0] a, input [31:0] d, output [31:0] r, output bit timeout, output bit err);
    int n;
    @(posedge fclk); ps_sys.addr <= a; ps_sys.wdata <= d;
    @(posedge fclk); if (w) ps_sys.wen <= 1; else ps_sys.ren <= 1;
    @(posedge fclk); ps_sys.wen <= 0; ps_sys.ren <= 0;
    n = 0; timeout = 0;
    while (!ps_sys.ack && n < 32) begin @(posedge fclk); n++; end
    if (!ps_sys.ack) timeout = 1;
    r = ps_sys.rdata; err = ps_sys.err;
    repeat (4) @(posedge fclk);
  endtask
  task automatic rd(input [31:0] a, input [31:0] exp, input string what);
    logic [31:0] r; bit t, e;
    access(0, a, 0, r, t, e);
    $display("READ  %-26s %08h -> %08h timeout=%0d err=%0d", what, a, r, t, e);
    if (t || r !== exp) begin errors++; $display("  FAIL: expected %08h", exp); end
  endtask
  task automatic wr(input [31:0] a, input [31:0] d, input string what);
    logic [31:0] r; bit t, e;
    access(1, a, d, r, t, e);
    $display("WRITE %-26s %08h <- %08h timeout=%0d err=%0d", what, a, d, t, e);
    if (t) errors++;
  endtask
  initial begin
    repeat (20) @(posedge fclk); frstn = 1; adc_rstn = 1; repeat (10) @(posedge fclk);
    rd(32'h0060_0000, `ID6, "slot 6 ID");
    rd(32'h0070_0000, `ID7, "slot 7 ID");
    wr(32'h0060_0004, 32'hA5A5A5A5, "slot 6 SCRATCH");
    rd(32'h0060_0004, 32'hA5A5A5A5, "slot 6 SCRATCH");
    wr(32'h0070_0004, 32'h5A5A5A5A, "slot 7 SCRATCH");
    rd(32'h0070_0004, 32'h5A5A5A5A, "slot 7 SCRATCH");
    rd(32'h0060_0004, 32'hA5A5A5A5, "slot 6 SCRATCH again");     // the other slot's access did not disturb it
    rd(32'h0060_0000, `ID6, "slot 6 ID again");
    $display("ERRORS=%0d", errors);
    if (errors == 0) $display("BUS PATH PASS"); else $display("BUS PATH FAIL");
    $finish;
  end
endmodule
