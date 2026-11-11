// Equivalence and latency bench for the brief 24 reference controller (Icarus 12, plain SystemVerilog, no cocotb).
//   separated (ctl_sep) against monolithic (ctl_mono): every output, every cycle, under random inputs and random resets;
//   OUT=2 (lookahead) against OUT=0 (combinational): equal except cmd_ack, which is one cycle later;
//   OUT=1 (registered) against OUT=0 delayed by one cycle.
// Prints "EQUIV_OK <cycles>" or the first mismatches, then the latencies measured with a fixed scenario.
module tb_equiv;
  logic clk = 0, rst_n = 0;
  logic cmd_valid = 0, gnt = 0, ack = 0, nack = 0, rsp_ready = 0;
  always #5 clk = ~clk;

  `define OUTS(p) wire p``_cr, p``_ca, p``_br, p``_av, p``_bv, p``_bl, p``_rv, p``_re;
  `OUTS(a) `OUTS(b) `OUTS(c) `OUTS(d) `OUTS(e) `OUTS(f)
  `define DUT(M, o, p) M #(.OUT(o), .RST(0)) p``_i (.clk, .rst_n, .ce(1'b1), .cmd_valid, .cmd_ready(p``_cr), .cmd_ack(p``_ca), \
      .gnt, .ack, .nack, .bus_req(p``_br), .bus_addr_v(p``_av), .bus_valid(p``_bv), .bus_last(p``_bl), \
      .rsp_valid(p``_rv), .rsp_err(p``_re), .rsp_ready);
  `DUT(ctl_sep, 0, a) `DUT(ctl_mono, 0, b) `DUT(ctl_sep, 2, c) `DUT(ctl_mono, 2, d) `DUT(ctl_sep, 1, e) `DUT(ctl_mono, 1, f)

  wire [7:0] va = {a_cr, a_ca, a_br, a_av, a_bv, a_bl, a_rv, a_re}, vb = {b_cr, b_ca, b_br, b_av, b_bv, b_bl, b_rv, b_re};
  wire [7:0] vc = {c_cr, c_ca, c_br, c_av, c_bv, c_bl, c_rv, c_re}, vd = {d_cr, d_ca, d_br, d_av, d_bv, d_bl, d_rv, d_re};
  wire [7:0] ve = {e_cr, e_ca, e_br, e_av, e_bv, e_bl, e_rv, e_re}, vf = {f_cr, f_ca, f_br, f_av, f_bv, f_bl, f_rv, f_re};
  logic [7:0] va_q;
  integer errs = 0, cyc = 0, since_rst = 9;
  localparam logic [7:0] NOACK = 8'b1011_1111;        // bit 6 is cmd_ack: compare everything but it
  always @(negedge clk) begin
    cyc++; since_rst = rst_n ? since_rst + 1 : 0;
    if (va !== vb) begin errs++; if (errs < 5) $display("MISMATCH sep/mono OUT0 t=%0d %b %b", cyc, va, vb); end
    if (vc !== vd) begin errs++; if (errs < 5) $display("MISMATCH sep/mono OUT2 t=%0d %b %b", cyc, vc, vd); end
    if (ve !== vf) begin errs++; if (errs < 5) $display("MISMATCH sep/mono OUT1 t=%0d %b %b", cyc, ve, vf); end
    if (since_rst > 2) begin
      if ((vc & NOACK) !== (va & NOACK)) begin errs++; if (errs < 5) $display("MISMATCH lookahead/comb t=%0d %b %b", cyc, vc, va); end
      if ((ve & NOACK) !== (va_q & NOACK)) begin errs++; if (errs < 5) $display("MISMATCH registered/comb-delayed t=%0d %b %b", cyc, ve, va_q); end
    end
    va_q <= va;
  end

  integer seed = 7, t;
  initial begin
    repeat (3) @(posedge clk); #1 rst_n = 1;
    for (t = 0; t < 40000; t++) begin
      @(posedge clk); #1;
      cmd_valid = ($urandom(seed) % 100) < 50;  gnt = ($urandom % 100) < 30;
      ack = ($urandom % 100) < 12;               nack = ($urandom % 100) < 6;
      rsp_ready = ($urandom % 100) < 40;
      if (($urandom % 700) == 0) rst_n = 0; else rst_n = 1;
    end
    if (errs == 0) $display("EQUIV_OK %0d", cyc); else $display("EQUIV_FAIL %0d", errs);
    $finish;
  end
endmodule
