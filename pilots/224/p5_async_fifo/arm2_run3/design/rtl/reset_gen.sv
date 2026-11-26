// Reset synchroniser: asynchronous assert, synchronous release into dest_clk (active high).
module reset_gen (
    input  logic dest_clk,
    input  logic rst_in,
    output logic rst_out
);
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst (
        .dest_clk(dest_clk), .src_arst(rst_in), .dest_arst(rst_out));
endmodule
