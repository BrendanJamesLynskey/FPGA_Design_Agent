// Per-button 2-flop synchroniser, stable-for-N-cycles filter, one-cycle press pulse.
module t1_debounce #(
    parameter int DEBOUNCE_CYCLES = 2000000
) (
    input  logic clk,
    input  logic rst,
    input  logic din,
    output logic level,   // debounced level
    output logic pulse    // single-cycle pulse on debounced rising edge
);
    localparam int CW = $clog2(DEBOUNCE_CYCLES) + 1;
    logic          s1, s2;
    logic [CW-1:0] cnt;

    assign pulse = (s2 != level) && (cnt == CW'(DEBOUNCE_CYCLES - 1)) && s2;

    always_ff @(posedge clk) begin
        if (rst) begin
            s1    <= 1'b0;
            s2    <= 1'b0;
            level <= 1'b0;
            cnt   <= '0;
        end else begin
            s1 <= din;
            s2 <= s1;
            if (s2 != level) begin
                if (cnt == CW'(DEBOUNCE_CYCLES - 1)) begin
                    level <= s2;
                    cnt   <= '0;
                end else begin
                    cnt <= cnt + 1'b1;
                end
            end else begin
                cnt <= '0;
            end
        end
    end
endmodule
