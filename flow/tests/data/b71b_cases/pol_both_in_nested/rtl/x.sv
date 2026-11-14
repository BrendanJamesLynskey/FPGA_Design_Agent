module x(input clk, input rst_n, input d, output logic q);
always_ff @(posedge clk) begin if (!rst_n) q<=0; else q<=d; end
always_ff @(posedge clk) begin if (rst_n) q<=d; end
endmodule
