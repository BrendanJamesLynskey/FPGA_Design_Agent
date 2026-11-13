// kr260_gth_top.sv: the SFP+ transceiver design on the Kria KR260 carrier (brief 56A): one GTH lane, J24 cage.
//
// Clock plan: the 25 MHz HPA input (an open-source reference design's figure for this pin; unconfirmed against the
// schematic, as in designs/b58a_trigger) -> MMCM -> 100 MHz free-running clock for the GT reset helper, the DRP and the host
// registers. The 156.25 MHz reference on MGTREFCLK0 of quad 224 (also unconfirmed against the schematic) feeds the QPLL.
// The PS is not used: the host reaches the registers over the JTAG cable (jtag_bus, reused from b58a_trigger).
// The laser starts disabled: sfp_tx_disable resets to 1 (SFF convention for a high-active disable; polarity on this carrier is
// unconfirmed, docs/board_run_plan.md step 1).
module kr260_gth_top #(
    parameter logic [31:0] BUILD_STAMP = 32'h0
) (
    input  logic       clk_25,
    input  logic       sfp_mgt_refclk_p,
    input  logic       sfp_mgt_refclk_n,
    input  logic       sfp_rx_p,
    input  logic       sfp_rx_n,
    output logic       sfp_tx_p,
    output logic       sfp_tx_n,
    output logic       sfp_tx_disable,
    input  logic       sfp_mod_abs,
    input  logic       sfp_rx_los,
    input  logic       sfp_tx_fault,
    inout  wire        sfp_i2c_scl,
    inout  wire        sfp_i2c_sda,
    output logic [1:0] led
);
    logic clk, locked, fb, clk_u, rst, refclk;
`ifdef SYNTHESIS
    MMCME4_BASE #(.CLKIN1_PERIOD(40.0), .CLKFBOUT_MULT_F(40.0), .DIVCLK_DIVIDE(1), .CLKOUT0_DIVIDE_F(10.0)) u_mmcm (
        .CLKIN1(clk_25), .CLKFBIN(fb), .CLKFBOUT(fb), .CLKFBOUTB(), .CLKOUT0(clk_u), .CLKOUT0B(), .CLKOUT1(), .CLKOUT1B(),
        .CLKOUT2(), .CLKOUT2B(), .CLKOUT3(), .CLKOUT3B(), .CLKOUT4(), .CLKOUT5(), .CLKOUT6(), .LOCKED(locked),
        .PWRDWN(1'b0), .RST(1'b0));
    BUFG u_bg (.I(clk_u), .O(clk));
    IBUFDS_GTE4 #(.REFCLK_EN_TX_PATH(1'b0), .REFCLK_HROW_CK_SEL(2'b00), .REFCLK_ICNTL_RX(2'b00)) u_ref (
        .I(sfp_mgt_refclk_p), .IB(sfp_mgt_refclk_n), .CEB(1'b0), .O(refclk), .ODIV2());
`else
    logic [4:0] lk = 5'd0;
    always_ff @(posedge clk_25) if (!lk[4]) lk <= lk + 5'd1;
    assign clk = clk_25; assign locked = lk[4]; assign clk_u = 1'b0; assign fb = 1'b0;
    assign refclk = sfp_mgt_refclk_p;
`endif
    xpm_cdc_sync_rst #(.DEST_SYNC_FF(4), .INIT(1), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0)) u_rst (
        .src_rst(!locked), .dest_clk(clk), .dest_rst(rst));

    // SFP+ control and I2C pins (open drain: the carrier's pull-ups, unconfirmed, set the high level)
    logic scl_low, sda_low, scl_i, sda_i;
    assign sfp_i2c_scl = scl_low ? 1'b0 : 1'bz;
    assign sfp_i2c_sda = sda_low ? 1'b0 : 1'bz;
    assign scl_i = sfp_i2c_scl;
    assign sda_i = sfp_i2c_sda;

    // SYSMON on the clk DRP: die temperature and rails for the operating-conditions record
    logic        sm_en, sm_rdy;
    logic [7:0]  sm_addr;
    logic [15:0] sm_do;
`ifdef SYNTHESIS
    SYSMONE4 #(.SIM_MONITOR_FILE("none"), .SIM_DEVICE("ZYNQ_ULTRASCALE")) u_sysmon (
        .DCLK(clk), .DEN(sm_en), .DWE(1'b0), .DADDR(sm_addr), .DI(16'h0), .DO(sm_do), .DRDY(sm_rdy),
        .RESET(rst), .CONVST(1'b0), .CONVSTCLK(1'b0), .VP(1'b0), .VN(1'b0), .VAUXP(16'h0), .VAUXN(16'h0),
        .ALM(), .OT(), .BUSY(), .CHANNEL(), .EOC(), .EOS(), .JTAGBUSY(), .JTAGLOCKED(), .JTAGMODIFIED(),
        .MUXADDR(), .ADC_DATA(), .I2C_SCLK(1'b1), .I2C_SDA(1'b1), .I2C_SCLK_TS(), .I2C_SDA_TS(), .SMBALERT_TS());
`else
    assign sm_do = 16'h0; assign sm_rdy = sm_en;
`endif

    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;
    jtag_bus u_jtag (.clk, .rst, .h_we, .h_re, .h_addr, .h_wdata, .h_rdata);

    gth_serdes_core #(.BUILD_STAMP(BUILD_STAMP)) u_core (.clk, .rst, .h_we, .h_re, .h_addr, .h_wdata, .h_rdata,
        .refclk, .rx_p(sfp_rx_p), .rx_n(sfp_rx_n), .tx_p(sfp_tx_p), .tx_n(sfp_tx_n),
        .sfp_tx_disable, .sfp_mod_abs, .sfp_rx_los, .sfp_tx_fault,
        .i2c_scl_low(scl_low), .i2c_sda_low(sda_low), .i2c_scl_i(scl_i), .i2c_sda_i(sda_i),
        .sm_en, .sm_addr, .sm_do, .sm_rdy, .led);
endmodule
