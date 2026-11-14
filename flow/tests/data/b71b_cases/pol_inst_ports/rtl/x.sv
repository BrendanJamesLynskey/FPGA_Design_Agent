module x(input clk, input rst_n, input d, output logic q);
sub a(.clk(clk), .rst(rst_n));
sub b(.clk(clk), .rst_n(~rst_n));
endmodule
