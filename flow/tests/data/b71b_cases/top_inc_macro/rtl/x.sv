`include "m.svh"
module x(input clk, input rst_n, input d, output logic q);
`DFF(q,d)
endmodule
