// source: solutions/p16l05_montgomery/montgomery.sv (course file, unchanged below this line)
// Part 16 lesson 5 exercise: a bit-serial Montgomery multiplier of parameterised width. For an ODD modulus n < 2^W and operands a, b < n it computes r = a * b * 2^-W mod n.
//   Algorithm (radix 2): S = 0; for i = 0 .. W-1: S = S + a[i] * b; if S is odd, S = S + n; S = S / 2.  After W steps S < 2n; one conditional subtraction gives r = S - n if S >= n else S.
//   start (one clock, only while !busy): take a, b, n. One bit of a per clock: W clocks, then one clock for the final subtraction. busy is high from the clock after start until r is ready; done is high for
//   exactly one clock then, and r keeps its value until the next start.  Latency: counting the edge that sampled start as edge 1, done is high after edge W+2 (edge 1 loads, edges 2..W+1 are the steps,
//   edge W+2 subtracts). It must be the same for every a, b and n: no data-dependent early exit, and the final subtraction is a multiplexer, not a branch in time. rst_n is synchronous, active low,
//   clears busy and done. S needs W+2 bits (S < 2n plus the addends before halving).
module montgomery #(
    parameter int W = 64
) (
    input  logic         clk,
    input  logic         rst_n,
    input  logic         start,
    input  logic [W-1:0] a,
    input  logic [W-1:0] b,
    input  logic [W-1:0] n,
    output logic         busy,
    output logic         done,
    output logic [W-1:0] r
);
    logic [W-1:0]  ar, br, nr;
    logic [W+1:0]  s;
    logic [$clog2(W+2)-1:0] cnt;
    logic          fin;
    logic [W+1:0]  sum, sum2;
    always_comb begin
        sum = s + (ar[0] ? {2'b00, br} : '0);
        sum2 = sum[0] ? sum + {2'b00, nr} : sum;
    end
    always_ff @(posedge clk) begin
        done <= 1'b0;
        if (!rst_n) begin busy <= 1'b0; fin <= 1'b0; end
        else if (!busy) begin
            if (start) begin ar <= a; br <= b; nr <= n; s <= '0; cnt <= '0; busy <= 1'b1; fin <= 1'b0; end
        end else if (!fin) begin
            s <= sum2 >> 1;
            ar <= ar >> 1;
            cnt <= cnt + 1'b1;
            if (cnt == W - 1) fin <= 1'b1;
        end else begin
            r <= (s >= {2'b00, nr}) ? (s - {2'b00, nr}) : s[W-1:0];
            busy <= 1'b0;
            done <= 1'b1;
        end
    end
endmodule
