// Top: clock buffers, power-up reset generator, jtag_bus and the register core only.
// The supplied data/jtag_bus.sv (read-only) leaves tdo and cmd_s[45] unused in simulation.
/* verilator lint_off UNUSEDSIGNAL */
module p5_async_fifo_soak (
    input  logic       clk_c3,
    input  logic       gt_refclk_p,
    input  logic       gt_refclk_n,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    logic clk_wr, clk_rd, refclk_o;

    BUFG u_bufg_wr (.I(clk_c3), .O(clk_wr));
    /* verilator lint_off PINCONNECTEMPTY */
    IBUFDS_GTE4 u_ibufds (.I(gt_refclk_p), .IB(gt_refclk_n), .CEB(1'b0), .O(), .ODIV2(refclk_o));
    /* verilator lint_on PINCONNECTEMPTY */
    // GT reference clock reaches the fabric only through BUFG_GT (ODIV2 = refclk / 1)
    BUFG_GT u_bufg_rd (.I(refclk_o), .CE(1'b1), .CEMASK(1'b0), .CLR(1'b0), .CLRMASK(1'b0),
                       .DIV(3'b000), .O(clk_rd));

    // power-up reset: held for 16 clk_wr clocks from the configuration initial values
    logic [4:0] por_cnt = 5'd0;
    logic       rst     = 1'b1;
    always_ff @(posedge clk_wr) begin
        if (!por_cnt[4]) por_cnt <= por_cnt + 5'd1;
        rst <= !por_cnt[4];
    end

    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;

    logic rst_j = 1'b1;
    always_ff @(posedge clk_wr) rst_j <= !por_cnt[4];

    jtag_bus u_jtag (.clk(clk_wr), .rst(rst_j), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                     .h_wdata(h_wdata), .h_rdata(h_rdata));

`ifndef SYNTHESIS
    // simulation only: mark the supplied jtag_bus's unused internals as observed for lint
    logic sink_unused;
    assign sink_unused = u_jtag.tdo ^ (^u_jtag.cmd_s[45]);
`endif

    p5_async_fifo_soak_core u_core (
        .clk_wr(clk_wr), .clk_rd(clk_rd), .rst(rst),
        .h_we(h_we), .h_re(h_re), .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata),
        .led(led), .sfp_tx_disable(sfp_tx_disable));
endmodule
