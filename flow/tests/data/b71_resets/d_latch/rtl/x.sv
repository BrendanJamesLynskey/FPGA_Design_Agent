module x(input rst, input en, input d, output logic q);
always_latch if (rst) q = 0; else if (en) q = d;
endmodule
