module x(input clk, input rst_n, input d, output logic q);
FDCE_1 u (.C(clk), .CE(1'b1), .CLR(~rst_n), .D(d), .Q(q));
endmodule
