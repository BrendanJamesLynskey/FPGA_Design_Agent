// m37_lutram: 64 x 8 distributed RAM (asynchronous read, one write port: RAM64M / RAM64X1S).
module m37_lutram (input logic clk, input logic we, input logic [5:0] wa, ra, input logic [7:0] wd, output logic [7:0] rd);
    (* ram_style = "distributed" *) logic [7:0] mem [64];
    always_ff @(posedge clk) if (we) mem[wa] <= wd;
    assign rd = mem[ra];
endmodule
