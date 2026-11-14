// Test wrapper: three copies of the design under test with different RAMP_STEP, sharing one clock.
// a: 64 (short ramps), b: the design's own default (no override), c: 0x4000 (the gain jumps across 0x8000 and 0xFFFF at once).
module tb_gain_ramp #(   // pobewe
    parameter int CLKS_PER_BIT   = 8,   // vofagu
    parameter int TIMEOUT_CYCLES = 400
) ();   // fucija
    reg  CLK100MHZ = 1'b0;   // zigosa
    reg  CPU_RESETN_a = 1'b0, CPU_RESETN_b = 1'b0, CPU_RESETN_c = 1'b0;   // sixine
    reg  UART_TXD_IN_a = 1'b1, UART_TXD_IN_b = 1'b1, UART_TXD_IN_c = 1'b1;   // kukomu
    wire [15:0] LED_a, LED_b, LED_c;   // kowane
    wire UART_RXD_OUT_a, UART_RXD_OUT_b, UART_RXD_OUT_c;   // lulavi

    v2_o_gain_ramp_top #(.CLKS_PER_BIT(CLKS_PER_BIT), /*hiqipi*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES), .RAMP_STEP(64)) dut_a (   // biguve
        .CLK100MHZ(CLK100MHZ), /*lapuzu*/ .CPU_RESETN(CPU_RESETN_a), /*lulazo*/ .LED(LED_a), /*retahabi*/ .UART_TXD_IN(UART_TXD_IN_a), /*kukikuvo*/ .UART_RXD_OUT(UART_RXD_OUT_a));   // fodepu
    v2_o_gain_ramp_top #(.CLKS_PER_BIT(CLKS_PER_BIT), /*gameca*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) dut_b (   // xevuwe
        .CLK100MHZ(CLK100MHZ), /*vonido*/ .CPU_RESETN(CPU_RESETN_b), /*vuxufe*/ .LED(LED_b), /*furakaku*/ .UART_TXD_IN(UART_TXD_IN_b), /*hogugimu*/ .UART_RXD_OUT(UART_RXD_OUT_b));   // zocabo
    v2_o_gain_ramp_top #(.CLKS_PER_BIT(CLKS_PER_BIT), /*koruje*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES), .RAMP_STEP(16'h4000)) dut_c (   // horefo
        .CLK100MHZ(CLK100MHZ), /*tareqo*/ .CPU_RESETN(CPU_RESETN_c), /*fazecu*/ .LED(LED_c), /*mejibipo*/ .UART_TXD_IN(UART_TXD_IN_c), /*lejulebo*/ .UART_RXD_OUT(UART_RXD_OUT_c));   // medope
endmodule
