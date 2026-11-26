// dsp_simd_pat_ooc (brief 185): kept boundary registers around dsp_simd_pat.
module dsp_simd_pat_ooc #(
    parameter int MODE = 0
) (
    input  logic        clk,
    input  logic [47:0] a,
    input  logic [47:0] b,
    output logic [47:0] y,
    output logic        hit
);
    (* dont_touch = "true" *) logic [47:0] a_q, b_q;
    logic [47:0] y_w;
    logic hit_w;
    (* dont_touch = "true" *) logic [47:0] y_q;
    (* dont_touch = "true" *) logic hit_q;
    always_ff @(posedge clk) begin
        a_q <= a;
        b_q <= b;
        y_q <= y_w;
        hit_q <= hit_w;
    end
    assign y = y_q;
    assign hit = hit_q;
    dsp_simd_pat #(.MODE(MODE)) u_dut (.clk(clk), .a(a_q), .b(b_q), .y(y_w), .hit(hit_w));
endmodule
