module x(input clk, input rst_n, input d, output logic q);
for (genvar i=0;i<4;i++) begin: g FDCE u (.C(clk), .CE(1'b1), .CLR(~rst_n), .D(d), .Q(q)); end
endmodule
