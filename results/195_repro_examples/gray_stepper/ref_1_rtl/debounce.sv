// Counter debounce: the internal level follows the input once the input has
// differed from it for DEBOUNCE_CYCLES clocks. press is a one-clock pulse on
// the rising edge of the debounced level.
module debounce #(
    parameter int DEBOUNCE_CYCLES = 2_000_000
) (
    input  logic clk,
    input  logic rst,
    input  logic din,     // already synchronised
    output logic press
);
    localparam int CW = (DEBOUNCE_CYCLES > 1) ? $clog2(DEBOUNCE_CYCLES) : 1;

    logic [CW-1:0] cnt;
    logic          level;

    always_ff @(posedge clk) begin
        press <= 1'b0;
        if (rst) begin
            cnt   <= '0;
            level <= 1'b0;
        end else if (din == level) begin
            cnt <= '0;
        end else if (cnt == CW'(DEBOUNCE_CYCLES - 1)) begin
            cnt   <= '0;
            level <= din;
            press <= din;
        end else begin
            cnt <= cnt + 1'b1;
        end
    end
endmodule
