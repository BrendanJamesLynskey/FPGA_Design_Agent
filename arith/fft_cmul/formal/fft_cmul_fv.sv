// fft_cmul_fv: both complex multiplier variants equal the plain formula, for every operand pair in every clock (arith brief 148).
// The reference is written here as integer arithmetic (pr = ar*br - ai*bi, pi = ar*bi + ai*br in 2 * (WA + WB) bit signed variables) and shares no code with the variants; each variant
// (STAGES = ST) is compared with the reference delayed by its own latency, once that many clocks have passed since the start. Inputs are free in every clock.
module fft_cmul_fv #(
    parameter int WA = 4,
    parameter int WB = 4,
    parameter int ST = 3
) (
    input logic              clk,
    input logic [WA-1:0]     ar,
    input logic [WA-1:0]     ai,
    input logic [WB-1:0]     br,
    input logic [WB-1:0]     bi
);
    localparam int WP = WA + WB + 1;
    logic [WP-1:0] pr4, pi4, pr3, pi3;
    fft_cmul_m4 #(.WA(WA), .WB(WB), .STAGES(ST)) u4 (.clk(clk), .ar(ar), .ai(ai), .br(br), .bi(bi), .pr(pr4), .pi(pi4));
    fft_cmul_m3 #(.WA(WA), .WB(WB), .STAGES(ST)) u3 (.clk(clk), .ar(ar), .ai(ai), .br(br), .bi(bi), .pr(pr3), .pi(pi3));
    logic signed [WA-1:0] sar, sai;
    logic signed [WB-1:0] sbr, sbi;
    logic signed [WP+WA+WB:0] rr, ri;
    logic [WP-1:0] dr [3];
    logic [WP-1:0] di [3];
    logic [1:0]    warm = 2'd0;
    always_comb begin
        sar = ar; sai = ai; sbr = br; sbi = bi;
        rr = (WP + WA + WB + 1)'(sar) * (WP + WA + WB + 1)'(sbr) - (WP + WA + WB + 1)'(sai) * (WP + WA + WB + 1)'(sbi);
        ri = (WP + WA + WB + 1)'(sar) * (WP + WA + WB + 1)'(sbi) + (WP + WA + WB + 1)'(sai) * (WP + WA + WB + 1)'(sbr);
    end
    always_ff @(posedge clk) begin
        dr[0] <= WP'(rr);
        di[0] <= WP'(ri);
        dr[1] <= dr[0];
        di[1] <= di[0];
        dr[2] <= dr[1];
        di[2] <= di[1];
        if (warm != 2'd3) warm <= warm + 2'd1;
    end
    always_comb begin
        M4: assert (ST == 0 ? (pr4 == WP'(rr) && pi4 == WP'(ri)) : (warm < 2'(ST) || (pr4 == dr[ST-1] && pi4 == di[ST-1])));
        M3: assert (ST == 0 ? (pr3 == WP'(rr) && pi3 == WP'(ri)) : (warm < 2'(ST) || (pr3 == dr[ST-1] && pi3 == di[ST-1])));
    end
endmodule
