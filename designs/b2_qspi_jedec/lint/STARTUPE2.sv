// Lint-only stand-in for the Xilinx STARTUPE2 primitive (ports as in UG953), so the
// lint step can check b2_qspi_jedec_top. flow/lint.sh adds designs/<name>/lint/*.sv;
// synthesis never reads this file (build.yaml lists rtl/ only).
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNUSEDPARAM */
module STARTUPE2 #(
    parameter string PROG_USR      = "FALSE",
    parameter real   SIM_CCLK_FREQ = 0.0
) (
    output logic CFGCLK, CFGMCLK, EOS, PREQ,
    input  logic CLK, GSR, GTS, KEYCLEARB, PACK,
    input  logic USRCCLKO, USRCCLKTS, USRDONEO, USRDONETS
);
    assign CFGCLK = 1'b0;
    assign CFGMCLK = 1'b0;
    assign EOS = 1'b1;
    assign PREQ = 1'b0;
endmodule
/* verilator lint_on UNUSEDPARAM */
/* verilator lint_on UNUSEDSIGNAL */
