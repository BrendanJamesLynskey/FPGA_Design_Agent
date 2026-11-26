// Brief 213 fixture: an 8-bit loadable counter with a wrap flag. Synchronous active-high reset.
module rg_counter (
    input  logic       clk,
    input  logic       rst,
    input  logic       en,
    input  logic       load,
    input  logic [7:0] d,
    output logic [7:0] q,
    output logic       wrap
);
    always_ff @(posedge clk) begin
        if (rst) begin
            q    <= 8'h00;
            wrap <= 1'b0;
        end else begin
            wrap <= en && !load && (q == 8'hFF);
            if (load)     q <= d;
            else if (en)  q <= q + 8'h02;   // seeded bug the directed bench catches: counts by two
        end
    end
endmodule
