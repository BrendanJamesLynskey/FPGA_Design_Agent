module x(input clk, input rst_n, input d, output logic q);
always_ff @(posedge clk) if (!rst_n[0]) q<=0;
always_ff @(posedge clk) if (rst_n[0]) q<=d;
endmodule
