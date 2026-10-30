// debounce.sv: synchronise and debounce one push button.
// The debounced level changes only after the synchronised input has differed
// from it for CYCLES consecutive clocks; a shorter difference restarts the
// count. press pulses for one clock on each 0 -> 1 change of the level.

module debounce #(
    parameter int CYCLES = 1_000_000          // 10 ms at 100 MHz
) (
    input  logic clk,
    input  logic rst,
    input  logic btn,                         // asynchronous, active high
    output logic level,                       // debounced
    output logic press                        // one-clock pulse on a press
);
    localparam int CW = $clog2(CYCLES + 1);

    logic          s;
    logic [CW-1:0] cnt;

    sync2 #(.WIDTH(1)) u_sync (.clk(clk), .rst(rst), .d(btn), .q(s));

    always_ff @(posedge clk) begin
        press <= 1'b0;
        if (rst) begin
            level <= 1'b0;
            cnt   <= '0;
        end else if (s == level) begin
            cnt <= '0;
        end else if (cnt == CW'(CYCLES - 1)) begin
            cnt   <= '0;
            level <= s;
            press <= s;
        end else begin
            cnt <= cnt + 1'b1;
        end
    end
endmodule
