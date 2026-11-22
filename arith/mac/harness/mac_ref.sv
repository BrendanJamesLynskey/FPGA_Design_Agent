// mac_ref: the multiply-accumulate of arith/mac/spec.md written as plainly as the specification reads, as the reference of the formal jobs (arith brief 139a).
// A sample presented at a clock is applied LAT - 1 clocks later by one accumulate: acc <= (clr ? 0 : acc) + the sum of the lane products (plain `*` on signed
// or unsigned integers, summed in ACCW bits). rst (synchronous) clears acc and every sample in flight. It is the model's delay line in RTL form, with no
// DSP-oriented coding and no operand registers, so a variant that agrees with it agrees with the specification, whatever its own pipeline looks like.
module mac_ref #(
    parameter int WA     = 4,
    parameter int WB     = 4,
    parameter int LANES  = 1,
    parameter int ACCW   = 8,
    parameter int SIGNED = 1,
    parameter int LAT    = 1
) (
    input  logic                clk,
    input  logic                rst,
    input  logic                en,
    input  logic                clr,
    input  logic [LANES*WA-1:0] a,
    input  logic [LANES*WB-1:0] b,
    output logic [ACCW-1:0]     acc
);
    logic [LANES*WA-1:0] a_d [LAT];
    logic [LANES*WB-1:0] b_d [LAT];
    logic                en_d [LAT];
    logic                clr_d [LAT];
    always_comb begin
        a_d[0] = a;
        b_d[0] = b;
        en_d[0] = en;
        clr_d[0] = clr;
    end
    for (genvar i = 1; i < LAT; i++) begin : g_d
        always_ff @(posedge clk) begin
            a_d[i]   <= a_d[i-1];
            b_d[i]   <= b_d[i-1];
            clr_d[i] <= clr_d[i-1];
            if (rst) en_d[i] <= 1'b0;
            else     en_d[i] <= en_d[i-1];
        end
    end

    logic [ACCW-1:0] sum;
    always_comb begin
        sum = '0;
        for (int k = 0; k < LANES; k++) begin
            logic signed [WA:0] x;
            logic signed [WB:0] y;
            logic signed [WA+WB+1:0] p;
            x = SIGNED != 0 ? {a_d[LAT-1][k*WA+WA-1], a_d[LAT-1][k*WA +: WA]} : {1'b0, a_d[LAT-1][k*WA +: WA]};
            y = SIGNED != 0 ? {b_d[LAT-1][k*WB+WB-1], b_d[LAT-1][k*WB +: WB]} : {1'b0, b_d[LAT-1][k*WB +: WB]};
            p = x * y;
            sum = sum + ACCW'(p);
        end
    end
    always_ff @(posedge clk) begin
        if (rst)                 acc <= '0;
        else if (en_d[LAT-1])    acc <= (clr_d[LAT-1] ? '0 : acc) + sum;
    end
endmodule
