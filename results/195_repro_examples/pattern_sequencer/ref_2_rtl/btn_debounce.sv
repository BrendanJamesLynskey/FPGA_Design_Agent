// btn_debounce: 2-flop synchroniser, stable-count debouncer, rising-edge pulse.
module btn_debounce #(
    parameter int DEBOUNCE_CYCLES = 1000000
) (
    input  logic clk,
    input  logic rst,     // synchronous, active high
    input  logic btn,     // asynchronous
    output logic press    // one-cycle pulse per debounced rising edge
);
    localparam int CW = (DEBOUNCE_CYCLES > 1) ? $clog2(DEBOUNCE_CYCLES) : 1;

    logic          sync_q;
    logic          stable;
    logic          prev;
    logic [CW-1:0] cnt;

    sync2 #(.WIDTH(1)) u_sync (.clk(clk), .rst(rst), .d(btn), .q(sync_q));

    always_ff @(posedge clk) begin
        if (rst) begin
            stable <= 1'b0;
            prev   <= 1'b0;
            cnt    <= '0;
            press  <= 1'b0;
        end else begin
            if (sync_q == stable) begin
                cnt <= '0;
            end else if (int'(cnt) + 1 >= DEBOUNCE_CYCLES) begin
                stable <= sync_q;
                cnt    <= '0;
            end else begin
                cnt <= cnt + 1'b1;
            end
            prev  <= stable;
            press <= stable && !prev;
        end
    end
endmodule
