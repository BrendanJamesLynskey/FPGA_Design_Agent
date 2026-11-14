module x(input clk, input rst_n, input d, output logic q);
always_ff @(posedge clk) begin if (!rst_n) q<=0; else q<=d; end
always_ff @(posedge clk) begin case (rst_n) 1'b1: q<=d; default: q<=0; endcase end
endmodule
