module x(input clk, input rst, input d, output logic q, r);
always_ff @(posedge clk) if (!rst) q<=0; else q<=d;
always_ff @(posedge clk) if (rst) r<=0; else r<=d;
endmodule
