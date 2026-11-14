interface ff_if(input clk, input rst_n);
logic q, d;
always_ff @(posedge clk or negedge rst_n) if (!rst_n) q<=0; else q<=d;
endinterface
module x(input clk, input rst_n); ff_if i(clk,rst_n); endmodule
