// Board top: jtag_bus, power-on reset, GT reference clock buffer, and the register core.
/* verilator lint_off PROCASSINIT */
/* verilator lint_off SYNCASYNCNET */
module top (
    input  logic       clk_25,
    input  logic       gt_refclk_p,
    input  logic       gt_refclk_n,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    // power-on reset: held for 8 clk_25 cycles after configuration
    logic [3:0] por_cnt = 4'd0;
    logic       rst;
    always_ff @(posedge clk_25) if (!por_cnt[3]) por_cnt <= por_cnt + 4'd1;
    assign rst = !por_cnt[3];

    // reader clock: SFP+ MGTREFCLK0 through IBUFDS_GTE4 and BUFG_GT (no transceiver channel)
    logic gt_odiv2, gt_o, gt_clk;
    IBUFDS_GTE4 #(.REFCLK_EN_TX_PATH(1'b0), .REFCLK_HROW_CK_SEL(2'b00), .REFCLK_ICNTL_RX(2'b00)) u_ibufds (
        .I(gt_refclk_p), .IB(gt_refclk_n), .CEB(1'b0), .O(gt_o), .ODIV2(gt_odiv2));
    BUFG_GT u_bufg (.CE(1'b1), .CEMASK(3'b000), .CLR(1'b0), .CLRMASK(3'b000), .DIV(3'b000), .I(gt_odiv2), .O(gt_clk));

    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;

    jtag_bus u_bus (.clk(clk_25), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                    .h_wdata(h_wdata), .h_rdata(h_rdata));

    p5_async_fifo_core u_core (
        .clk_25(clk_25), .gt_refclk(gt_clk), .rst(rst),
        .h_we(h_we), .h_re(h_re), .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata),
        .led(led), .sfp_tx_disable(sfp_tx_disable));

    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_ok;
`ifndef SYNTHESIS
    // Lint only: the supplied read-only jtag_bus.sv leaves tdo and cmd_s[45] unread in simulation.
    assign unused_ok = gt_o ^ u_bus.tdo ^ u_bus.cmd_s[45];
`else
    assign unused_ok = gt_o;
`endif
endmodule

