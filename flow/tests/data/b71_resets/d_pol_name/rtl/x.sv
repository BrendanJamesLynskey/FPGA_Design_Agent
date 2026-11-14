module x(input clk, input clr, input d, output logic q, r);
always_ff @(posedge clk) if (!clr) q<=0; else q<=d;
always_ff @(posedge clk) if (clr) r<=0; else r<=d;
endmodule
