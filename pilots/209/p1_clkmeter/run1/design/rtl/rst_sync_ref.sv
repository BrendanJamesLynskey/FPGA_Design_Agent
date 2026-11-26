// Reset synchroniser into the clk_ref domain: asynchronous assert, synchronous release (xpm_cdc_async_rst).
module rst_sync_ref (
    input  logic rst_in,     // active high
    input  logic clk_ref,
    output logic rst_ref     // active high, released synchronously
);
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst (
        .src_arst(rst_in), .dest_clk(clk_ref), .dest_arst(rst_ref));
endmodule
