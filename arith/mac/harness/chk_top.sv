// chk_top: the instance under test with mac_checker beside it (arith brief 139a). run_harness.py --checker builds this with a generated dut_defs.svh (`define DUT_MODULE <your module>,
// `define DUT_PARAMS "#(.WA(WA),...)" (the parameters you pass, taken from this wrapper's parameters of the same name); the port list is the MAC contract's.
`include "dut_defs.svh"
module chk_top #(
    parameter int WA     = 16,
    parameter int WB     = 16,
    parameter int LANES  = 1,
    parameter int ACCW   = 40,
    parameter int SIGNED = 1,
    parameter int NREG   = 3,
    parameter int LAT    = 3
) (
    input  logic                clk,
    input  logic                rst,
    input  logic                en,
    input  logic                clr,
    input  logic [LANES*WA-1:0] a,
    input  logic [LANES*WB-1:0] b,
    output logic [ACCW-1:0]     acc,
    output logic [31:0]         errors
);
    // verilator lint_off UNUSEDPARAM
    `DUT_MODULE `DUT_PARAMS u_dut (.clk(clk), .rst(rst), .en(en), .clr(clr), .a(a), .b(b), .acc(acc));
    // verilator lint_on UNUSEDPARAM
    mac_checker #(.WA(WA), .WB(WB), .LANES(LANES), .ACCW(ACCW), .SIGNED(SIGNED), .LAT(LAT)) u_chk
        (.clk(clk), .rst(rst), .en(en), .clr(clr), .a(a), .b(b), .acc(acc), .errors(errors));
endmodule
