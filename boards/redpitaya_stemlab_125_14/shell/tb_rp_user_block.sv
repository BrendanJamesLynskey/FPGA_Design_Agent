// Self-checking test bench of rp_user_block (brief 225): iverilog -g2012 tb_rp_user_block.sv rp_user_block.sv; vvp prints TB PASS. Timing: the block answers in the cycle after wen or ren.
module tb;
  logic clk = 0, rstn = 0;
  logic [31:0] addr = 0, wdata = 0, rdata; logic wen = 0, ren = 0, err, ack;
  logic signed [13:0] a = -14'sd100, b = 14'sd77, da, db;
  rp_user_block dut(.clk(clk), .rstn(rstn), .sys_addr(addr), .sys_wdata(wdata), .sys_wen(wen), .sys_ren(ren), .sys_rdata(rdata), .sys_err(err), .sys_ack(ack),
                    .adc_a(a), .adc_b(b), .dac_a(da), .dac_b(db));
  always #4 clk = ~clk;
  int fails = 0;
  task wr(input [31:0] ad, input [31:0] d, output logic e);
    @(negedge clk); addr = ad; wdata = d; wen = 1; @(negedge clk); wen = 0; #1 e = err; if (!ack) begin $display("no ack on write"); fails++; end
  endtask
  task rd(input [31:0] ad, output [31:0] d, output logic e);
    @(negedge clk); addr = ad; ren = 1; @(negedge clk); ren = 0; #1 d = rdata; e = err; if (!ack) begin $display("no ack on read"); fails++; end
  endtask
  logic [31:0] d; logic e;
  initial begin
    repeat (3) @(posedge clk); rstn = 1;
    rd(32'h40700000, d, e); if (d !== 32'hFDA10001 || e) begin $display("ID %h %b", d, e); fails++; end
    wr(32'h40700004, 32'hCAFEF00D, e); rd(32'h40700004, d, e); if (d !== 32'hCAFEF00D || e) begin $display("SCRATCH %h", d); fails++; end
    rd(32'h40700008, d, e); if (d == 0 || e) begin $display("COUNT %h", d); fails++; end
    rd(32'h4070000C, d, e); if (d !== 32'hFFFFFF9C) begin $display("IN1 %h", d); fails++; end
    rd(32'h40700010, d, e); if (d !== 32'd77) begin $display("IN2 %h", d); fails++; end
    wr(32'h40700014, 32'h3FFF, e); if (da !== -14'sd1) begin $display("DAC1 %0d", da); fails++; end
    rd(32'h40700014, d, e); if (d !== 32'hFFFFFFFF) begin $display("DAC1 rb %h", d); fails++; end
    wr(32'h40700000, 32'h1, e); if (!e) begin $display("write to ID not an error"); fails++; end
    rd(32'h40700000, d, e); if (d !== 32'hFDA10001) begin $display("ID changed"); fails++; end
    rd(32'h4070001C, d, e); if (!e || d !== 0) begin $display("unmapped 0x1C no error"); fails++; end
    rd(32'h40700104, d, e); if (!e) begin $display("alias 0x104 no error"); fails++; end
    wr(32'h40700104, 32'h55, e); if (!e) begin $display("alias write no error"); fails++; end
    rd(32'h40700004, d, e); if (d !== 32'hCAFEF00D) begin $display("alias write hit SCRATCH"); fails++; end
    rstn = 0; repeat (2) @(posedge clk); #1 if (da !== 0) begin $display("reset"); fails++; end
    if (fails == 0) $display("TB PASS"); else $display("TB FAIL %0d", fails); $finish;
  end
endmodule
