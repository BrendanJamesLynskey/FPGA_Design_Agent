module x(input clk, d, output q);
logic rst_n; assign rst_n = d;
reg q_r; assign q=q_r;
always @(posedge clk or negedge rst_n) if(!rst_n) q_r<=0; else q_r<=d;
endmodule
