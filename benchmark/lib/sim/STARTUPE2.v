// STARTUPE2.v: simulation stand-in for the 7-series STARTUPE2 primitive (benchmark benches only; never built by
// Vivado, which uses its own). The configuration clock pin (CCLK) is not a port of the user design, so the stub
// copies USRCCLKO (when enabled by USRCCLKTS = 0) to the bench wrapper's `cclk` net by hierarchical name: the
// wrapper module must be named `tb_cclk_bench` and declare `logic cclk;`. Works in Icarus 12 and Verilator 5.048.
module STARTUPE2 #(
    parameter PROG_USR = "FALSE",
    parameter real SIM_CCLK_FREQ = 0.0
) (
    output CFGCLK, output CFGMCLK, output EOS, output PREQ,
    input CLK, input GSR, input GTS, input KEYCLEARB, input PACK,
    input USRCCLKO, input USRCCLKTS, input USRDONEO, input USRDONETS
);
    assign CFGCLK = 1'b0;
    assign CFGMCLK = 1'b0;
    assign EOS = 1'b1;
    assign PREQ = 1'b0;
    always @* tb_cclk_bench.cclk = USRCCLKO & ~USRCCLKTS;
endmodule
