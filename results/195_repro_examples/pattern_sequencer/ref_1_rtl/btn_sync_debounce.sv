// btn_sync_debounce: two-flop synchroniser, then a debounce counter. The debounced
// state changes only after the input has differed from it for DEBOUNCE_CYCLES clocks.
// press is a one-clock pulse on each debounced rising edge.
module btn_sync_debounce #(
    parameter int DEBOUNCE_CYCLES = 2000000
) (
    input  logic clk,
    input  logic rst,     // synchronous, active high
    input  logic btn,     // asynchronous
    output logic press
);
    localparam int CW = (DEBOUNCE_CYCLES > 2) ? $clog2(DEBOUNCE_CYCLES) : 1;

    (* ASYNC_REG = "TRUE" *) logic [1:0] sync;
    logic          state;
    logic [CW-1:0] cnt;

    always_ff @(posedge clk) sync <= {sync[0], btn};

    always_ff @(posedge clk) begin
        press <= 1'b0;
        if (rst) begin
            state <= 1'b0;
            cnt   <= '0;
        end else if (sync[1] == state) begin
            cnt <= '0;
        end else if (cnt == CW'(DEBOUNCE_CYCLES - 1)) begin
            state <= sync[1];
            cnt   <= '0;
            press <= sync[1];
        end else begin
            cnt <= cnt + 1'b1;
        end
    end
endmodule
