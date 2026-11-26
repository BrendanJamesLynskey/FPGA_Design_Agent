// chk_top: the instance under test with fp_fma_checker beside it (arith brief 139e). run_harness.py --checker builds this with a generated dut_defs.svh (`define DUT_MODULE <your module>,
// `define DUT_PARAMS "#(.EXP(EXP),...)" (the parameters you pass, taken from this wrapper's parameters of the same name); the port list is the fp_fma contract's.
`include "dut_defs.svh"
module chk_top #(
    parameter int EXP      = 8,
    parameter int MAN      = 23,
    parameter int SUBNORM  = 1,
    parameter int STAGES   = 4,
    parameter int STAGES_M = -1,                       // given only for the cascade: then the checker expects two roundings
    parameter int STAGES_A = 3,
    parameter int LAT      = 0
) (
    input  logic                clk,
    input  logic [EXP+MAN:0]    a,
    input  logic [EXP+MAN:0]    b,
    input  logic [EXP+MAN:0]    c,
    output logic [EXP+MAN:0]    y,
    output logic [31:0]         errors
);
    localparam int ROUNDS = (STAGES_M >= 0) ? 2 : 1;
    // verilator lint_off UNUSEDPARAM
    `DUT_MODULE `DUT_PARAMS u_dut (.clk(clk), .a(a), .b(b), .c(c), .y(y));
    // verilator lint_on UNUSEDPARAM
    fp_fma_checker #(.EXP(EXP), .MAN(MAN), .SUBNORM(SUBNORM), .ROUNDS(ROUNDS), .LAT(LAT)) u_chk (.clk(clk), .a(a), .b(b), .c(c), .y(y), .errors(errors));
endmodule
