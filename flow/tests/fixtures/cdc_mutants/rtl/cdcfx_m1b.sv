// M1b: no synchroniser: one destination flop.
module cdcfx_m1b (input logic clk_a, input logic clk_b, input logic ev_in, output logic ev_out, output logic err_out);
    logic tog = 1'b0;
    always_ff @(posedge clk_a) if (ev_in) tog <= ~tog;
    logic lvl = 1'b0, prev = 1'b0;
    always_ff @(posedge clk_b) begin lvl <= tog; prev <= lvl; ev_out <= lvl ^ prev; end
    assign err_out = 1'b0;
endmodule
