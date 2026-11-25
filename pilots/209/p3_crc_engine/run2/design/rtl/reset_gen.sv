// reset_gen: asynchronous-assert, synchronous-release reset from MMCM locked, held 6 clocks after release.
module reset_gen (
    input  logic clk,
    input  logic locked_async,
    output logic locked_sync,
    output logic rst
);
    logic arst;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst (
        .src_arst(~locked_async), .dest_clk(clk), .dest_arst(arst));
    assign locked_sync = ~arst;

    logic [2:0] cnt;
    always_ff @(posedge clk) begin
        if (arst) begin
            cnt <= 3'd0;
            rst <= 1'b1;
        end else if (cnt == 3'd5) begin
            rst <= 1'b0;
        end else begin
            cnt <= cnt + 3'd1;
        end
    end
endmodule
