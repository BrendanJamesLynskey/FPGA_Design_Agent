module x(input clk, input rst_n, input d, output logic q);
FDCE #(.INIT(1'b0)) u1(.C(clk)), u2 (.C(clk), .CLR(~rst_n), .D(d), .Q(q));
endmodule
