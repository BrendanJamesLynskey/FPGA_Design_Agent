// Reset generator (reset synchroniser): rst (active high, registered) is held for RST_HOLD_CYCLES clk
// cycles after configuration and while the MMCM is not locked. The asynchronous locked input is
// synchronised by xpm_cdc_single.
module rst_gen #(
    parameter int RST_HOLD_CYCLES = 16
) (
    input  logic clk,
    input  logic locked,
    output logic rst
);
    /* verilator lint_off PROCASSINIT */
    (* ASYNC_REG = "TRUE" *) logic locked_m = 1'b0;
    (* ASYNC_REG = "TRUE" *) logic locked_s = 1'b0;
    /* verilator lint_on PROCASSINIT */
    always_ff @(posedge clk) begin
        locked_m <= locked;
        locked_s <= locked_m;
    end

    /* verilator lint_off PROCASSINIT */
    logic [4:0] cnt = 5'd0;
    /* verilator lint_on PROCASSINIT */
    initial rst = 1'b1;
    always_ff @(posedge clk) begin
        if (cnt != 5'(RST_HOLD_CYCLES)) cnt <= cnt + 5'd1;
        rst <= (cnt != 5'(RST_HOLD_CYCLES)) | ~locked_s;
    end
endmodule
