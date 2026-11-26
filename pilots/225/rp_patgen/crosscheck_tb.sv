// Independent cross-check of the agent's rp_patgen (brief 225): written by the executor from the spec and hil/redpitaya_models.py, not by the agent and not from the
// agent's tests. iverilog -g2012 crosscheck_tb.sv rtl/rp_patgen.sv; vvp. It waits for sys_ack up to 4 cycles (the spec says "the next cycle"; the latency is reported).
module tb;
  logic clk = 0, rstn = 0;
  logic [31:0] addr = 0, wdata = 0, rdata; logic wen = 0, ren = 0, err, ack;
  logic signed [13:0] a = 0, b = 0, da, db;
  rp_patgen dut(.clk(clk), .rstn(rstn), .sys_addr(addr), .sys_wdata(wdata), .sys_wen(wen), .sys_ren(ren), .sys_rdata(rdata), .sys_err(err), .sys_ack(ack),
                .adc_a(a), .adc_b(b), .dac_a(da), .dac_b(db));
  always #4 clk = ~clk;
  int fails = 0, lat = 0, maxabs = 0;
  always @(posedge clk) begin if (da > maxabs) maxabs <= da; if (-da > maxabs) maxabs <= -da; end
  task acc(input [31:0] ad, input [31:0] d, input bit w, output [31:0] q, output logic e);
    int n;
    @(negedge clk); addr = ad; wdata = d; wen = w; ren = !w; n = 0;
    @(negedge clk); wen = 0; ren = 0;
    while (!ack && n < 4) begin @(negedge clk); n++; end
    #1 q = rdata; e = err; lat = n + 1;
    if (!ack) begin $display("no ack"); fails++; end
  endtask
  task wr(input [31:0] ad, input [31:0] d, output logic e); logic [31:0] q; acc(ad, d, 1, q, e); endtask
  task rd(input [31:0] ad, output [31:0] q, output logic e); acc(ad, 0, 0, q, e); endtask
  task chk(input string what, input bit ok); if (!ok) begin $display("FAIL: %s", what); fails++; end endtask
  logic [31:0] d; logic e; int hi_seen, lo_seen, cyc, nonzero_after;
  logic signed [13:0] trace [0:511];
  initial begin
    repeat (4) @(posedge clk); rstn = 1;
    rd(32'h00, d, e); chk("ID", d === 32'hFDA10201 && !e); $display("access latency %0d cycles after the access cycle", lat);
    rd(32'h24, d, e); chk("LIMIT reset 4096", d === 32'd4096);
    rd(32'h18, d, e); chk("LEVEL_HI reset 2048", d === 32'd2048);
    wr(32'h24, 32'h7FFF, e); rd(32'h24, d, e); chk("LIMIT ceiling 7372", d === 32'd7372);
    wr(32'h10, 32'd0, e); rd(32'h10, d, e); chk("PERIOD clamps to 2", d === 32'd2);
    wr(32'h20, 32'd0, e); rd(32'h20, d, e); chk("COUNT clamps to 1", d === 32'd1);
    wr(32'h30, 32'd99, e); rd(32'h30, d, e); chk("PAT_LEN clamps to 16", d === 32'd16);
    wr(32'h0C, 32'd7, e); rd(32'h0C, d, e); chk("MODE other stores 0", d === 32'd0);
    wr(32'h2C, 32'd1, e); chk("write to RO errors", e === 1'b1);
    rd(32'h38, d, e); chk("unmapped 0x38 errors", e === 1'b1);
    rd(32'h40 + 32'h100, d, e); chk("unmapped beyond map errors", e === 1'b1);
    // pulse train with levels above LIMIT
    wr(32'h24, 32'd3000, e); wr(32'h18, 32'd5000, e); wr(32'h1C, (-4000) & 32'h3FFF, e);
    wr(32'h10, 32'd100, e); wr(32'h14, 32'd40, e); wr(32'h20, 32'd2, e);
    maxabs = 0;
    wr(32'h08, 32'd1, e);
    for (cyc = 0; cyc < 400; cyc++) begin @(posedge clk); #1 if (cyc < 512) trace[cyc] = da; end
    hi_seen = 0; lo_seen = 0; nonzero_after = 0;
    for (cyc = 0; cyc < 400; cyc++) begin if (trace[cyc] == 3000) hi_seen++; if (trace[cyc] == -3000) lo_seen++; if (cyc > 250 && trace[cyc] != 0) nonzero_after++; end
    $display("hi cycles %0d lo cycles %0d max |dac| %0d", hi_seen, lo_seen, maxabs);
    chk("output never exceeds LIMIT", maxabs <= 3000);
    chk("high cycles = 2 periods x WIDTH", hi_seen == 80);
    chk("low cycles = 2 x 60", lo_seen == 120);
    chk("zero after the sequence", nonzero_after == 0);
    rd(32'h28, d, e); chk("DONE, not RUNNING, CLAMPED", d[1] === 1'b1 && d[0] === 1'b0 && d[2] === 1'b1);
    rd(32'h2C, d, e); chk("PERIODS_DONE 2", d === 32'd2);
    // STOP ends a continuous run at once
    wr(32'h08, 32'd5, e); repeat (50) @(posedge clk); rd(32'h28, d, e); chk("RUNNING in CONT", d[0] === 1'b1);
    wr(32'h08, 32'd2, e); repeat (3) @(posedge clk); #1 chk("zero after STOP", da === 0); rd(32'h28, d, e); chk("not RUNNING after STOP", d[0] === 1'b0);
    // reset: output 0
    rstn = 0; repeat (2) @(posedge clk); #1 chk("zero in reset", da === 0 && db === 0);
    if (fails == 0) $display("XCHECK PASS"); else $display("XCHECK FAIL %0d", fails);
    $finish;
  end
endmodule
