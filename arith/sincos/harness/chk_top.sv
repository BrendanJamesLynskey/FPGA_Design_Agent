// chk_top: the instance under test with sincos_checker beside it (arith brief 139d). run_harness.py --checker builds this with a generated dut_defs.svh (`define DUT_MODULE <your module>,
// `define DUT_PARAMS "#(.PH(PH),...)" (the parameters you pass, taken from this wrapper's parameters of the same name); the port list is the sincos contract's.
`include "dut_defs.svh"
module chk_top #(
    parameter int PH        = 14,
    parameter int OW        = 14,
    parameter int SB        = 5,
    parameter int NIT       = 14,
    parameter int G         = 4,
    parameter int LAT       = 2,
    parameter int ERR_MILLI = 3000
) (
    input  logic                  clk,
    input  logic [PH-1:0]         phase,
    output logic [OW-1:0]         s,
    output logic [OW-1:0]         c,
    output logic [31:0]           errors
);
    // verilator lint_off UNUSEDPARAM
    `DUT_MODULE `DUT_PARAMS u_dut (.clk(clk), .phase(phase), .s(s), .c(c));
    // verilator lint_on UNUSEDPARAM
    sincos_checker #(.PH(PH), .OW(OW), .LAT(LAT), .ERR_MILLI(ERR_MILLI)) u_chk (.clk(clk), .phase(phase), .s(s), .c(c), .errors(errors));
endmodule
