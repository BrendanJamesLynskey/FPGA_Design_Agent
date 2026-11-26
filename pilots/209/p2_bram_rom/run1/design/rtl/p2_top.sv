// p2_top: power-on reset, jtag_bus and p2_core.
// The h_* ports are the spec's internal register-port names; they are declared on the
// top because the spec lists them, and are unused (the real bus is wired internally).
module p2_top #(
    parameter int unsigned POR_CYCLES = 8
) (
    input  logic       clk,
    output logic [1:0] led,
    output logic       sfp_tx_disable,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    input  logic [31:0] h_rdata
    /* verilator lint_on UNUSEDSIGNAL */
);
    /* verilator lint_off PROCASSINIT */
    logic [3:0] por_cnt = 4'd0;
    logic       rst = 1'b1;
    /* verilator lint_on PROCASSINIT */
    always_ff @(posedge clk) begin
        if (por_cnt == 4'(POR_CYCLES)) rst <= 1'b0;
        else por_cnt <= por_cnt + 4'd1;
    end

    logic        b_we, b_re;
    logic [11:0] b_addr;
    logic [31:0] b_wdata, b_rdata;

    /* verilator lint_off UNUSEDSIGNAL */
    jtag_bus u_bus (.clk(clk), .rst(rst), .h_we(b_we), .h_re(b_re), .h_addr(b_addr),
                    .h_wdata(b_wdata), .h_rdata(b_rdata));
    /* verilator lint_on UNUSEDSIGNAL */

    p2_core u_core (.clk(clk), .rst(rst), .h_we(b_we), .h_re(b_re), .h_addr(b_addr),
                    .h_wdata(b_wdata), .h_rdata(b_rdata), .led(led), .sfp_tx_disable(sfp_tx_disable));
endmodule
