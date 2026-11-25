// chk_top: the instance under test with mult_checker beside it (arith brief 139a). run_harness.py --checker builds this with a generated dut_defs.svh (`define DUT_MODULE <your module>,
// `define DUT_PARAMS "#(.WA(WA),...)" (the parameters you pass, taken from this wrapper's parameters of the same name); the port list is the multiplier contract's.
`include "dut_defs.svh"
module chk_top #(
    parameter int WA     = 18,
    parameter int WB     = 18,
    parameter int SIGNED = 1,
    parameter int STAGES = 3,
    parameter int REG    = 0,
    parameter int LAT    = 0
) (
    input  logic                clk,
    input  logic [WA-1:0]       a,
    input  logic [WB-1:0]       b,
    output logic [WA+WB-1:0]    p,
    output logic [31:0]         errors
);
    // verilator lint_off UNUSEDPARAM
    `DUT_MODULE `DUT_PARAMS u_dut (.clk(clk), .a(a), .b(b), .p(p));
    // verilator lint_on UNUSEDPARAM
    mult_checker #(.WA(WA), .WB(WB), .SIGNED(SIGNED), .LAT(LAT)) u_chk (.clk(clk), .a(a), .b(b), .p(p), .errors(errors));
endmodule
