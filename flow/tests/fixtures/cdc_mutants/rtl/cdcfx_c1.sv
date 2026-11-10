// C1: toggle synchronised by a 2-flop ASYNC_REG chain (vector form), edge detect in clk_b.
module cdcfx_c1 (input logic clk_a, input logic clk_b, input logic ev_in, output logic ev_out, output logic err_out);
    logic tog = 1'b0;
    always_ff @(posedge clk_a) if (ev_in) tog <= ~tog;
    (* ASYNC_REG = "TRUE" *) logic [1:0] sync = 2'b00;
    always_ff @(posedge clk_b) sync <= {sync[0], tog};
    logic prev = 1'b0;
    always_ff @(posedge clk_b) begin prev <= sync[1]; ev_out <= sync[1] ^ prev; end
    assign err_out = 1'b0;
endmodule
