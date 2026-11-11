// Lint-only stand-in for the XADC primitive (the real one is a Vivado primitive).
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off DECLFILENAME */
module XADC #(
    parameter [15:0] INIT_40 = 0, INIT_41 = 0, INIT_42 = 0, INIT_48 = 0, INIT_49 = 0, INIT_4A = 0, INIT_4B = 0,
    parameter [15:0] INIT_4C = 0, INIT_4D = 0, INIT_4E = 0, INIT_4F = 0, INIT_50 = 0, INIT_51 = 0, INIT_52 = 0,
    parameter [15:0] INIT_53 = 0, INIT_54 = 0, INIT_55 = 0, INIT_56 = 0, INIT_57 = 0, INIT_58 = 0, INIT_5C = 0,
    parameter SIM_DEVICE = "7SERIES"
) (
    input DCLK, DEN, DWE, input [6:0] DADDR, input [15:0] DI, output [15:0] DO, output DRDY,
    input RESET, CONVST, CONVSTCLK, VP, VN, input [15:0] VAUXP, VAUXN,
    output ALM, OT, BUSY, output [4:0] CHANNEL, output EOC, EOS, JTAGBUSY, JTAGLOCKED, JTAGMODIFIED, output [4:0] MUXADDR
);
    assign {DO, DRDY, ALM, OT, BUSY, CHANNEL, EOC, EOS, JTAGBUSY, JTAGLOCKED, JTAGMODIFIED, MUXADDR} = '0;
endmodule
