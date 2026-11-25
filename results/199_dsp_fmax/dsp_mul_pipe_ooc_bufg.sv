// dsp_mul_pipe_ooc_bufg (brief 199): the brief-185 wrapper with the clock port driven through a BUFG, so that the clock-buffer limits (data-sheet
// BUFG FMAX) are checked by the pulse-width and timing reports as they are in a real design. Same registers and one slice (1,1,1) as 185.
module dsp_mul_pipe_ooc_bufg (
    input  logic                  clk_in,
    input  logic                  rst,
    input  logic signed [17:0]    a,
    input  logic signed [17:0]    b,
    output logic signed [35:0]    p
);
    logic clk;
    BUFG u_bufg (.I(clk_in), .O(clk));
    dsp_mul_pipe_ooc #(.WA(18), .WB(18), .NA(1), .NM(1), .NP(1), .RSTP(0)) u (.clk(clk), .rst(rst), .a(a), .b(b), .p(p));
endmodule
