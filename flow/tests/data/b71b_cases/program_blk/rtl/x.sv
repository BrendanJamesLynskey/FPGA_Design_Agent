program x(input clk, rst_n, d, output logic q);
initial forever @(posedge clk or negedge rst_n) if(!rst_n) q<=0; else q<=d;
endprogram
