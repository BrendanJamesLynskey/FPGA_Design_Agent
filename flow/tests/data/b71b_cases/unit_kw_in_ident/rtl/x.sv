module x(input clk, rst_n, d, output logic q);
logic my_module_name, program_x;
always @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endmodule
