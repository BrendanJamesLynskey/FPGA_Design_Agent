// divider_hr_fix: the last step of a division (brief 139c), combinational: add the two words of the remainder, and if the sum is negative take the
// quotient QM = Q - 1 and add the divisor back, so 0 <= R < b. CS = 1: (us, uc) are carry-save (W + 3 bits each); CS = 0: us holds the W + 1 bit
// two's-complement remainder and uc is ignored.
module divider_hr_fix #(
    parameter int W  = 16,
    parameter int QW = 9,
    parameter bit CS = 1'b1
) (
    input  logic [W+2:0]  us,
    input  logic [W+2:0]  uc,
    input  logic [W-1:0]  b,
    input  logic [QW-1:0] qq,
    input  logic [QW-1:0] qm,
    output logic [QW-1:0] quo,
    output logic [W-1:0]  rem
);
    localparam int WW = W + 3;
    logic [WW-1:0] u, ua;
    logic          neg;
    logic          unused;
    if (CS) begin : g_cs
        assign u = us + uc;
        assign unused = 1'b0;
    end else begin : g_cpa
        assign u = {{2{us[W]}}, us[W:0]};
        assign unused = &{1'b0, us[WW-1:W+1], uc};
    end
    assign neg = u[WW-1];
    assign ua  = u + {3'b000, b};
    assign quo = neg ? qm : qq;
    assign rem = neg ? ua[W-1:0] : u[W-1:0];
    logic unused_u;
    assign unused_u = &{1'b0, u[WW-2:W], ua[WW-1:W]};
endmodule
