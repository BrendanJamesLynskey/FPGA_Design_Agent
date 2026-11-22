// isqrt_restoring_iter: integer square root by the restoring digit-by-digit recurrence, one result bit per clock (brief 139b).
//   x (W bits, W >= 3) -> root = floor(sqrt(x)) (RW = ceil(W/2) bits), rem = x - root**2 (RW + 1 bits). in_ready is high while idle;
//   one result per RW + 1 clocks; latency RW + 1.
// Primitive use (intended, not yet measured): one (RW+2)-bit subtractor (ceil((RW+2)/4) CARRY4; half the width of a W-bit divider's
// because the root has half the bits) whose borrow is the root bit and the restore mux select; the trial value is {root, 2'b01}, so it
// needs no adder of its own. Flip-flops: remaining radicand (2*RW), root (RW), remainder (RW+1), counter.
module isqrt_restoring_iter #(
    parameter int W = 16                  // radicand width, 3 or more
) (
    input  logic            clk,
    input  logic            rst,
    input  logic            in_valid,
    output logic            in_ready,
    input  logic [W-1:0]    x,
    output logic            out_valid,    // one clock, RW + 1 clocks after the accepting edge
    output logic [(W+1)/2-1:0] root,
    output logic [(W+1)/2:0]   rem
);
    localparam int RW = (W + 1) / 2;
    localparam int CW = $clog2(RW + 1);

    logic            busy;
    logic [CW-1:0]   cnt;
    logic [2*RW-1:0] xs;                  // radicand bits still to come, next pair at the top
    logic [RW-1:0]   rt;
    logic [RW:0]     rm;
    logic [RW+1:0]   sh;                  // 4*rem + pair: below 2**(RW+2) because rem is below 2**(iterations done + 1)
    logic [RW:0]     trial;               // 4*root + 1: below 2**(RW+1) because root is below 2**(RW-1) before the last step
    logic [RW+2:0]   t;
    logic            unused;

    assign in_ready = ~busy;
    assign sh    = {rm[RW-1:0], xs[2*RW-1:2*RW-2]};
    assign trial = {rt[RW-2:0], 2'b01};
    assign t     = {1'b0, sh} - {2'b00, trial};     // t[RW+2] = borrow
    assign root  = rt;
    assign rem   = rm;
    assign unused = &{1'b0, rm[RW], rt[RW-1], t[RW+1]};

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
                if (cnt == CW'(RW - 1)) begin
                    busy      <= 1'b0;
                    out_valid <= 1'b1;
                end
            end
        end
    end

    always_ff @(posedge clk) begin        // data path: no reset
        if (in_valid && in_ready) begin
            xs <= (2*RW)'(x);
            rt <= '0;
            rm <= '0;
        end else if (busy) begin
            xs <= {xs[2*RW-3:0], 2'b00};
            rt <= {rt[RW-2:0], ~t[RW+2]};
            rm <= t[RW+2] ? sh[RW:0] : t[RW:0];
        end
    end
endmodule
