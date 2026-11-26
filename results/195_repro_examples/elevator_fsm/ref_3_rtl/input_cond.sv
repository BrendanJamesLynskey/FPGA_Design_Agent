// Per-switch 2-flop synchroniser, debounce counter and rising-edge detect.
module input_cond #(
    parameter int N = 4,
    parameter int DEBOUNCE_CYCLES = 1000000
) (
    input  logic         clk,
    input  logic         rst,
    input  logic [N-1:0] sw_async,
    output logic [N-1:0] edges
);
    localparam int CW = $clog2(DEBOUNCE_CYCLES + 1) + 1;

    (* ASYNC_REG = "TRUE" *) logic [N-1:0] s1;
    (* ASYNC_REG = "TRUE" *) logic [N-1:0] s2;
    logic [N-1:0] stable, prev;
    logic [CW-1:0] cnt [N];

    always_ff @(posedge clk) begin
        s1 <= sw_async;
        s2 <= s1;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            stable <= '0;
            prev   <= '0;
            for (int n = 0; n < N; n++) cnt[n] <= '0;
        end else begin
            prev <= stable;
            for (int n = 0; n < N; n++) begin
                if (s2[n] != stable[n]) begin
                    if (int'(cnt[n]) + 1 >= DEBOUNCE_CYCLES) begin
                        cnt[n]    <= '0;
                        stable[n] <= ~stable[n];
                    end else begin
                        cnt[n] <= cnt[n] + 1'b1;
                    end
                end else begin
                    cnt[n] <= '0;
                end
            end
        end
    end

    assign edges = stable & ~prev;
endmodule
