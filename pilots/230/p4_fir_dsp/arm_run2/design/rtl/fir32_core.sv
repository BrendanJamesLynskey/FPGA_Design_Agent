// Simulated toplevel of the register core: thin wrapper around fir_core.
module fir32_core (
    input  logic        clk25,
    input  logic        clk_dp,
    input  logic        rst,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    fir_core u_fir_core (.clk25(clk25), .clk_dp(clk_dp), .rst(rst), .h_we(h_we), .h_re(h_re),
                         .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata), .led(led),
                         .sfp_tx_disable(sfp_tx_disable));
endmodule
