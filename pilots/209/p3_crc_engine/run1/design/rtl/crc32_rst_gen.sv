// Reset generator: asynchronous assert while the MMCM is unlocked, synchronous release.
module crc32_rst_gen (
    input  logic clk,
    input  logic locked,
    output logic rst
);
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst (
        .dest_arst(rst), .dest_clk(clk), .src_arst(~locked));
endmodule
