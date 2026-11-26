// p6_clkmux_top: thin top: reset generator, jtag_bus, GT reference buffers, register core.
module p6_clkmux_top #(
    parameter logic [31:0] ID_VALUE          = 32'h20960001,
    parameter int          B_DIV             = 1,
    parameter logic [31:0] GATE_LEN_DEFAULT  = 32'd25000000,
    parameter int          RST_HOLD_CYCLES   = 16
) (
    input  logic       clk_c3,
    input  logic       gtref_p,
    input  logic       gtref_n,
    output logic [1:0] led,
    output logic       sfp_tx_disable
);
    // power-on reset: held RST_HOLD_CYCLES clocks, synchronous
    /* verilator lint_off PROCASSINIT */
    logic [4:0] rcnt = 5'd0;
    logic       rst = 1'b1;
    /* verilator lint_on PROCASSINIT */
    always_ff @(posedge clk_c3) begin
        if (rcnt == 5'(RST_HOLD_CYCLES - 1)) rst <= 1'b0;
        else rcnt <= rcnt + 5'd1;
    end

    logic        h_we, h_re;
    logic [11:0] h_addr;
    logic [31:0] h_wdata, h_rdata;
    jtag_bus u_bus (.clk(clk_c3), .rst(rst), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
                    .h_wdata(h_wdata), .h_rdata(h_rdata));

    logic gt_o, gt_odiv2, clk_b;
    IBUFDS_GTE4 u_ibufds (.I(gtref_p), .IB(gtref_n), .CEB(1'b0), .O(gt_o), .ODIV2(gt_odiv2));
    BUFG_GT u_bufg_gt (.I(gt_o), .CE(1'b1), .CEMASK(1'b0), .CLR(1'b0), .CLRMASK(1'b0),
                       .DIV(3'(B_DIV - 1)), .O(clk_b));

    p6_clkmux_core #(.ID_VALUE(ID_VALUE), .B_DIV(B_DIV), .GATE_LEN_DEFAULT(GATE_LEN_DEFAULT)) u_core (
        .clk(clk_c3), .rst(rst), .clk_b(clk_b), .h_we(h_we), .h_re(h_re), .h_addr(h_addr),
        .h_wdata(h_wdata), .h_rdata(h_rdata), .led(led), .sfp_tx_disable(sfp_tx_disable));

    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_odiv2;
    assign unused_odiv2 = gt_odiv2;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
