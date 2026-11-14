module x #(parameter bit ASYNC=1)(input clk, rst_n, d, output logic q);
if (ASYNC) begin : g
always_ff @(posedge clk or negedge rst_n) if (!rst_n) q<=0; else q<=d;
end else begin : h
always_ff @(posedge clk) q<=d;
end
endmodule
