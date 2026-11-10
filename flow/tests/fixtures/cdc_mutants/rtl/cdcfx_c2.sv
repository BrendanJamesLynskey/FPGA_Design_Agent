// C2: as C1 with a 3-flop chain.
module cdcfx_c2 (input logic clk_a, input logic clk_b, input logic ev_in, output logic ev_out, output logic err_out);
    logic tog = 1'b0;
    always_ff @(posedge clk_a) if (ev_in) tog <= ~tog;
    (* ASYNC_REG = "TRUE" *) logic [2:0] sync = 3'b000;
    always_ff @(posedge clk_b) sync <= {sync[1:0], tog};
    logic prev = 1'b0;
    always_ff @(posedge clk_b) begin prev <= sync[2]; ev_out <= sync[2] ^ prev; end
    assign err_out = 1'b0;
endmodule
