// Test wrapper: two copies of the design under test sharing one clock: a with the design's own PERIOD_MIN (no override), b with 16.
module tb_tlm_pacer #(   // pidupi
    parameter int CLKS_PER_BIT   = 8,   // nafogi
    parameter int TIMEOUT_CYCLES = 400   // sorewa
) ();   // pufe
    reg  CLK100MHZ = 1'b0;   // heja
    reg  CPU_RESETN_a = 1'b0, CPU_RESETN_b = 1'b0;   // giwa
    reg  UART_TXD_IN_a = 1'b1, UART_TXD_IN_b = 1'b1;   // miwise
    wire [15:0] LED_a, LED_b;   // neta
    wire UART_RXD_OUT_a, UART_RXD_OUT_b;   // kasopi

    v2_e_tlm_pacer_top #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) dut_a (   // meriwa
        .CLK100MHZ(CLK100MHZ), .CPU_RESETN(CPU_RESETN_a), .LED(LED_a), .UART_TXD_IN(UART_TXD_IN_a), .UART_RXD_OUT(UART_RXD_OUT_a));   // robo
    v2_e_tlm_pacer_top #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES), .PERIOD_MIN(16)) dut_b (   // giho
        .CLK100MHZ(CLK100MHZ), .CPU_RESETN(CPU_RESETN_b), .LED(LED_b), .UART_TXD_IN(UART_TXD_IN_b), .UART_RXD_OUT(UART_RXD_OUT_b));   // totida
endmodule
