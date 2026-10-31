// tb_tmp.sv: simulation wrapper for tmp_regs: the open-drain I2C bus (wired AND of
// the master and the device model's pulls, as the board's pull-ups make it).
module tb_tmp #(
    parameter int QUARTER = 5
) (
    input  logic        clk,
    input  logic        rst,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata,
    input  logic        dev_scl_pull,    // driven by the cocotb device model
    input  logic        dev_sda_pull,
    output logic        scl,
    output logic        sda
);
    logic scl_oe, sda_oe;
    assign scl = ~(scl_oe | dev_scl_pull);
    assign sda = ~(sda_oe | dev_sda_pull);
    tmp_regs #(.QUARTER(QUARTER), .DEV_ADDR(7'h4B)) u_regs (
        .clk(clk), .rst(rst), .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata),
        .scl_oe(scl_oe), .sda_oe(sda_oe), .scl_in(scl), .sda_in(sda));
endmodule
