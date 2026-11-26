// freq_meter_top: thin top. GT refclk buffer, reset generator, jtag_bus, core.
/* verilator lint_off DECLFILENAME */
/* verilator lint_off PINCONNECTEMPTY */
/* verilator lint_off PROCASSINIT */
module rst_gen (
    input  logic clk,
    output logic rst
);
    logic [3:0] cnt = 4'd0;
    always_ff @(posedge clk) if (!cnt[3]) cnt <= cnt + 4'd1;
    assign rst = !cnt[3];
endmodule

module freq_meter_top (
    input  logic       ref_clk_p,
    input  logic       ref_clk_n,
    input  logic       c3_clk,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    logic ref_odiv2, ref_clk, rst;
    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;

    IBUFDS_GTE4 u_ibuf (.I(ref_clk_p), .IB(ref_clk_n), .CEB(1'b0), .O(), .ODIV2(ref_odiv2));
    BUFG_GT u_bufg (.I(ref_odiv2), .CE(1'b1), .CEMASK(1'b0), .CLR(1'b0), .CLRMASK(1'b0),
                    .DIV(3'b000), .O(ref_clk));

    rst_gen u_rst (.clk(ref_clk), .rst(rst));

    jtag_bus u_bus (.clk(ref_clk), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                    .h_wdata(h_wdata), .h_rdata(h_rdata));

`ifndef SYNTHESIS
    // Simulation/lint only: reference the supplied (read-only) jtag_bus's deliberately unused signals.
    /* verilator lint_off UNUSEDSIGNAL */
    logic jtag_unused_sink;
    /* verilator lint_on UNUSEDSIGNAL */
    assign jtag_unused_sink = u_bus.tdo ^ u_bus.cmd_s[45];
`endif

    freq_meter_core u_core (.clk(ref_clk), .rst(rst), .c3_clk(c3_clk), .h_we(h_we), .h_re(h_re),
                            .h_addr(h_addr), .h_wdata(h_wdata), .h_rdata(h_rdata), .led(led),
                            .sfp_tx_disable(sfp_tx_disable));
endmodule
