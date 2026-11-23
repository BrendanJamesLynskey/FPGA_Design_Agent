// dsp_preadd (brief 185): p = (d + a) * b, the symmetric-FIR tap, to see whether Vivado uses the slice's pre-adder.
// VAR 0: operand registers on a, d and (two deep) b, a register on the pre-adder output (ADREG), multiplier register, output register. Latency 4.
// VAR 1: as VAR 0 without the pre-adder register: operand registers, multiplier register, output register. Latency 3.
module dsp_preadd #(
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
    logic signed [WA-1:0] ar, dr;
    logic signed [WB-1:0] br1, br2;
    logic signed [WA:0]   ad, adr;
    logic signed [WA+WB:0] mr;
    always_ff @(posedge clk) begin
        ar <= a;
        dr <= d;
        br1 <= b;
        br2 <= br1;
    end
    assign ad = (WA+1)'(dr) + (WA+1)'(ar);
    if (VAR == 0) begin : g_v0
        always_ff @(posedge clk) begin
            adr <= ad;
            mr  <= adr * br2;
            p   <= mr;
        end
    end else begin : g_v1
        always_ff @(posedge clk) begin
            mr <= ad * br1;
            p  <= mr;
        end
    end
endmodule
