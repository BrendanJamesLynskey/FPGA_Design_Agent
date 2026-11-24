// m30_async_rst: 32 registers with an asynchronous reset (FDCE).
module m30_async_rst (input logic clk, input logic arst_n, input logic [31:0] d, output logic [31:0] q);
    always_ff @(posedge clk or negedge arst_n) if (!arst_n) q <= '0; else q <= d;
endmodule
