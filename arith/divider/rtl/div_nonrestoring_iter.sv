// div_nonrestoring_iter: unsigned W-bit non-restoring divider, one quotient bit per clock, then one correction clock (brief 139b).
//   n / d -> q, r; d = 0 gives q = all ones, r = n. in_ready is high while idle; one result per W + 2 clocks; latency W + 2.
// Primitive use (intended, not yet measured): one (W+2)-bit adder/subtractor (add or subtract chosen by the sign of the partial remainder:
// one LUT per bit in front of the carry chain, ceil((W+2)/4) CARRY4) and no restore multiplexer; the sign of the result is the next
// quotient bit. The correction (add the divisor back to a negative final remainder) is a second adder of W + 1 bits (ceil((W+1)/4) CARRY4) used
// in its own clock, so the iteration path is one add/subtract chain, as short as the restoring divider's; a tool that shares the two adders
// would put a multiplexer in front of the chain. Flip-flops: partial remainder, dividend/quotient shift register, divisor, counter.
module div_nonrestoring_iter #(
    parameter int W = 8
) (
    input  logic         clk,
    input  logic         rst,
    input  logic         in_valid,
    output logic         in_ready,
    input  logic [W-1:0] n,
    input  logic [W-1:0] d,
    output logic         out_valid,       // one clock, W + 2 clocks after the accepting edge
    output logic [W-1:0] q,
    output logic [W-1:0] r
);
    localparam int CW = $clog2(W + 2);

    logic          busy;
    logic [CW-1:0] cnt;
    logic [W-1:0]  rn;
    logic [W-1:0]  dd;
    logic [W:0]    p;                     // signed partial remainder, W + 1 bits
    logic [W+1:0]  sh;
    logic [W+1:0]  t;

    assign in_ready = ~busy;
    assign sh = {p, rn[W-1]};
    assign t  = p[W] ? sh + {2'b00, dd} : sh - {2'b00, dd};
    assign q  = rn;
    assign r  = p[W-1:0];

    always_ff @(posedge clk) begin
        if (rst) begin
            busy      <= 1'b0;
            out_valid <= 1'b0;
            cnt       <= '0;
        end else begin
            out_valid <= 1'b0;
            if (in_valid && in_ready) begin
                busy <= 1'b1;
                cnt  <= '0;
            end else if (busy) begin
                cnt <= cnt + 1'b1;
                if (cnt == CW'(W)) begin  // the correction clock is the last
                    busy      <= 1'b0;
                    out_valid <= 1'b1;
                end
            end
        end
    end

    always_ff @(posedge clk) begin        // data path: no reset
        if (in_valid && in_ready) begin
            rn <= n;
            dd <= d;
            p  <= '0;
        end else if (busy) begin
            if (cnt == CW'(W)) begin
                if (p[W]) p <= p + {1'b0, dd};
            end else begin
                p  <= t[W:0];
                rn <= {rn[W-2:0], ~t[W+1]};
            end
        end
    end
endmodule
