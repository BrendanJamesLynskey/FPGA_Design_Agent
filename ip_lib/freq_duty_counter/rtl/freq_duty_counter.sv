// freq_duty_counter: counts rising edges and high clocks of an asynchronous input over a fixed gate of GATE_CLKS
// clocks (brief 30). frequency = edges / (GATE_CLKS / f_clk); duty = high_clks / GATE_CLKS. Accuracy: edges is exact
// for the signal as sampled (at most one edge per two clocks); frequency resolution is f_clk / GATE_CLKS.
module freq_duty_counter #(
    parameter int GATE_CLKS = 100_000,   // gate length in clocks (1 ms at 100 MHz)
    parameter int CNT_W     = 24         // width of the edge and high-clock counters
) (
    input  logic             clk,
    input  logic             rst,         // synchronous, active high
    input  logic             sig,         // asynchronous input
    output logic             valid,       // one-clock pulse: edges / high_clks hold the gate just finished
    output logic [CNT_W-1:0] edges,
    output logic [CNT_W-1:0] high_clks,
    output logic [31:0]      gates        // number of gates completed
);
    initial begin
        if (GATE_CLKS < 4 || GATE_CLKS > (1 << 30)) $error("freq_duty_counter: GATE_CLKS %0d outside 4..2^30", GATE_CLKS);
        if (CNT_W < 3 || CNT_W > 32) $error("freq_duty_counter: CNT_W %0d outside 3..32", CNT_W);
        if (CNT_W < 32 && GATE_CLKS >= (1 << CNT_W)) $error("freq_duty_counter: CNT_W %0d cannot hold a gate of %0d clocks", CNT_W, GATE_CLKS);
    end

    (* ASYNC_REG = "TRUE" *) logic s1, s2;
    logic s3;
    always_ff @(posedge clk) begin
        s1 <= sig; s2 <= s1; s3 <= s2;
    end

    logic [31:0]      gate_cnt;
    logic [CNT_W-1:0] e_acc, h_acc;
    always_ff @(posedge clk) begin
        valid <= 1'b0;
        if (rst) begin
            gate_cnt <= '0; e_acc <= '0; h_acc <= '0; edges <= '0; high_clks <= '0; gates <= '0;
        end else begin
            if (gate_cnt == GATE_CLKS - 1) begin
                gate_cnt  <= '0;
                edges     <= e_acc + CNT_W'(s2 & ~s3);
                high_clks <= h_acc + CNT_W'(s2);
                e_acc     <= '0;
                h_acc     <= '0;
                gates     <= gates + 1'b1;
                valid     <= 1'b1;
            end else begin
                gate_cnt <= gate_cnt + 1'b1;
                e_acc    <= e_acc + CNT_W'(s2 & ~s3);
                h_acc    <= h_acc + CNT_W'(s2);
            end
        end
    end
endmodule
