// C3: toggle through xpm_cdc_single (3 stages).
module cdcfx_c3 (input logic clk_a, input logic clk_b, input logic ev_in, output logic ev_out, output logic err_out);
    logic tog = 1'b0;
    always_ff @(posedge clk_a) if (ev_in) tog <= ~tog;
    logic lvl;
    xpm_cdc_single #(.DEST_SYNC_FF(3), .SRC_INPUT_REG(1)) u_x (.src_clk(clk_a), .src_in(tog), .dest_clk(clk_b), .dest_out(lvl));
    logic prev = 1'b0;
    always_ff @(posedge clk_b) begin prev <= lvl; ev_out <= lvl ^ prev; end
    assign err_out = 1'b0;
endmodule
