// dsp_dot_ooc (brief 185): kept boundary registers around dsp_dot (see dsp_mul_pipe_ooc).
module dsp_dot_ooc #(
    parameter int W     = 16,
    parameter int K     = 8,
    parameter int STYLE = 0,
    parameter int TR    = 1
) (
    input  logic                              clk,
    input  logic signed [K*W-1:0]             a,
    input  logic signed [K*W-1:0]             b,
    output logic signed [2*W+$clog2(K)-1:0]   y
);
    (* dont_touch = "true" *) logic signed [K*W-1:0] a_q, b_q;
    logic signed [2*W+$clog2(K)-1:0] y_w;
    (* dont_touch = "true" *) logic signed [2*W+$clog2(K)-1:0] y_q;
    always_ff @(posedge clk) begin
        a_q <= a;
        b_q <= b;
        y_q <= y_w;
    end
    assign y = y_q;
    dsp_dot #(.W(W), .K(K), .STYLE(STYLE), .TR(TR)) u_dut (.clk(clk), .a(a_q), .b(b_q), .y(y_w));
endmodule
