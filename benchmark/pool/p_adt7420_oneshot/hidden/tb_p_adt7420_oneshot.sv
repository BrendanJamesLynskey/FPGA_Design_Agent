// Simulation wrapper: open-drain I2C bus with pull-ups; the device model pulls SDA low.
module tb_p_adt7420_oneshot #(
    parameter int CLKS_PER_BIT = 868, parameter int TIMEOUT_CYCLES = 100000,
    parameter int QUARTER = 250, parameter int CONV_WAIT = 30000000
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED,
    input  logic        dev_sda_pull,
    output logic        scl,
    output logic        sda
);
    tri1 scl_w;
    tri1 sda_w;
    assign sda_w = dev_sda_pull ? 1'b0 : 1'bz;
    assign scl = scl_w;
    assign sda = sda_w;
    p_adt7420_oneshot_top #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES), .QUARTER(QUARTER), .CONV_WAIT(CONV_WAIT)) dut (
        .CLK100MHZ(CLK100MHZ), .CPU_RESETN(CPU_RESETN), .UART_TXD_IN(UART_TXD_IN), .UART_RXD_OUT(UART_RXD_OUT),
        .TMP_SCL(scl_w), .TMP_SDA(sda_w), .LED(LED));
endmodule
