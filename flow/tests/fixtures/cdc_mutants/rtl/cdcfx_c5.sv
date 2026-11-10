// C5: pulse through xpm_cdc_pulse.
module cdcfx_c5 (input logic clk_a, input logic clk_b, input logic ev_in, output logic ev_out, output logic err_out);
    logic pls = 1'b0;
    always_ff @(posedge clk_a) pls <= ev_in;
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .REG_OUTPUT(1), .RST_USED(0))
        u_x (.src_clk(clk_a), .src_pulse(pls), .dest_clk(clk_b), .src_rst(1'b0), .dest_rst(1'b0), .dest_pulse(ev_out));
    assign err_out = 1'b0;
endmodule
