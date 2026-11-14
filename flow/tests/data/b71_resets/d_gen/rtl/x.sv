module x(input clk, input rst_n, input d, output logic q);
generate if (1) begin : g
always_ff @(posedge clk, negedge rst_n) begin : blk
 if (!rst_n) q<=0; else q<=d; end end endgenerate
endmodule
