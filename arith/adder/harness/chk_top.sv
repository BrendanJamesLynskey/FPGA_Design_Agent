// chk_top: the instance under test with adder_checker beside it (arith brief 139a). run_harness.py --checker builds this with a generated dut_defs.svh (`define DUT_MODULE <your module>,
// `define DUT_PARAMS "#(.WIDTH(WIDTH),...)" (the parameters you pass, taken from this wrapper's parameters of the same name); the port list is the adder contract's.
`include "dut_defs.svh"
module chk_top #(
    parameter int WIDTH  = 32,
    parameter int BLOCK  = 8,
    parameter int STAGES = 4,
    parameter int LAT    = 0
) (
    input  logic             clk,
    input  logic [WIDTH-1:0] a,
    input  logic [WIDTH-1:0] b,
    input  logic             cin,
    input  logic             sub,
    output logic [WIDTH-1:0] s,
    output logic             co,
    output logic             ovf,
    output logic [31:0]      errors
);
    // verilator lint_off UNUSEDPARAM
    `DUT_MODULE `DUT_PARAMS u_dut (.clk(clk), .a(a), .b(b), .cin(cin), .sub(sub), .s(s), .co(co), .ovf(ovf));
    // verilator lint_on UNUSEDPARAM
    adder_checker #(.WIDTH(WIDTH), .LAT(LAT)) u_chk (.clk(clk), .a(a), .b(b), .cin(cin), .sub(sub), .s(s), .co(co), .ovf(ovf), .errors(errors));
endmodule
