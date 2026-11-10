// M4: two toggles that change together are XORed before the synchroniser (the XOR should never change; a skew
// between the two routes makes it glitch).
module cdcfx_m4 (input logic clk_a, input logic clk_b, input logic ev_in, output logic ev_out, output logic err_out);
    logic t0 = 1'b0, t1 = 1'b0;
    always_ff @(posedge clk_a) if (ev_in) begin t0 <= ~t0; t1 <= ~t1; end
    wire x = t0 ^ t1;
    (* ASYNC_REG = "TRUE" *) logic [1:0] sync = 2'b00;
    always_ff @(posedge clk_b) sync <= {sync[0], x};
    logic prev = 1'b0;
    always_ff @(posedge clk_b) begin prev <= sync[1]; err_out <= sync[1] != prev; end
    assign ev_out = 1'b0;
endmodule
