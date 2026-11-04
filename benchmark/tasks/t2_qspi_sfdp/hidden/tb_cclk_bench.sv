// tb_cclk_bench.sv: bench wrapper for t2_qspi_sfdp. The STARTUPE2 simulation stub (benchmark/lib/sim/STARTUPE2.v)
// copies USRCCLKO (enabled by USRCCLKTS = 0) onto this module's `cclk`, the configuration clock pin the flash sees.
module tb_cclk_bench #(
    parameter int CLKS_PER_BIT   = 868,
    parameter int TIMEOUT_CYCLES = 100_000,
    parameter int HALF           = 10
) (
    input  logic CLK100MHZ,
    input  logic CPU_RESETN,
    input  logic UART_TXD_IN,
    output logic UART_RXD_OUT,
    output logic QSPI_CSN,
    output logic QSPI_DQ0,
    input  logic QSPI_DQ1,
    output logic QSPI_DQ2,
    output logic QSPI_DQ3,
    output logic sck
);
    logic cclk;
    initial cclk = 1'b0;
    assign sck = cclk;

    t2_qspi_sfdp_top #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES), .HALF(HALF)) u_top (
        .CLK100MHZ(CLK100MHZ), .CPU_RESETN(CPU_RESETN), .QSPI_CSN(QSPI_CSN), .QSPI_DQ0(QSPI_DQ0),
        .QSPI_DQ1(QSPI_DQ1), .QSPI_DQ2(QSPI_DQ2), .QSPI_DQ3(QSPI_DQ3),
        .UART_TXD_IN(UART_TXD_IN), .UART_RXD_OUT(UART_RXD_OUT));
endmodule
