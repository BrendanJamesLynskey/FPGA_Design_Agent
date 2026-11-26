// Board top: jtag_bus, start-up reset, soak core, GT reference clock buffer.
module p5_async_fifo_soak (
    input  logic       clk_25,
    input  logic       mgtrefclk0_p,
    input  logic       mgtrefclk0_n,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    logic clk_rd_odiv2, clk_rd_unused, clk_rd;
    IBUFDS_GTE4 #(.REFCLK_EN_TX_PATH(1'b0), .REFCLK_HROW_CK_SEL(2'b00), .REFCLK_ICNTL_RX(2'b00)) u_refclk (
        .O(clk_rd_unused), .ODIV2(clk_rd_odiv2), .CEB(1'b0), .I(mgtrefclk0_p), .IB(mgtrefclk0_n));
    BUFG_GT u_bufg (.O(clk_rd), .CE(1'b1), .CEMASK(1'b0), .CLR(1'b0), .CLRMASK(1'b0), .DIV(3'b000),
                    .I(clk_rd_odiv2));

    // jtag_bus reset: high for a few clocks after configuration
    logic [3:0] rst_sr = 4'hF;
    always_ff @(posedge clk_25) rst_sr <= {rst_sr[2:0], 1'b0};

    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;

    jtag_bus u_bus (.clk(clk_25), .rst(rst_sr[3]), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                    .h_wdata(h_wdata), .h_rdata(h_rdata));

    soak_core u_core (
        .clk_wr(clk_25), .clk_rd(clk_rd), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
        .h_wdata(h_wdata), .h_rdata(h_rdata), .led(led), .sfp_tx_disable(sfp_tx_disable));

    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_o;
`ifdef SYNTHESIS
    assign unused_o = clk_rd_unused;
`else
    // simulation only: touch the supplied bus's otherwise-unused nets (it cannot be edited)
    assign unused_o = clk_rd_unused ^ u_bus.tdo ^ u_bus.cmd_s[45];
`endif
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
