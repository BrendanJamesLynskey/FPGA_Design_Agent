// M1: two flops but no ASYNC_REG (the tool may place them apart and may merge or retime them).
module cdcfx_m1 (input logic clk_a, input logic clk_b, input logic ev_in, output logic ev_out, output logic err_out);
    logic tog = 1'b0;
    always_ff @(posedge clk_a) if (ev_in) tog <= ~tog;
    logic m = 1'b0, lvl = 1'b0;
    always_ff @(posedge clk_b) begin m <= tog; lvl <= m; end
    logic prev = 1'b0;
    always_ff @(posedge clk_b) begin prev <= lvl; ev_out <= lvl ^ prev; end
    assign err_out = 1'b0;
endmodule
