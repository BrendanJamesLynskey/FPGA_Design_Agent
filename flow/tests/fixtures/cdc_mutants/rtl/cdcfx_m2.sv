// M2: one asynchronous bit sampled by two flops that are then compared (they can disagree for a cycle).
module cdcfx_m2 (input logic clk_a, input logic clk_b, input logic ev_in, output logic ev_out, output logic err_out);
    logic tog = 1'b0;
    always_ff @(posedge clk_a) if (ev_in) tog <= ~tog;
    (* DONT_TOUCH = "TRUE" *) logic q0 = 1'b0;
    (* DONT_TOUCH = "TRUE" *) logic q1 = 1'b0;
    always_ff @(posedge clk_b) begin q0 <= tog; q1 <= tog; end
    logic prev = 1'b0;
    always_ff @(posedge clk_b) begin prev <= q0; ev_out <= q0 ^ prev; err_out <= q0 != q1; end
endmodule
