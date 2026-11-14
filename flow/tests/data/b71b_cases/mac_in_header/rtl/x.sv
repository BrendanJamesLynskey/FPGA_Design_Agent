module x(input clk, input rst_n, input d, output logic q);
`include "m.svh"
`DFF(q,d)
endmodule
