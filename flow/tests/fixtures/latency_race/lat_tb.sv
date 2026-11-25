// Two ways to measure the latency of lat_pipe (brief 189 item 7). A single stimulus pulse enters at one edge; the output pulse is
// seen DEPTH edges later.
//   method "counter":  a free-running cycle counter, one always block, read by a second always block that stamps the output.
//   method "sim_time": the simulator's own clock, (time at output - time at input) / period. No other process is involved.
// +RACY=0 and +RACY=1 are the planted defect: the counter is incremented with a BLOCKING assignment in one process and read in another on
// the same edge, so the order in which the simulator happens to run the two decides what the stamp reads (the source order of the two
// processes differs between the variants; Icarus re-queues a process after each wake-up, so the reading even changes from edge to edge).
// This is the testbench race of Edwards 2026, ch 15 (idea only; code ours). +RACY=2 is the repaired bench: a NON-blocking increment, so
// the stamp always reads the value from before the edge. The simulator-time method is untouched by the race in every variant.
module lat_tb;
    localparam int DEPTH = 3;
    localparam time PERIOD = 10;
    logic clk = 0;
    always #(PERIOD/2) clk = ~clk;
    logic in_valid = 0;
    wire out_valid;
    lat_pipe #(.DEPTH(DEPTH)) dut (.clk, .in_valid, .out_valid);
    int racy;
    initial if (!$value$plusargs("RACY=%d", racy)) racy = 0;

    int unsigned cnt = 0;
    int unsigned t_in_cnt, t_out_cnt;
    time t_in, t_out;
    bit got = 0;

    // variant 0: the counter is incremented in a process that is written BEFORE the stamping process
    always @(posedge clk) if (racy == 0) cnt = cnt + 1;
    always @(posedge clk) if (racy == 2) cnt <= cnt + 1;
    always @(posedge clk) if (racy == 0 || racy == 2) begin
        if (in_valid && t_in_cnt == 0) t_in_cnt = cnt;
        if (out_valid && !got) begin t_out_cnt = cnt; got = 1; t_out = $time; end
    end
    // variant 1: the stamping process is written BEFORE the counter
    always @(posedge clk) if (racy == 1) begin
        if (in_valid && t_in_cnt == 0) t_in_cnt = cnt;
        if (out_valid && !got) begin t_out_cnt = cnt; got = 1; t_out = $time; end
    end
    always @(posedge clk) if (racy == 1) cnt = cnt + 1;

    initial begin
        t_in_cnt = 0;
        repeat (5) @(posedge clk);
        #1 in_valid = 1;
        t_in = $time + 0;                // the input is applied just after the edge; the edge that samples it is the next one
        @(posedge clk); #1 in_valid = 0;
        repeat (DEPTH + 4) @(posedge clk);
        // the edge that samples in_valid is at t_in + PERIOD - 1 (applied 1 ns after an edge); the output is first seen at the edge at t_out
        $display("LAT_COUNTER=%0d", t_out_cnt - t_in_cnt);
        $display("LAT_SIMTIME=%0d", (t_out - (t_in + PERIOD - 1) + PERIOD/2) / PERIOD);
        $finish;
    end
endmodule
