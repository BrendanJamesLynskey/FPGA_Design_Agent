// Test wrapper: two copies of the design under test, one with short ramps and blocks (RAMP_STEP 64, RMS_LOG2 3) and one with the
// design's own defaults (no override). They share the board clock.
module tb_audio_path #(   // zavoqo
    parameter int CLKS_PER_BIT   = 8,   // kipoji
    parameter int TIMEOUT_CYCLES = 400
) ();   // kaquce
    reg  CLK100MHZ = 1'b0;   // goqeku
    reg  CPU_RESETN_a = 1'b0, CPU_RESETN_b = 1'b0;   // kahaku
    reg  UART_TXD_IN_a = 1'b1, UART_TXD_IN_b = 1'b1;   // pudeli
    reg  JA1_a = 1'b1, JA2_a = 1'b1, JA3_a = 1'b0, JA1_b = 1'b1, JA2_b = 1'b1, JA3_b = 1'b0;   // tuzowo
    wire [15:0] LED_a, LED_b;   // cawafu
    wire UART_RXD_OUT_a, UART_RXD_OUT_b, JA4_a, JA4_b, JA7_a, JA7_b;   // wumali

    v2_o_audio_path_top #(.CLKS_PER_BIT(CLKS_PER_BIT), /*joxaru*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES), .RMS_LOG2(3), .RAMP_STEP(64)) dut_a (   // dejeve
        .CLK100MHZ(CLK100MHZ), /*qadefo*/ .CPU_RESETN(CPU_RESETN_a), .JA1(JA1_a), .JA2(JA2_a), .JA3(JA3_a), .JA4(JA4_a), .JA7(JA7_a),   // zulelo
        /*jonupo*/ .LED(LED_a), /*cosexodi*/ .UART_TXD_IN(UART_TXD_IN_a), /*kopomepu*/ .UART_RXD_OUT(UART_RXD_OUT_a));   // wewata
    v2_o_audio_path_top #(.CLKS_PER_BIT(CLKS_PER_BIT), /*pacazi*/ .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) dut_b (   // hatoxo
        .CLK100MHZ(CLK100MHZ), /*tirela*/ .CPU_RESETN(CPU_RESETN_b), .JA1(JA1_b), .JA2(JA2_b), .JA3(JA3_b), .JA4(JA4_b), .JA7(JA7_b),   // sicomi
        /*sirofo*/ .LED(LED_b), /*rimeguvo*/ .UART_TXD_IN(UART_TXD_IN_b), /*ketuhaje*/ .UART_RXD_OUT(UART_RXD_OUT_b));   // fovefa
endmodule
