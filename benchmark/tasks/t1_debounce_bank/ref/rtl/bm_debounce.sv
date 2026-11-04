// bm_debounce.sv: two-flop synchroniser, then a counting debounce. The level
// changes only after the synchronised input has differed from it for CYCLES
// consecutive clocks; a shorter difference restarts the count. rise is a
// one-clock pulse on each 0 -> 1 change of the level.
module bm_debounce #(
    parameter int CYCLES = 1_000_000
) (
    input  logic clk,
    input  logic rst,
    input  logic d_async,
    output logic level,
    output logic rise
);
    localparam int CW = $clog2(CYCLES + 1);
    logic        d;
    logic [CW-1:0] run;

    sync2 u_sync (.clk(clk), .rst(rst), .d(d_async), .q(d));

    always_ff @(posedge clk) begin
        rise <= 1'b0;
        if (rst) begin
            level <= 1'b0;
            run   <= '0;
        end else if (d == level) begin
            run <= '0;
        end else if (run == CW'(CYCLES - 1)) begin
            level <= d;
            run   <= '0;
            rise  <= d;
        end else begin
            run <= run + 1'b1;
        end
    end
endmodule
