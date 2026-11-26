// Per-domain reset synchronisers (asynchronous assert, synchronous release).
/* verilator lint_off DECLFILENAME */
module reset_gen (
    input  logic rst,
    input  logic clk_wr,
    input  logic clk_rd,
    output logic rst_wr,
    output logic rst_rd
);
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst_wr (
        .src_arst(rst), .dest_clk(clk_wr), .dest_arst(rst_wr));
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst_rd (
        .src_arst(rst), .dest_clk(clk_rd), .dest_arst(rst_rd));
endmodule
