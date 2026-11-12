// interlocks.sv: the safety checks every order passes on the fast path (brief 58A step 5).
//
// A request (req_v) is granted one clock later (grant) unless, checked in this order:
//   kill      the kill register or the kill input is set (kill also blocks a grant in the clock it rises)
//   halt      trading is halted (a sequence gap with halt-on-gap set, until the host clears it)
//   qty       the quantity is zero or above max_qty (a fat-finger size)
//   band      the order price is more than band from the reference price (a fat-finger price)
//   position  the position after the order would exceed max_pos in either direction
//   rate      no token is left: a bucket of `bucket` tokens, one token back every `refill` clocks
// A grant takes one token and moves the position by the quantity (buy +, sell -). The position counts every order
// granted, whether or not it is later filled or cancelled (no fills exist on the bench), so it is the worst case.
// Configuration values are taken as unsigned 31-bit numbers (bit 31 ignored) so the arithmetic cannot wrap.
// Properties: verif/formal/formal_interlocks.sv.

module interlocks (
    input  logic        clk,
    input  logic        rst,
    input  logic        kill_reg,
    input  logic        kill_in,
    input  logic        halt,
    input  logic [31:0] max_qty,
    input  logic [31:0] band,
    input  logic [31:0] max_pos,
    input  logic [15:0] bucket,
    input  logic [31:0] refill,
    input  logic        reload,         // fill the bucket to `bucket` tokens (the host wrote the bucket size)
    input  logic        req_v,
    input  logic        req_side,       // 0 buy, 1 sell
    input  logic [31:0] req_qty,
    input  logic [31:0] req_px,
    input  logic [31:0] req_ref,
    output logic        grant,
    output logic        rej_v,
    output logic [2:0]  rej_why,        // 1 kill, 2 halt, 3 qty, 4 band, 5 position, 6 rate
    output logic signed [33:0] pos,
    output logic [15:0] tokens,
    output logic        approved,       // the request was approved last clock (grant = approved and not killed now)
    output logic        tick            // a refill tick this clock
);
    logic [30:0] mq, bd, mp;
    assign mq = max_qty[30:0];
    assign bd = band[30:0];
    assign mp = max_pos[30:0];

    logic               kill_now;
    assign kill_now = kill_reg | kill_in;

    logic [32:0]        dpx;
    logic signed [33:0] npos;
    logic [33:0]        nabs;
    always_comb begin
        dpx  = (req_px >= req_ref) ? ({1'b0, req_px} - {1'b0, req_ref}) : ({1'b0, req_ref} - {1'b0, req_px});
        npos = req_side ? pos - $signed({2'b00, req_qty}) : pos + $signed({2'b00, req_qty});
        nabs = npos[33] ? 34'(-npos) : 34'(npos);
    end

    logic [2:0] why;
    always_comb begin
        if (kill_now)                                   why = 3'd1;
        else if (halt)                                  why = 3'd2;
        else if (req_qty == 0 || req_qty > {1'b0, mq})  why = 3'd3;
        else if (dpx > {2'b00, bd})                     why = 3'd4;
        else if (nabs > {3'b000, mp})                   why = 3'd5;
        else if (tokens == 0)                           why = 3'd6;
        else                                            why = 3'd0;
    end

    logic        g_q;
    logic [31:0] rt;
    always_ff @(posedge clk) begin
        rej_v <= 1'b0;
        g_q   <= 1'b0;
        if (rst) begin
            pos <= '0; tokens <= bucket; rt <= '0; rej_why <= '0;
        end else begin
            // refill
            if (rt + 32'd1 >= refill) begin
                rt <= '0;
                if (tokens < bucket) tokens <= tokens + 16'd1;
            end else rt <= rt + 32'd1;
            if (tokens > bucket) tokens <= bucket;                      // the host lowered the bucket
            if (reload) tokens <= bucket;
            if (req_v) begin
                if (why == 3'd0) begin
                    g_q    <= 1'b1;
                    pos    <= npos;
                    tokens <= tokens - 16'd1;                           // wins over a refill in the same clock
                end else begin
                    rej_v   <= 1'b1;
                    rej_why <= why;
                end
            end
        end
    end
    assign grant    = g_q & ~kill_now;
    assign approved = g_q;
    assign tick     = (rt + 32'd1 >= refill);
endmodule
