module x(input clk, input rst_n, input d, output logic q);
FDCPE u (.C(clk), .CE(1'b1), .CLR(~rst_n), .PRE(1'b0), .D(d), .Q(q));
endmodule
