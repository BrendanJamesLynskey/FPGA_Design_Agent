// p2_mem_test: board top. jtag_bus + power-on reset + register core.
module p2_mem_test (
    input  logic       clk,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    // power-on reset: held for 8 clocks after configuration
    /* verilator lint_off PROCASSINIT */
    logic [3:0] por_cnt = 4'd0;
    logic       rst = 1'b1;
    /* verilator lint_on PROCASSINIT */
    always_ff @(posedge clk) begin
        if (!por_cnt[3]) por_cnt <= por_cnt + 4'd1;
        rst <= !por_cnt[3];
    end

    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;

    jtag_bus u_bus (.clk(clk), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                    .h_wdata(h_wdata), .h_rdata(h_rdata));

`ifndef SYNTHESIS
    // simulation/lint only: reference the supplied (read-only) jtag_bus's otherwise unused nets
    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_bus_nets;
    assign unused_bus_nets = u_bus.tdo ^ u_bus.cmd_s[45];
    /* verilator lint_on UNUSEDSIGNAL */
`endif

    p2_mem_test_core u_core (.clk(clk), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                             .h_wdata(h_wdata), .h_rdata(h_rdata), .led(led),
                             .sfp_tx_disable(sfp_tx_disable));
endmodule
