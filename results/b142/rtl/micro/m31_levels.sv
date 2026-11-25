// m31_levels: 40-input AND-OR-XOR reduction (logic depth of a wide function), registered in and out.
module m31_levels (input logic clk, input logic [39:0] x, output logic y);
    logic [39:0] xq;
    always_ff @(posedge clk) begin
        xq <= x;
        y <= (^xq[19:0]) & (|xq[29:20]) | (&xq[39:30]) ^ (^xq[39:25]);
    end
endmodule
