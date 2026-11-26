// Reset synchroniser: asynchronous assert, synchronous release (active-high in and out).
module reset_sync (
    input  logic dest_clk,
    input  logic src_rst,
    output logic dest_rst
);
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst (
        .dest_arst(dest_rst), .dest_clk(dest_clk), .src_arst(src_rst));
endmodule
