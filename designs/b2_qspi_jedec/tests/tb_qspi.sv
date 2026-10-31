// tb_qspi.sv: simulation wrapper for qspi_regs; the cocotb flash model drives dq1.
// (On the board SCK leaves through STARTUPE2; here it is a plain output.)
module tb_qspi #(
    parameter int HALF     = 4,
    parameter int PREAMBLE = 8
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    output logic        sck,
    output logic        cs_n,
    output logic        dq0,
    input  logic        dq1
);
    qspi_regs #(.HALF(HALF), .PREAMBLE(PREAMBLE)) u_regs (
        .clk(clk), .rst(rst), .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata),
        .sck(sck), .cs_n(cs_n), .dq0(dq0), .dq1(dq1));
endmodule
