// Board top: reset generator, jtag_bus, GT reference clock buffers and the register core.
module p6_clkmux_top (
    input  logic       clk,
    input  logic       gtref_p,
    input  logic       gtref_n,
    output logic       sfp_tx_disable,
    output logic [1:0] led
);
    localparam int unsigned B_DIV = 1;

    // power-on reset, 8 clk cycles
    /* verilator lint_off PROCASSINIT */
    logic [3:0] rst_cnt = 4'd0;
    logic       rst = 1'b1;
    always_ff @(posedge clk) begin
        if (rst_cnt == 4'd8) rst <= 1'b0;
        else rst_cnt <= rst_cnt + 4'd1;
    end

    // clock B: GT reference through IBUFDS_GTE4 and BUFG_GT
    /* verilator lint_off UNUSEDSIGNAL */
    logic gt_odiv2;
    /* verilator lint_on UNUSEDSIGNAL */
    logic gt_o, clk_b;
    IBUFDS_GTE4 #(.REFCLK_EN_TX_PATH(1'b0), .REFCLK_HROW_CK_SEL(2'b00), .REFCLK_ICNTL_RX(2'b00)) u_ibufds (
        .O(gt_o), .ODIV2(gt_odiv2), .CEB(1'b0), .I(gtref_p), .IB(gtref_n));
    BUFG_GT u_bufg_gt (
        .O(clk_b), .CE(1'b1), .CEMASK(1'b0), .CLR(1'b0), .CLRMASK(1'b0),
        .DIV(3'(B_DIV - 1)), .I(gt_o));

    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;

    jtag_bus u_jtag (.clk(clk), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                     .h_wdata(h_wdata), .h_rdata(h_rdata));

    p6_clkmux_core #(.B_DIV(B_DIV)) u_core (
        .clk(clk), .rst(rst), .clk_b(clk_b), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
        .h_wdata(h_wdata), .h_rdata(h_rdata), .led(led), .sfp_tx_disable(sfp_tx_disable));
endmodule
