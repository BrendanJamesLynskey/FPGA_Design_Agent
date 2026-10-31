// tb_mic.sv: simulation wrapper for mic_regs; the cocotb microphone model drives mdata.
module tb_mic #(
    parameter int HALF = 4
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic        mclk,
    input  logic        mdata
);
    mic_regs #(.HALF(HALF)) u_regs (
        .clk(clk), .rst(rst), .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata), .mclk(mclk), .mdata(mdata));
endmodule
