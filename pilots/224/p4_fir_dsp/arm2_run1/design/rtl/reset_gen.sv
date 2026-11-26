// Reset generator: power-on reset for the bus domain (active high), and a reset for the
// datapath domain that is asserted asynchronously (from the bus reset or MMCM not locked)
// and released synchronously by xpm_cdc_async_rst. The asynchronous input comes straight
// from one register (no logic before the synchroniser).
module reset_gen (
    input  logic clk_bus,
    input  logic clk_dp,
    input  logic locked,
    output logic rst_bus,
    output logic rst_dp
);
    /* verilator lint_off PROCASSINIT */
    logic [3:0] por_cnt = 4'hF;
    logic       rst_bus_r = 1'b1;
    logic       rst_arst_r = 1'b1;   // separate copy feeding the asynchronous input
    (* ASYNC_REG = "TRUE" *) logic lock_s1 = 1'b0;
    (* ASYNC_REG = "TRUE" *) logic lock_s2 = 1'b0;
    /* verilator lint_on PROCASSINIT */
    always_ff @(posedge clk_bus) begin
        if (por_cnt != 4'h0) por_cnt <= por_cnt - 4'h1;
        rst_bus_r  <= (por_cnt != 4'h0);
        lock_s1    <= locked;
        lock_s2    <= lock_s1;
        rst_arst_r <= (por_cnt != 4'h0) || !lock_s2;
    end
    assign rst_bus = rst_bus_r;

    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst_dp (
        .dest_arst(rst_dp), .dest_clk(clk_dp), .src_arst(rst_arst_r)
    );
endmodule
