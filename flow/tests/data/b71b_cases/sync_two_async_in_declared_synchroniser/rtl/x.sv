module x(input clk, rst_n, d, output logic q);
(* ASYNC_REG *) logic a;
always_ff @(posedge clk) a<=d;
always_ff @(posedge clk or negedge d) q<=a;
endmodule
