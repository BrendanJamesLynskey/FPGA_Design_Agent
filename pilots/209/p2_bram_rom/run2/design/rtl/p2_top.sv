// p2_top: thin board top: reset generator, jtag_bus and p2_core.
module p2_top (
    input  logic       clk,

    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    // power-on reset: high for 8 clocks after configuration
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

    p2_core u_core (.clk(clk), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                    .h_wdata(h_wdata), .h_rdata(h_rdata), .led(led), .sfp_tx_disable(sfp_tx_disable));
endmodule
