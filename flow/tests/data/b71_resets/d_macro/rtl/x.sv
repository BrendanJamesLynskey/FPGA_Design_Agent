`define SENS posedge clk or negedge rst_n
module x(input clk, input rst_n, input d, output logic q);
always @(`SENS) if (!rst_n) q<=0; else q<=d;
endmodule
