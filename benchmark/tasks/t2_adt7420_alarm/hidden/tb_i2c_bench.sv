// tb_i2c_bench.sv: bench wrapper for t2_adt7420_alarm: the board's pull-ups on TMP_SCL / TMP_SDA (tri1), the
// cocotb device model's pull-downs (dev_*_pull = 1 pulls the line low), and TMP_INT driven by the model (the
// sensor's open-drain INT with the FPGA pull-up). scl / sda are the resolved bus levels.
module tb_i2c_bench #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter int          QUARTER        = 250,
    parameter int          PERIOD_CYCLES  = 25_000_000
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    input  logic        dev_scl_pull,
    input  logic        dev_sda_pull,
    input  logic        TMP_INT,
    output logic        scl,
    output logic        sda,
    output logic [15:0] LED
);
    tri1 TMP_SCL, TMP_SDA;
    assign TMP_SCL = dev_scl_pull ? 1'b0 : 1'bz;
    assign TMP_SDA = dev_sda_pull ? 1'b0 : 1'bz;
    assign scl = TMP_SCL;
    assign sda = TMP_SDA;

    t2_adt7420_alarm_top #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES), .QUARTER(QUARTER),
                           .PERIOD_CYCLES(PERIOD_CYCLES)) u_top (
        .CLK100MHZ(CLK100MHZ), .CPU_RESETN(CPU_RESETN), .TMP_SCL(TMP_SCL), .TMP_SDA(TMP_SDA), .TMP_INT(TMP_INT),
        .LED(LED), .UART_TXD_IN(UART_TXD_IN), .UART_RXD_OUT(UART_RXD_OUT));
endmodule
