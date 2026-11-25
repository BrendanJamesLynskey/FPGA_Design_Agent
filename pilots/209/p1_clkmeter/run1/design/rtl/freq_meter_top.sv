// Thin top: clock buffers, reset generator, jtag_bus and the core.
module freq_meter_top (
    input  logic       clk_c3,
    input  logic       mgtrefclk0_p,
    input  logic       mgtrefclk0_n,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    logic clk, clk_ref, ref_raw, ref_odiv2;
    BUFG u_bufg_c3 (.I(clk_c3), .O(clk));
    IBUFDS_GTE4 #(.REFCLK_EN_TX_PATH(1'b0), .REFCLK_HROW_CK_SEL(2'b00), .REFCLK_ICNTL_RX(2'b00)) u_ibufds (
        .I(mgtrefclk0_p), .IB(mgtrefclk0_n), .CEB(1'b0), .O(ref_raw), .ODIV2(ref_odiv2));
    BUFG_GT u_bufg_ref (.I(ref_odiv2), .CE(1'b1), .CEMASK(1'b0), .CLR(1'b0), .CLRMASK(1'b0), .DIV(3'b000), .O(clk_ref));

    // reset generator: held high for the first clocks after configuration
    /* verilator lint_off PROCASSINIT */
    logic [3:0] rst_cnt = 4'd0;
    logic       rst = 1'b1;
    /* verilator lint_on PROCASSINIT */
    always_ff @(posedge clk) begin
        if (rst_cnt != 4'hF) rst_cnt <= rst_cnt + 4'd1;
        rst <= (rst_cnt != 4'hF);
    end

    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;
    jtag_bus u_jtag (.clk(clk), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                     .h_wdata(h_wdata), .h_rdata(h_rdata));

    freq_meter_core u_core (.clk(clk), .clk_ref(clk_ref), .rst(rst), .h_we(h_we), .h_re(h_re),
                            .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata),
                            .led(led), .sfp_tx_disable(sfp_tx_disable));

    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_odiv2;
    logic unused_raw;
    assign unused_odiv2 = ref_odiv2;
    assign unused_raw = ref_raw;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
