// fft_window_fv: the window multiplier equals the plain rounding formula for every sample and coefficient, in every clock (arith brief 148).
// The reference is integer arithmetic here (y = (x * w + half) >>> WW, with half = 2**(WW-1) for RND = 1 and 0 otherwise) and shares no code with the block; the block (STAGES = ST) is
// compared with the reference delayed by its own latency once that many clocks have passed since the start. Inputs are free in every clock.
module fft_window_fv #(
    parameter int WD  = 4,
    parameter int WW  = 4,
    parameter int RND = 1,
    parameter int ST  = 3
) (
    input logic              clk,
    input logic [WD-1:0]     xr,
    input logic [WD-1:0]     xi,
    input logic [WW-1:0]     w
);
    logic [WD-1:0] yr, yi;
    fft_window_dsp #(.WD(WD), .WW(WW), .RND(RND), .STAGES(ST)) u (.clk(clk), .xr(xr), .xi(xi), .w(w), .yr(yr), .yi(yi));
    logic signed [WD-1:0]  sr, si;
    logic signed [WD+WW+2:0] pr, pi, half;
    logic [WD-1:0] rr, ri;
    logic [WD-1:0] dr [3];
    logic [WD-1:0] di [3];
    logic [1:0]    warm = 2'd0;
    always_comb begin
        sr = xr; si = xi;
        half = (RND != 0) ? (WD + WW + 3)'(1 << (WW - 1)) : '0;
        pr = (WD + WW + 3)'(sr) * (WD + WW + 3)'({1'b0, w}) + half;
        pi = (WD + WW + 3)'(si) * (WD + WW + 3)'({1'b0, w}) + half;
        rr = WD'(pr >>> WW);
        ri = WD'(pi >>> WW);
    end
    always_ff @(posedge clk) begin
        dr[0] <= rr; di[0] <= ri;
        dr[1] <= dr[0]; di[1] <= di[0];
        dr[2] <= dr[1]; di[2] <= di[1];
        if (warm != 2'd3) warm <= warm + 2'd1;
    end
    always_comb begin
        WIN: assert (ST == 0 ? (yr == rr && yi == ri) : (warm < 2'(ST) || (yr == dr[ST-1] && yi == di[ST-1])));
    end
endmodule
