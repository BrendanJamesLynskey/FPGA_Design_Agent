module x(input clk, input rst_n, input d, output logic q);
always @ ( * ) q = d;
endmodule
