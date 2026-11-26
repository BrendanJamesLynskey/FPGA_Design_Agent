// Reset release synchroniser: asynchronous assert, synchronous release in the destination clock domain.
module rst_sync (
    input  logic arst_in,   // active high, from another domain
    input  logic clk,
    output logic rst_out    // active high, released synchronously to clk
);
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_arst (
        .src_arst(arst_in), .dest_clk(clk), .dest_arst(rst_out));
endmodule
