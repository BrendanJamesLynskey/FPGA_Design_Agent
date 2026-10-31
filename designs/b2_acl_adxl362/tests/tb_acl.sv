// tb_acl.sv: simulation wrapper for acl_regs; the cocotb ADXL362 model drives miso.
module tb_acl #(
    parameter int HALF = 4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic        sclk,
    output logic        mosi,
    output logic        cs_n,
    input  logic        miso
);
    acl_regs #(.HALF(HALF)) u_regs (
        .clk(clk), .rst(rst), .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata),
        .sclk(sclk), .mosi(mosi), .cs_n(cs_n), .miso(miso));
endmodule
