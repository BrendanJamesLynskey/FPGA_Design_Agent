// top: a clock primitive and the core. The primitive has no definition here, so open-source Yosys cannot elaborate this module.
module top (input logic clk25, output logic [1:0] led);
    logic clk, locked, rst;
    MMCME4_BASE u_mmcm (.CLKIN1(clk25), .CLKOUT0(clk), .LOCKED(locked));
    assign rst = !locked;
    logic [31:0] rd;
    reg_core u_core (.clk(clk), .rst(rst), .h_we(1'b0), .h_addr(12'd0), .h_wdata(32'd0), .h_rdata(rd));
    assign led = rd[1:0];
endmodule
