// m36_uram_big: 16384 x 72 RAM requested as UltraRAM (4 x 4096 deep: a URAM288 cascade or an array of 4), single port, output register.
module m36_uram_big (input logic clk, input logic we, input logic [13:0] a, input logic [71:0] d, output logic [71:0] q);
    (* ram_style = "ultra" *) logic [71:0] mem [16384]; logic [71:0] r;
    always_ff @(posedge clk) begin
        if (we) mem[a] <= d;
        r <= mem[a];
        q <= r;
    end
endmodule
