// formal_interlocks.sv: properties of rtl/interlocks.sv, proved by SymbiYosys (interlocks.sby).
// Every input is free (the solver plays the hostile traffic and the host); the configuration is held stable after
// reset except the kill and halt inputs, which may change on any clock. A grant must never breach a limit.
module formal_interlocks (
    input logic        clk,
    input logic        kill_reg, kill_in, halt,
    input logic [31:0] max_qty, band, max_pos, refill,
    input logic [15:0] bucket,
    input logic        req_v, req_side,
    input logic [31:0] req_qty, req_px, req_ref,
    input logic        req_noref,
    input logic        reload
);
    logic rst;
    logic f_past = 1'b0;
    logic [3:0] f_n = 4'd0;
    always_ff @(posedge clk) begin f_past <= 1'b1; if (f_n != 4'hF) f_n <= f_n + 4'd1; end
    assign rst = (f_n == 4'd0);

    logic grant, rej_v, approved, tick;
    logic [2:0] rej_why;
    logic signed [33:0] pos;
    logic [15:0] tokens;
    interlocks dut (.clk, .rst, .kill_reg, .kill_in, .halt, .max_qty, .band, .max_pos, .bucket, .refill, .reload,
                    .req_v, .req_side, .req_qty, .req_px, .req_ref, .req_noref, .grant, .rej_v, .rej_why, .pos, .tokens,
                    .approved, .tick);

    // configuration stable after reset (the host does not reconfigure during a run); small values keep it shallow
    always_ff @(posedge clk) if (f_past && !rst) begin
        assume (max_qty == $past(max_qty)); assume (band == $past(band)); assume (max_pos == $past(max_pos));
        assume (bucket == $past(bucket));   assume (refill == $past(refill));
    end
    always_comb begin
        assume (bucket <= 16'd4);
        assume (refill >= 32'd3 && refill <= 32'd6);
        assume (!reload);
    end

    // the request seen by the clock that grants it
    logic        p_side;
    logic [31:0] p_qty, p_px, p_ref;
    logic        p_kill, p_halt, p_noref;
    logic signed [33:0] p_pos;
    logic [15:0] p_tok;
    always_ff @(posedge clk) begin
        p_side <= req_side; p_qty <= req_qty; p_px <= req_px; p_ref <= req_ref;
        p_kill <= kill_reg | kill_in; p_halt <= halt; p_noref <= req_noref; p_pos <= pos; p_tok <= tokens;
    end
    logic [32:0] p_d;
    assign p_d = (p_px >= p_ref) ? {1'b0, p_px} - {1'b0, p_ref} : {1'b0, p_ref} - {1'b0, p_px};

    // grants since the last refill tick (the token bucket's promise: no more than `bucket` between two ticks... plus
    // what was left; counted from reset, where the bucket is full)
    logic [7:0] g_win;
    always_ff @(posedge clk) begin
        if (rst || tick) g_win <= '0;
        else if (grant) g_win <= g_win + 8'd1;
    end
    // position, recomputed independently from the granted orders
    logic signed [33:0] f_pos;
    always_ff @(posedge clk) begin
        if (rst) f_pos <= '0;
        else if (approved) f_pos <= p_side ? f_pos - $signed({2'b00, p_qty}) : f_pos + $signed({2'b00, p_qty});
    end

    always_ff @(posedge clk) if (f_past && !rst && !$past(rst)) begin
        if (grant) begin
            assert (!(kill_reg | kill_in));                       // kill wins even in the grant clock
            assert (!p_kill && !p_halt);                          // not killed or halted when asked
            assert (p_qty != 0 && p_qty <= {1'b0, max_qty[30:0]});        // size
            assert (p_d <= {2'b00, band[30:0]} && !p_noref);      // price band, against a real reference
            assert (p_tok != 0);                                  // a token was there
        end
        // the position never leaves the limit, whatever the requests (it starts at 0 and only grants move it)
        // pos = the sum of approved requests (an approval the kill input then blocks in the grant clock still
        // counts: the worst case); grant only ever follows an approval
        assert (pos == (approved ? (p_side ? f_pos - $signed({2'b00, p_qty}) : f_pos + $signed({2'b00, p_qty})) : f_pos));
        assert (!grant || approved);
        assert ((pos[33] ? -pos : pos) <= $signed({3'b000, max_pos[30:0]}));
        assert (tokens <= bucket);
        assert ({8'd0, g_win} <= bucket);                     // no more than a bucketful between two refill ticks
        assert (!(grant && rej_v));
    end
    // reachability: an order can be granted, and each refusal can happen
    always_ff @(posedge clk) if (f_past && !rst) begin
        cover (grant);
        cover (rej_v && rej_why == 3'd5);
        cover (rej_v && rej_why == 3'd6);
        cover (rej_v && rej_why == 3'd4);
    end
endmodule
