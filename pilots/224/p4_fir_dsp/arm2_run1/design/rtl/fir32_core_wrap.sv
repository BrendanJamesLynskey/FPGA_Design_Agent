// Simulated toplevel name for the register core (fir_core holds the logic).
/* verilator lint_off DECLFILENAME */
module fir32_core (
    input  logic        clk_bus,
    input  logic        clk_dp,
    input  logic        rst_bus,
    input  logic        rst_dp,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    fir_core u_fir_core (
        .clk_bus(clk_bus), .clk_dp(clk_dp), .rst_bus(rst_bus), .rst_dp(rst_dp),
        .h_we(h_we), .h_re(h_re), .h_addr(h_addr), .h_wdata(h_wdata),
        .h_rdata(h_rdata), .led(led), .sfp_tx_disable(sfp_tx_disable));
endmodule
