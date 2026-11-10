// M5: a one-cycle pulse into a level synchroniser (no stretch, no toggle): lost if the destination misses it.
module cdcfx_m5 (input logic clk_a, input logic clk_b, input logic ev_in, output logic ev_out, output logic err_out);
    logic pls = 1'b0;
    always_ff @(posedge clk_a) pls <= ev_in;
    (* ASYNC_REG = "TRUE" *) logic [1:0] sync = 2'b00;
    always_ff @(posedge clk_b) sync <= {sync[0], pls};
    logic prev = 1'b0;
    always_ff @(posedge clk_b) begin prev <= sync[1]; ev_out <= sync[1] & ~prev; end
    assign err_out = 1'b0;
endmodule
