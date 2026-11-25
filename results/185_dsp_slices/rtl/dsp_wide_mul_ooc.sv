// dsp_wide_mul_ooc (brief 185): kept boundary registers around dsp_wide_mul (see dsp_mul_pipe_ooc).
module dsp_wide_mul_ooc #(
    parameter int WA    = 32,
    parameter int WB    = 32,
    parameter int STYLE = 0,
    parameter int NA    = 1,
    parameter int LB    = 24
) (
    input  logic                    clk,
    input  logic signed [WA-1:0]    a,
    input  logic signed [WB-1:0]    b,
    output logic signed [WA+WB-1:0] p
);
    (* dont_touch = "true" *) logic signed [WA-1:0] a_q;
    (* dont_touch = "true" *) logic signed [WB-1:0] b_q;
    logic signed [WA+WB-1:0] p_w;
    (* dont_touch = "true" *) logic signed [WA+WB-1:0] p_q;
    always_ff @(posedge clk) begin
        a_q <= a;
        b_q <= b;
        p_q <= p_w;
    end
    assign p = p_q;
    dsp_wide_mul #(.WA(WA), .WB(WB), .STYLE(STYLE), .NA(NA), .LB(LB)) u_dut (.clk(clk), .a(a_q), .b(b_q), .p(p_w));
endmodule
