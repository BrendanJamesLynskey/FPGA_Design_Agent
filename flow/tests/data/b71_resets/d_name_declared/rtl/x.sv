module sub(input clk, input rst_n, input d, output logic q);
always_ff @(posedge clk or negedge rst_n) if (!rst_n) q<=0; else q<=d;
endmodule
module x(input clk, input a, input b, input d, output q);
wire rst_n = a & b;
sub u(.clk(clk), .rst_n(rst_n), .d(d), .q(q));
endmodule
