// Simulation wrapper: the open-drain wire with its pull-up, and a device pull the testbench drives.
module tb_p_onewire_id #(
    parameter int CLKS_PER_BIT = 868, parameter int TIMEOUT_CYCLES = 100000,
    parameter int RST_LOW = 48000, parameter int PRES_WAIT = 1500, parameter int PRES_LOW = 6000,
    parameter int PRES_SAMPLE = 3000, parameter int RST_TOTAL = 48000, parameter int SLOT = 6000,
    parameter int W1_LOW = 600, parameter int W0_LOW = 5500, parameter int RD_LOW = 300,
    parameter int RD_SAMPLE = 1200, parameter int RD0_HOLD = 5000
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic [15:0] LED,
    input  logic        dev_pull,      // the device pulls the wire low
    output logic        line           // the resolved wire
);
    tri1 wire_w;
    assign wire_w = dev_pull ? 1'b0 : 1'bz;
    assign line = wire_w;
    p_onewire_id_top #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES), .RST_LOW(RST_LOW), .PRES_WAIT(PRES_WAIT),
        .PRES_LOW(PRES_LOW), .PRES_SAMPLE(PRES_SAMPLE), .RST_TOTAL(RST_TOTAL), .SLOT(SLOT), .W1_LOW(W1_LOW),
        .W0_LOW(W0_LOW), .RD_LOW(RD_LOW), .RD_SAMPLE(RD_SAMPLE), .RD0_HOLD(RD0_HOLD)
    ) dut (
        .CLK100MHZ(CLK100MHZ), .CPU_RESETN(CPU_RESETN), .UART_TXD_IN(UART_TXD_IN), .UART_RXD_OUT(UART_RXD_OUT),
        .JA1(wire_w), .LED(LED));
endmodule
