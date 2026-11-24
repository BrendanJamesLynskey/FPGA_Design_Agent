// sqrt_r4_iter: integer square root by the radix-4 digit recurrence, one digit (two root bits) per clock (brief 139c).
//   x (W bits, W >= 5) -> root = floor(sqrt(x)) (RW = ceil(W/2) bits), rem = x - root**2 (RW + 1 bits). in_ready is high while idle;
//   one result per RP + 1 clocks, RP = ceil(RW/2); latency RP + 1.
// Each step shifts four radicand bits into the remainder and tries the three trial values 8q+1, 16q+4, 24q+9 (the radix-4 digits 1, 2, 3)
// at once; the largest that fits is the digit. The digit set is {0,1,2,3}, non-redundant, so the remainder is an ordinary binary number.
// Primitive use (intended, not yet measured): three (QW+4)-bit subtractors in parallel (ceil((QW+4)/4) CARRY4 each) whose borrows select
// the result, plus one adder for 24q+9; against isqrt_restoring_iter it halves the clocks and roughly triples the carry chains.
module sqrt_r4_iter #(
    parameter int W = 16                  // radicand width, 5 or more
) (
    input  logic            clk,
    input  logic            rst,
    input  logic            in_valid,
    output logic            in_ready,
    input  logic [W-1:0]    x,
    output logic            out_valid,    // one clock, RP + 1 clocks after the accepting edge
    output logic [(W+1)/2-1:0] root,
    output logic [(W+1)/2:0]   rem
);
    localparam int RW = (W + 1) / 2;
    localparam int RP = (RW + 1) / 2;
    localparam int QW = 2 * RP;
    localparam int CW = $clog2(RP + 1);

    logic            busy;
    logic [CW-1:0]   cnt;
    logic [4*RP-1:0] xs;                  // radicand bits still to come, next nibble at the top
    logic [QW-1:0]   q;
    logic [QW:0]     r;
    logic [QW+2:0]   sh;                  // 16*rem + nibble: below 2**(QW+3) because rem <= 2q and q < 4**(RP-1) before the last step
    logic [QW-3:0]   qq;                  // q before the step is below 4**(RP-1)
    logic [QW+2:0]   t1, t2, t3;
    logic [QW+3:0]   d1, d2, d3;          // MSB = borrow
    logic [QW:0]     r_n;
    logic [QW-1:0]   q_n;
    logic            unused;

    assign in_ready = ~busy;
    assign sh = {r[QW-2:0], xs[4*RP-1:4*RP-4]};
    assign qq = q[QW-3:0];
    assign t1 = {2'b00, qq, 3'b001};
    assign t2 = {1'b0, qq, 4'b0100};
    assign t3 = (QW+3)'({qq, 4'b0000}) + (QW+3)'({qq, 3'b000}) + (QW+3)'(9);   // 24*q + 9
    assign d1 = {1'b0, sh} - {1'b0, t1};
    assign d2 = {1'b0, sh} - {1'b0, t2};
    assign d3 = {1'b0, sh} - {1'b0, t3};
    always_comb begin
        if (!d3[QW+3])      begin r_n = d3[QW:0]; q_n = {q[QW-3:0], 2'b11}; end
        else if (!d2[QW+3]) begin r_n = d2[QW:0]; q_n = {q[QW-3:0], 2'b10}; end
        else if (!d1[QW+3]) begin r_n = d1[QW:0]; q_n = {q[QW-3:0], 2'b01}; end
        else                begin r_n = sh[QW:0]; q_n = {q[QW-3:0], 2'b00}; end
    end
    assign root = q[RW-1:0];
    assign rem  = r[RW:0];
    if (QW > RW) begin : g_un
        assign unused = &{1'b0, q[QW-1:RW], r[QW:RW+1], d1[QW+2:QW+1], d2[QW+2:QW+1], d3[QW+2:QW+1]};
    end else begin : g_un
        assign unused = &{1'b0, d1[QW+2:QW+1], d2[QW+2:QW+1], d3[QW+2:QW+1]};
    end

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
                if (cnt == CW'(RP - 1)) begin
                    busy      <= 1'b0;
                    out_valid <= 1'b1;
                end
            end
        end
    end

    always_ff @(posedge clk) begin        // data path: no reset
        if (in_valid && in_ready) begin
            xs <= (4*RP)'(x);
            q  <= '0;
            r  <= '0;
        end else if (busy) begin
            xs <= {xs[4*RP-5:0], 4'b0000};
            q  <= q_n;
            r  <= r_n;
        end
    end
endmodule
