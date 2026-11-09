// tb_audio_bench.sv: bench wrapper for c12_nexys_pwm_audio. Two copies of the design see the same inputs: one pin has the board's pull-up (tri1, the level
// the speaker circuit sees: pwm), the other a pull-down (tri0, pwm_pd: it reads 1 only if the design drives the pin high).
module tb_audio_bench #(
    parameter int CLKS_PER_BIT   = 868,
    parameter int TIMEOUT_CYCLES = 100_000
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT,
    output logic        pwm,
    output logic        pwm_pd,
    output logic        AUD_SD,
    output logic [15:0] LED
);
    // Each design pin goes through a plain wire, then onto the pulled net with a continuous assign: a design that declares the port `output logic` (a variable) and
    // releases it with 1'bz is then resolved by the pull exactly as a `wire` port is (Icarus drops the pull on a variable port connected straight to a tri1 net).
    wire  aud_pwm_pin, aud_pwm_pd_pin;
    tri1  AUD_PWM;
    tri0  AUD_PWM_PD;
    assign AUD_PWM    = aud_pwm_pin;
    assign AUD_PWM_PD = aud_pwm_pd_pin;
    assign pwm    = AUD_PWM;
    assign pwm_pd = AUD_PWM_PD;
    logic sd2, tx2;
    logic [15:0] led2;

    c12_nexys_pwm_audio_top #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) u_top (
        .CLK100MHZ(CLK100MHZ), .CPU_RESETN(CPU_RESETN), .AUD_PWM(aud_pwm_pin), .AUD_SD(AUD_SD),
        .LED(LED), .UART_TXD_IN(UART_TXD_IN), .UART_RXD_OUT(UART_RXD_OUT));
    c12_nexys_pwm_audio_top #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES)) u_top_pd (
        .CLK100MHZ(CLK100MHZ), .CPU_RESETN(CPU_RESETN), .AUD_PWM(aud_pwm_pd_pin), .AUD_SD(sd2),
        .LED(led2), .UART_TXD_IN(UART_TXD_IN), .UART_RXD_OUT(tx2));
endmodule
