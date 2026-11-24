// m06_counter32: 32-bit counter with enable and synchronous clear.
module m06_counter32 (input logic clk, input logic en, clr, output logic [31:0] q);
    logic enq, clrq;
    always_ff @(posedge clk) begin
        enq <= en; clrq <= clr;
        if (clrq) q <= '0; else if (enq) q <= q + 32'd1;
    end
endmodule
