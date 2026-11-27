// Startup reset: held 16 clk_c3 cycles after configuration; the reader domain gets a synchronised release.
module rst_gen (
    input  logic clk_c3,
    input  logic clk_gt,
    output logic rst_c3,   // active high, clk_c3 domain
    output logic rst_gt    // active high, clk_gt domain
);
    /* verilator lint_off PROCASSINIT */
    /* verilator lint_off SYNCASYNCNET */
    logic [3:0] cnt = 4'd0;
    logic       rst_q = 1'b1;
    always_ff @(posedge clk_c3) begin
        if (cnt != 4'd15) cnt <= cnt + 4'd1;
        rst_q <= (cnt != 4'd15);
    end
    assign rst_c3 = rst_q;
    rst_sync u_rst_sync (.arst_in(rst_q), .clk(clk_gt), .rst_out(rst_gt));
endmodule
