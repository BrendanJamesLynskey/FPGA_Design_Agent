// freq_meter_top: board top. Clock buffers, power-up reset, jtag_bus and the register core.
module freq_meter_top (
    input  logic       clk_c3_in,
    input  logic       mgtrefclk0_p,
    input  logic       mgtrefclk0_n,
    output logic [1:0] led,
    output logic       sfp_tx_disable,
    // spec-declared register-port names (internal in the spec; unused inputs, mirrored read data)
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata
);
    logic clk_c3;
    BUFG u_bufg_c3 (.I(clk_c3_in), .O(clk_c3));

    logic refclk_odiv2, refclk_o, clk_ref;
    IBUFDS_GTE4 #(.REFCLK_EN_TX_PATH(1'b0), .REFCLK_HROW_CK_SEL(2'b00), .REFCLK_ICNTL_RX(2'b00)) u_ibufds_gt (
        .I(mgtrefclk0_p), .IB(mgtrefclk0_n), .CEB(1'b0), .O(refclk_o), .ODIV2(refclk_odiv2));
    BUFG_GT u_bufg_gt (.I(refclk_odiv2), .CE(1'b1), .CEMASK(1'b0), .CLR(1'b0), .CLRMASK(1'b0),
                       .DIV(3'b000), .O(clk_ref));

    // power-up reset: held for 8 clk_c3 cycles
    /* verilator lint_off PROCASSINIT */
    logic [7:0] rst_sr = 8'hFF;
    /* verilator lint_on PROCASSINIT */
    logic       rst;
    always_ff @(posedge clk_c3) rst_sr <= {rst_sr[6:0], 1'b0};
    assign rst = rst_sr[7];

    logic        b_we, b_re;
    logic [11:0] b_addr;
    logic [31:0] b_wdata, b_rdata;
    jtag_bus u_bus (.clk(clk_c3), .rst(rst), .h_we(b_we), .h_re(b_re), .h_addr(b_addr),
                    .h_wdata(b_wdata), .h_rdata(b_rdata));

    freq_meter_core u_core (.clk(clk_c3), .clk_ref(clk_ref), .rst(rst), .h_we(b_we), .h_re(b_re),
                            .h_addr(b_addr), .h_wdata(b_wdata), .h_rdata(b_rdata), .led(led),
                            .sfp_tx_disable(sfp_tx_disable));

    // spec-declared register-port names: mirror the internal bus (input ports unused)
    assign h_rdata = b_rdata;

    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_ok;
    assign unused_ok = refclk_o ^ h_we ^ h_re ^ (^h_addr) ^ (^h_wdata);
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
