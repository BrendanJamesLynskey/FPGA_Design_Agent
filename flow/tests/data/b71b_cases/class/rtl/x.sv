class C; logic q; task run(input logic clk, rst_n, d); fork forever @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d; join_none endtask endclass
module x(input clk,rst_n,d,output logic q); endmodule
