// dsp_mul_pipe_ooc (brief 185): kept registers on every input and output of dsp_mul_pipe, so that the timed path is register to register and the
// boundary registers are not absorbed into the slice under test (DONT_TOUCH). The two boundary registers are not part of the module's latency.
module dsp_mul_pipe_ooc #(
    parameter int WA   = 18,
    parameter int WB   = 18,
    parameter int NA   = 1,
    parameter int NM   = 1,
    parameter int NP   = 1,
    parameter int RSTP = 0
) (
    input  logic                    clk,
    input  logic                    rst,
    input  logic signed [WA-1:0]    a,
    input  logic signed [WB-1:0]    b,
    output logic signed [WA+WB-1:0] p
);
    (* dont_touch = "true" *) logic signed [WA-1:0] a_q;
    (* dont_touch = "true" *) logic signed [WB-1:0] b_q;
    (* dont_touch = "true" *) logic rst_q;
    logic signed [WA+WB-1:0] p_w;
    (* dont_touch = "true" *) logic signed [WA+WB-1:0] p_q;
    always_ff @(posedge clk) begin
        a_q <= a;
        b_q <= b;
        rst_q <= rst;
        p_q <= p_w;
    end
    assign p = p_q;
    dsp_mul_pipe #(.WA(WA), .WB(WB), .NA(NA), .NM(NM), .NP(NP), .RSTP(RSTP)) u_dut (.clk(clk), .rst(rst_q), .a(a_q), .b(b_q), .p(p_w));
endmodule
