// chk_top: the instance under test with atan2_checker beside it (arith brief 139d). run_harness.py --checker builds this with a generated dut_defs.svh (`define DUT_MODULE <your module>,
// `define DUT_PARAMS "#(.W(W),...)" (the parameters you pass, taken from this wrapper's parameters of the same name); the port list is the atan2_mag contract's.
`include "dut_defs.svh"
module chk_top #(
    parameter int W             = 12,
    parameter int PH            = 12,
    parameter int NIT           = 14,
    parameter int G             = 8,
    parameter int GRP           = 2,
    parameter int LAT           = 16,
    parameter int ERR_MILLI     = 1000,
    parameter int ERR_MAG_MILLI = 1000
) (
    input  logic          clk,
    input  logic [W-1:0]  x,
    input  logic [W-1:0]  y,
    output logic [PH-1:0] ang,
    output logic [W-1:0]  mag,
    output logic [31:0]   errors
);
    // verilator lint_off UNUSEDPARAM
    `DUT_MODULE `DUT_PARAMS u_dut (.clk(clk), .x(x), .y(y), .ang(ang), .mag(mag));
    // verilator lint_on UNUSEDPARAM
    atan2_checker #(.W(W), .PH(PH), .LAT(LAT), .ERR_MILLI(ERR_MILLI), .ERR_MAG_MILLI(ERR_MAG_MILLI)) u_chk (.clk(clk), .x(x), .y(y), .ang(ang), .mag(mag), .errors(errors));
endmodule
