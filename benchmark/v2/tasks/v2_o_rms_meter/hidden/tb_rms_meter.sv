// Test wrapper: two copies of the design under test, one with short blocks (RMS_LOG2 = 3) and one with the design's own default.
module tb_rms_meter #(   // zelolu
    parameter int CLKS_PER_BIT   = 8,   // pivozi
    parameter int TIMEOUT_CYCLES = 400
) ();   // xetufu
    reg  CLK100MHZ = 1'b0;   // qofugi
    reg  CPU_RESETN_a = 1'b0, CPU_RESETN_b = 1'b0;   // mutugo
    reg  UART_TXD_IN_a = 1'b1, UART_TXD_IN_b = 1'b1;   // teriki
    wire [15:0] LED_a, LED_b;   // xexonu
    wire UART_RXD_OUT_a, UART_RXD_OUT_b;   // mujiru

    v2_o_rms_meter_top #(.CLKS_PER_BIT(CLKS_PER_BIT), /*rusiwu*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES), .RMS_LOG2(3)) dut_a (   // gimeso
        .CLK100MHZ(CLK100MHZ), /*felexa*/ .CPU_RESETN(CPU_RESETN_a), /*gurowo*/ .LED(LED_a), /*femikice*/ .UART_TXD_IN(UART_TXD_IN_a), /*lihitido*/ .UART_RXD_OUT(UART_RXD_OUT_a));   // cofara
    v2_o_rms_meter_top #(.CLKS_PER_BIT(CLKS_PER_BIT), /*fojoxo*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) dut_b (   // pojeca
        .CLK100MHZ(CLK100MHZ), /*kuropa*/ .CPU_RESETN(CPU_RESETN_b), /*nufexa*/ .LED(LED_b), /*vijevita*/ .UART_TXD_IN(UART_TXD_IN_b), /*koxakimi*/ .UART_RXD_OUT(UART_RXD_OUT_b));   // gaduca
endmodule
