// m22_bram_big: 32768 x 32 RAM (1 Mbit), single port, output register: a BRAM cascade of 32 blocks on UltraScale+.
module m22_bram_big (input logic clk, input logic we, input logic [14:0] a, input logic [31:0] d, output logic [31:0] q);
    logic [31:0] mem [32768]; logic [31:0] r;
    always_ff @(posedge clk) begin
        if (we) mem[a] <= d;
        r <= mem[a];
        q <= r;
    end
endmodule
