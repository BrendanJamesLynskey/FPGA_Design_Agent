// dsp_simd_pat (brief 185): the two cheap slice features, in one module selected by MODE.
// MODE 0 (SIMD): four independent 12-bit adds on a 48-bit word, lane k of y = lane k of a + lane k of b (wraps inside the lane); use_dsp = "simd". Latency 2
//                (input register, output register).
// MODE 1 (pattern detect): acc <= acc + a * b (P register as accumulator) and hit <= (acc[39:0] == PAT, PAT = 40'h00_0000_ffff), a constant compare
//                on the accumulator that Vivado can map to the slice's pattern detector. Latency 3 to acc (operand, multiplier, accumulate); hit one clock after acc.
module dsp_simd_pat #(
    parameter int MODE = 0
) (
    input  logic               clk,
    input  logic [47:0]        a,
    input  logic [47:0]        b,
    output logic [47:0]        y,
    output logic               hit
);
    if (MODE == 0) begin : g_simd
        logic [47:0] ar, br;
        (* use_dsp = "simd" *) logic [47:0] sum;
        always_comb begin
            for (int k = 0; k < 4; k++) sum[12*k +: 12] = ar[12*k +: 12] + br[12*k +: 12];
        end
        always_ff @(posedge clk) begin
            ar <= a;
            br <= b;
            y  <= sum;
        end
        assign hit = 1'b0;
    end else begin : g_pat
        localparam logic [39:0] PAT = 40'h00_0000_ffff;
        logic signed [17:0] ar, br;
        logic signed [35:0] mr;
        logic signed [47:0] acc;
        always_ff @(posedge clk) begin
            ar  <= a[17:0];
            br  <= b[17:0];
            mr  <= ar * br;
            acc <= acc + 48'(mr);
            hit <= (acc[39:0] == PAT);
        end
        assign y = acc;
    end
endmodule
