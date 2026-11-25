// dsp_preadd_ooc (brief 185): kept boundary registers around dsp_preadd.
module dsp_preadd_ooc #(
    parameter int WA  = 24,
    parameter int WB  = 18,
    parameter int VAR = 0
) (
    input  logic                         clk,
    input  logic signed [WA-1:0]         a,
    input  logic signed [WA-1:0]         d,
    input  logic signed [WB-1:0]         b,
    output logic signed [WA+WB:0]        p
);
    (* dont_touch = "true" *) logic signed [WA-1:0] a_q, d_q;
    (* dont_touch = "true" *) logic signed [WB-1:0] b_q;
    logic signed [WA+WB:0] p_w;
    (* dont_touch = "true" *) logic signed [WA+WB:0] p_q;
    always_ff @(posedge clk) begin
        a_q <= a;
        d_q <= d;
        b_q <= b;
        p_q <= p_w;
    end
    assign p = p_q;
    dsp_preadd #(.WA(WA), .WB(WB), .VAR(VAR)) u_dut (.clk(clk), .a(a_q), .d(d_q), .b(b_q), .p(p_w));
endmodule
