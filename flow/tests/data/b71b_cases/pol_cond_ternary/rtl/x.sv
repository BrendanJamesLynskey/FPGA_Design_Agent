module x(input clk, input rst_n, input d, output logic q);
always_ff @(posedge clk) q <= rst_n ? d : 1'b0;
always_ff @(posedge clk) if (!rst_n) q<=0;
endmodule
