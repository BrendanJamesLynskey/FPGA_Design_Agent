// chk_top: the instance under test with exp2_checker beside it (arith brief 139d). run_harness.py --checker builds this with a generated dut_defs.svh (`define DUT_MODULE <your module>,
// `define DUT_PARAMS "#(.IW(IW),...)" (the parameters you pass, taken from this wrapper's parameters of the same name); the port list is the exp2 contract's.
`include "dut_defs.svh"
module chk_top #(
    parameter int IW        = 12,
    parameter int OW        = 12,
    parameter int REG       = 1,
    parameter int SB        = 5,
    parameter int NIT       = 16,
    parameter int G         = 5,
    parameter int LAT       = 2,
    parameter int ERR_MILLI = 1000
) (
    input  logic            clk,
    input  logic [IW-1:0]   x,
    output logic [OW-1:0]   y,
    output logic [31:0]     errors
);
    // verilator lint_off UNUSEDPARAM
    `DUT_MODULE `DUT_PARAMS u_dut (.clk(clk), .x(x), .y(y));
    // verilator lint_on UNUSEDPARAM
    exp2_checker #(.IW(IW), .OW(OW), .LAT(LAT), .ERR_MILLI(ERR_MILLI)) u_chk (.clk(clk), .x(x), .y(y), .errors(errors));
endmodule
