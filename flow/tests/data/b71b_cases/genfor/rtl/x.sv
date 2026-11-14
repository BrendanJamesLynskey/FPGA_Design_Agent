module x(input clk, input [3:0] rst_n, input [3:0] d, output logic [3:0] q);
generate for (genvar i=0;i<4;i++) begin : g
always_ff @(posedge clk or negedge rst_n[i]) if(!rst_n[i]) q[i]<=0; else q[i]<=d[i];
end endgenerate
endmodule
