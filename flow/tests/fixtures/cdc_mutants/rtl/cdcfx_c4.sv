// C4: pulse converted to a toggle in the source domain, two scalar ASYNC_REG flops in the destination.
module cdcfx_c4 (input logic clk_a, input logic clk_b, input logic ev_in, output logic ev_out, output logic err_out);
    logic pls = 1'b0, tg = 1'b0;
    always_ff @(posedge clk_a) begin pls <= ev_in; if (ev_in) tg <= ~tg; end
    (* ASYNC_REG = "TRUE" *) logic s1 = 1'b0, s2 = 1'b0;
    always_ff @(posedge clk_b) begin s1 <= tg; s2 <= s1; end
    logic prev = 1'b0;
    always_ff @(posedge clk_b) begin prev <= s2; ev_out <= s2 ^ prev; end
    assign err_out = 1'b0;
endmodule
