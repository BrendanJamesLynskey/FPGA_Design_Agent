// Independent cross-check of the agent's rp_freqcount (brief 225): written by the executor from the spec and hil/redpitaya_models.py, not by the agent, not from
// the agent's tests. A sine on adc_a at 1 MHz, 125 MHz clock; checks the registers' stated behaviour. iverilog -g2012 crosscheck_tb.sv rtl/rp_freqcount.sv; vvp.
module tb;
  logic clk = 0, rstn = 0;
  logic [31:0] addr = 0, wdata = 0, rdata; logic wen = 0, ren = 0, err, ack;
  logic signed [13:0] a = 0, b = 0, da, db;
  rp_freqcount dut(.clk(clk), .rstn(rstn), .sys_addr(addr), .sys_wdata(wdata), .sys_wen(wen), .sys_ren(ren), .sys_rdata(rdata), .sys_err(err), .sys_ack(ack),
                   .adc_a(a), .adc_b(b), .dac_a(da), .dac_b(db));
  always #4 clk = ~clk;
  real freq = 1.0e6, amp = 4000.0, t = 0.0;
  always @(posedge clk) begin t = t + 8.0e-9; a <= $rtoi(amp * $sin(6.283185307179586 * freq * t)); end
  int fails = 0;
  task wr(input [31:0] ad, input [31:0] d, output logic e);
    @(negedge clk); addr = ad; wdata = d; wen = 1; @(negedge clk); wen = 0; #1 e = err;
  endtask
  task rd(input [31:0] ad, output [31:0] d, output logic e);
    @(negedge clk); addr = ad; ren = 1; @(negedge clk); ren = 0; #1 d = rdata; e = err;
  endtask
  task chk(input string what, input bit ok); if (!ok) begin $display("FAIL: %s", what); fails++; end endtask
  logic [31:0] d, edges, actual, span, n0, n1; logic e; real fg, fr;
  initial begin
    repeat (4) @(posedge clk); rstn = 1;
    rd(32'h00, d, e); chk("ID", d === 32'hFDA10101 && !e);
    rd(32'h0C, d, e); chk("GATE_LEN reset", d === 32'd125000000);
    rd(32'h10, d, e); chk("THR_HIGH reset", d === 32'd256);
    rd(32'h14, d, e); chk("THR_LOW reset", d === 32'hFFFFFF00);
    wr(32'h0C, 32'd10, e); rd(32'h0C, d, e); chk("GATE_LEN clamps to 1000", d === 32'd1000);
    rd(32'h1C + 32'h1000, d, e); chk("unmapped read errors", e === 1'b1 && d === 32'd0);
    wr(32'h00, 32'd5, e); chk("write to ID errors", e === 1'b1);
    wr(32'h0C, 32'd125000, e);                       // 1 ms gate
    rd(32'h28, n0, e);
    wr(32'h08, 32'd1, e); rd(32'h08, d, e); chk("START reads 0", d[0] === 1'b0);
    rd(32'h18, d, e); chk("BUSY after START", d[0] === 1'b1 && d[1] === 1'b0);
    wr(32'h08, 32'd1, e);                            // ignored while BUSY
    repeat (125100) @(posedge clk);
    rd(32'h18, d, e); chk("DONE and not BUSY", d[1] === 1'b1 && d[0] === 1'b0 && d[3:2] === 2'b00);
    rd(32'h28, n1, e); chk("MEAS_DONE +1", n1 - n0 === 32'd1);
    rd(32'h1C, edges, e); rd(32'h20, actual, e); rd(32'h24, span, e);
    chk("GATE_ACTUAL", actual === 32'd125000);
    chk("edges about 1000", edges >= 999 && edges <= 1001);
    fg = edges / (actual / 125.0e6); fr = (edges - 1) * 125.0e6 / span;
    $display("edges %0d actual %0d span %0d f_gate %f f_recip %f", edges, actual, span, fg, fr);
    chk("f_gate within 1100 ppm", (fg > 0.9989e6) && (fg < 1.0011e6));
    chk("f_recip within 100 ppm", (fr > 0.9999e6) && (fr < 1.0001e6));
    // thresholds in the wrong order
    wr(32'h10, 32'h3F00, e); rd(32'h10, d, e); chk("THR_HIGH sign-extended readback", d === 32'hFFFFFF00);
    wr(32'h08, 32'd1, e); repeat (125100) @(posedge clk);
    rd(32'h18, d, e); chk("BAD_THRESH set", d[3] === 1'b1); rd(32'h1C, d, e); chk("no edges when BAD_THRESH", d === 32'd0);
    wr(32'h10, 32'd256, e);
    // a flat input: FEW_EDGES
    amp = 0.0; wr(32'h08, 32'd1, e); repeat (125100) @(posedge clk);
    rd(32'h18, d, e); chk("FEW_EDGES on a flat input", d[2] === 1'b1 && d[3] === 1'b0); rd(32'h1C, d, e); chk("EDGES 0", d === 32'd0);
    if (fails == 0) $display("XCHECK PASS"); else $display("XCHECK FAIL %0d", fails);
    $finish;
  end
endmodule
