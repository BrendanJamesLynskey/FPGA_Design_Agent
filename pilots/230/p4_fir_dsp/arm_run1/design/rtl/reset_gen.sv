// Power-on reset: active-high rst held RESET_CYCLES clk cycles after the MMCM is locked.
module reset_gen #(
    parameter int RESET_CYCLES = 16
) (
    input  logic clk,
    input  logic locked,
    output logic rst
);
    logic unlocked_s;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_unlock (
        .dest_arst(unlocked_s), .dest_clk(clk), .src_arst(~locked));

    logic [4:0] cnt = 5'd0;
    initial rst = 1'b1;
    always_ff @(posedge clk) begin
        if (unlocked_s) begin
            cnt <= 5'd0;
            rst <= 1'b1;
        end else if (cnt == 5'(RESET_CYCLES)) begin
            rst <= 1'b0;
        end else begin
            cnt <= cnt + 5'd1;
        end
    end
endmodule
