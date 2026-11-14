module x(input clk, input rst_n, input d, output logic q);
always_ff @(posedge clk) begin q<=d; end
initial begin @(negedge rst_n); q=0; end
endmodule
