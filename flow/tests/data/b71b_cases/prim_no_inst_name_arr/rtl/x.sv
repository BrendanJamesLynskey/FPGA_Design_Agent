module x(input clk, input rst_n, input d, output logic q);
FDPE u [3:0] (.C(clk), .CE(1'b1), .PRE(~rst_n), .D(d), .Q(q));
endmodule
