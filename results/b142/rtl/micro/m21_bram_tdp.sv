// m21_bram_tdp: 2048 x 18 true dual-port RAM, both ports on one clock, read-first; one process per port (Vivado infers block RAM only then).
module m21_bram_tdp (input logic clk, input logic wea, web, input logic [10:0] aa, ab, input logic [17:0] da, db, output logic [17:0] qa, qb);
    logic [17:0] mem [2048];
    always @(posedge clk) begin
        if (wea) mem[aa] <= da;
        qa <= mem[aa];
    end
    always @(posedge clk) begin
        if (web) mem[ab] <= db;
        qb <= mem[ab];
    end
endmodule
