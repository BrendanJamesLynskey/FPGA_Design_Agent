// m24_bram_be: 1024 x 32 RAM with byte write enables.
module m24_bram_be (input logic clk, input logic [3:0] we, input logic [9:0] a, input logic [31:0] d, output logic [31:0] q);
    logic [31:0] mem [1024];
    always_ff @(posedge clk) begin
        for (int i = 0; i < 4; i++) if (we[i]) mem[a][8*i +: 8] <= d[8*i +: 8];
        q <= mem[a];
    end
endmodule
