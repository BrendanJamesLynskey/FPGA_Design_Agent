module x(input clk, input rst_n, input d, output logic q);
task t; begin @(posedge clk or negedge rst_n); q<=d; end endtask
endmodule
