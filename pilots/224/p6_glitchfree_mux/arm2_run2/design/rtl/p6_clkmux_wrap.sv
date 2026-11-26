// Simulated toplevel name used by the bench; the logic is in clkmux_core (architecture.yaml).
/* verilator lint_off DECLFILENAME */
module p6_clkmux_core #(
    parameter int unsigned DESIGN_ID        = 546701313,
    parameter int unsigned B_DIV            = 1,
    parameter int unsigned GATE_LEN_DEFAULT = 25000000
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        clk_b,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    clkmux_core #(.DESIGN_ID(DESIGN_ID), .B_DIV(B_DIV), .GATE_LEN_DEFAULT(GATE_LEN_DEFAULT)) u_core (
        .clk(clk), .rst(rst), .clk_b(clk_b), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
        .h_wdata(h_wdata), .h_rdata(h_rdata), .led(led), .sfp_tx_disable(sfp_tx_disable));
endmodule
