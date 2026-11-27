// p5_async_fifo_soak: board top. Thin: clock buffers, power-up reset, jtag_bus (unchanged, data/jtag_bus.sv) and p5_core.
module p5_async_fifo_soak #(
    parameter int DATA_WIDTH           = 32,
    parameter int FIFO_DEPTH           = 512,
    parameter int PRBS_SEED            = 2147483647,
    parameter int DESIGN_ID            = 546635777,
    parameter int SLOW_READ_DIV_CYCLES = 8,
    parameter int RST_HOLD_CYCLES      = 8
) (
    input  logic       clk_c3,
    input  logic       gt_refclk_p,
    input  logic       gt_refclk_n,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    logic        clk;
    logic        rst;
    logic        gt_clk;
    /* verilator lint_off UNUSEDSIGNAL */
    logic        gt_o;
    /* verilator lint_on UNUSEDSIGNAL */
    logic        gt_odiv2;
    logic        h_we;
    logic        h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata;
    logic [31:0] h_rdata;

    BUFG u_bufg_c3 (.I(clk_c3), .O(clk));

    // SFP+ MGTREFCLK0: reference clock buffer only, no transceiver channel. ODIV2 (= O with the default HROW select) goes to the fabric.
    IBUFDS_GTE4 #(.REFCLK_EN_TX_PATH(1'b0), .REFCLK_HROW_CK_SEL(2'b00), .REFCLK_ICNTL_RX(2'b00)) u_ibufds_gt (
        .I(gt_refclk_p), .IB(gt_refclk_n), .CEB(1'b0), .O(gt_o), .ODIV2(gt_odiv2));
    BUFG_GT u_bufg_gt (.CE(1'b1), .CEMASK(1'b0), .CLR(1'b0), .CLRMASK(1'b0), .DIV(3'b000), .I(gt_odiv2), .O(gt_clk));

    rst_gen #(.HOLD(RST_HOLD_CYCLES)) u_rst_gen (.clk(clk), .rst(rst));

    jtag_bus u_jtag_bus (
        .clk(clk), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata));

    p5_core #(
        .DATA_WIDTH(DATA_WIDTH), .FIFO_DEPTH(FIFO_DEPTH), .PRBS_SEED(31'(PRBS_SEED)),
        .DESIGN_ID(32'(DESIGN_ID)), .SLOW_READ_DIV_CYCLES(SLOW_READ_DIV_CYCLES)
    ) u_core (
        .clk(clk), .rst(rst), .gt_clk(gt_clk), .h_we(h_we), .h_re(h_re), .h_addr(h_addr), .h_wdata(h_wdata),
        .h_rdata(h_rdata), .led(led), .sfp_tx_disable(sfp_tx_disable));
endmodule
