module x(input clk, input rst, input d, output logic q, r);
always_ff @(posedge clk) begin
  if (!rst) begin q<=0; end else q<=d;
end
always_ff @(posedge clk) begin
  if ((rst)) r<=0; else r<=d;
end
endmodule
