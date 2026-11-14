module x(input clk, input rst_n, input d, output logic q);
always_comb begin q=d; end
always_ff @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endmodule
