// Board top: jtag_bus, power-up reset generator, GT reference clock buffer and the soak core.
/* verilator lint_off PROCASSINIT */
/* verilator lint_off UNUSEDSIGNAL */
module p5_async_fifo_soak #(
    parameter int RESET_HOLD_CYCLES = 8
) (
    input  logic       clk_c3,
    input  logic       gt_refclk_p,
    input  logic       gt_refclk_n,
    output logic [1:0] led,
    output logic       sfp_tx_disable,
    // spec-declared register-port names; the live port is wired internally to jtag_bus
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,

    output logic [31:0] h_rdata
);
    // power-up reset, active high, synchronous to clk_c3
    logic [4:0] hold = 5'(RESET_HOLD_CYCLES);
    logic       rst  = 1'b1;
    always_ff @(posedge clk_c3) begin
        if (hold != 5'd0) hold <= hold - 5'd1;
        rst <= (hold != 5'd0);
    end

    // reader clock from the SFP+ MGTREFCLK0 (no GT channel)
    logic refclk, refclk_div2, clk_gt156;
    IBUFDS_GTE4 u_ibufds_gt (.I(gt_refclk_p), .IB(gt_refclk_n), .CEB(1'b0), .O(refclk), .ODIV2(refclk_div2));
    BUFG_GT u_bufg_gt (.I(refclk_div2), .CE(1'b1), .CEMASK(1'b0), .CLR(1'b0), .CLRMASK(1'b0), .DIV(3'b000),
                       .O(clk_gt156));

    logic        b_we, b_re;
    logic [11:0] b_addr;
    logic [31:0] b_wdata, b_rdata;

    jtag_bus u_bus (.clk(clk_c3), .rst(rst), .h_we(b_we), .h_re(b_re), .h_addr(b_addr), .h_wdata(b_wdata),
                    .h_rdata(b_rdata));

    assign h_rdata = b_rdata;

    soak_core u_core (.clk_c3(clk_c3), .clk_gt156(clk_gt156), .rst(rst), .h_we(b_we), .h_re(b_re),
                      .h_addr(b_addr), .h_wdata(b_wdata), .h_rdata(b_rdata), .led(led),
                      .sfp_tx_disable(sfp_tx_disable));
endmodule
