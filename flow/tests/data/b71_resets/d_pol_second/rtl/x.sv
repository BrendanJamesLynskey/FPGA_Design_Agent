module x(input clk, input rst, input en, input d, output logic q, r);
always_ff @(posedge clk) begin if (en) q<=d; if (!rst) q<=0; end
always_ff @(posedge clk) begin if (en) r<=d; if (rst) r<=0; end
endmodule
