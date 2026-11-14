module x(input clk, input rst_n, input en, input d, output logic q);
always_ff @(posedge clk iff (en) or negedge rst_n) if (!rst_n) q<=0; else q<=d;
endmodule
