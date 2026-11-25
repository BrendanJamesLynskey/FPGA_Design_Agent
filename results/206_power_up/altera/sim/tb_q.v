// Brief 206 Q10: what the post-fit gate-level netlist of q_top shows at power-up, before any clock edge, and after the
// resets. Functional simulation (Icarus Verilog with Quartus's atom libraries; no SDF): it shows the netlist's
// behaviour (power_up parameters and push-back inverters), not the silicon. Questa FSE needs a licence we do not have.
`timescale 1ns/1ps
module tb;
  reg [10:1] clk = 0; reg rst = 0;
  reg [7:0] d = 8'h00; reg [3:0] io_din = 4'h0; reg [17:0] ma = 0, mb = 0; reg rwe = 0; reg [7:0] rwa = 0, rra = 0;
  reg [15:0] rwd = 0; reg [63:0] d7 = 0, d8 = 0; reg inc9 = 0;
  wire [7:0] q1, q2, q3, q4; wire [3:0] io_dout; wire [35:0] mp; wire [15:0] rq; wire [63:0] q7, q8; wire [3:0] q9;
  q_top dut (.clk1(clk[1]), .clk2(clk[2]), .clk3(clk[3]), .clk4(clk[4]), .clk5(clk[5]), .clk6(clk[6]), .clk7(clk[7]),
             .clk8(clk[8]), .clk9(clk[9]), .clk10(clk[10]), .rst(rst), .d1(d), .d2(d), .d3(d), .d4(d), .q1(q1), .q2(q2),
             .q3(q3), .q4(q4), .io_din(io_din), .io_dout(io_dout), .ma(ma), .mb(mb), .mp(mp), .rwe(rwe), .rwa(rwa), .rra(rra),
             .rwd(rwd), .rq(rq), .d7(d7), .d8(d8), .q7(q7), .q8(q8), .inc9(inc9), .q9(q9));
  initial begin
    #5;
    $display("POWERUP q1=%h q2=%h q3=%h q4=%h io_dout=%h mp=%h rq=%h q7=%h q8=%h q9=%h", q1, q2, q3, q4, io_dout, mp, rq, q7, q8, q9);
    rst = 1; #2;
    $display("ASYNC_RST_HIGH q3=%h q4=%h", q3, q4);
    clk[2] = 1; #2 clk[2] = 0; #2;
    $display("SYNC_RST_EDGE q2=%h", q2);
    rst = 0; d = 8'h5A; #2 clk[1] = 1; clk[2] = 1; clk[3] = 1; clk[4] = 1; #2 clk = 0; #2;
    $display("AFTER_EDGE_D5A q1=%h q2=%h q3=%h q4=%h", q1, q2, q3, q4);
    $finish;
  end
endmodule
