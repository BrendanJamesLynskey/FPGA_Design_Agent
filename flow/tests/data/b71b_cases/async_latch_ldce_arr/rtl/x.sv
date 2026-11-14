module x(input clk, input rst_n, input d, output logic q);
LDPE_1 u (.G(clk), .GE(1'b1), .PRE(~rst_n), .D(d), .Q(q));
endmodule
