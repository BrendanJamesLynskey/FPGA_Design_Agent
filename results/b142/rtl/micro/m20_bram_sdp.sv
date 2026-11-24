// m20_bram_sdp: 1024 x 32 simple dual-port RAM, synchronous read, output register.
module m20_bram_sdp (input logic clk, input logic we, input logic [9:0] wa, ra, input logic [31:0] wd, output logic [31:0] rd);
    logic [31:0] mem [1024]; logic [31:0] r;
    always_ff @(posedge clk) begin
        if (we) mem[wa] <= wd;
        r <= mem[ra];
        rd <= r;
    end
endmodule
