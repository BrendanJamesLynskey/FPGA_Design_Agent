// m23_uram: 4096 x 72 RAM requested as UltraRAM (URAM288), simple dual port, output register.
module m23_uram (input logic clk, input logic we, input logic [11:0] wa, ra, input logic [71:0] wd, output logic [71:0] rd);
    (* ram_style = "ultra" *) logic [71:0] mem [4096]; logic [71:0] r;
    always_ff @(posedge clk) begin
        if (we) mem[wa] <= wd;
        r <= mem[ra];
        rd <= r;
    end
endmodule
