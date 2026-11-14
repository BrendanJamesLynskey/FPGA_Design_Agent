module x(input clk, input rst_n, input d, output logic q);
always_ff @(posedge clk) begin q<=d; end
always @(negedge rst_n) q<=0;
endmodule
