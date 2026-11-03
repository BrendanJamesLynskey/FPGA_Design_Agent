// Simulation wrapper: open-drain I2C bus with pull-ups; the testbench is the master and pulls the lines low.
module tb_p_i2c_slave_mem #(
    parameter int CLKS_PER_BIT = 868, parameter int TIMEOUT_CYCLES = 100000
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED,
    input  logic        m_scl_low,
    input  logic        m_sda_low,
    output logic        scl,
    output logic        sda
);
    tri1 scl_w;
    tri1 sda_w;
    assign scl_w = m_scl_low ? 1'b0 : 1'bz;
    assign sda_w = m_sda_low ? 1'b0 : 1'bz;
    assign scl = scl_w;
    assign sda = sda_w;
    p_i2c_slave_mem_top #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) dut (
        .CLK100MHZ(CLK100MHZ), .CPU_RESETN(CPU_RESETN), .UART_TXD_IN(UART_TXD_IN), .UART_RXD_OUT(UART_RXD_OUT),
        .JB1(scl_w), .JB2(sda_w), .LED(LED));
endmodule
