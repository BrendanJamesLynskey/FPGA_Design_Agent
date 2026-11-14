module x(input clk, input rst_n, input d, output logic q, r);
wire rst_p = ~rst_n;
always_ff @(posedge clk) if (!rst_n) q<=0; else q<=d;
always_ff @(posedge clk) if (rst_p) r<=0; else r<=d;
endmodule
