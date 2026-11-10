// c12_nexys_pwm_audio_top.sv: board top (Nexys A7-100T, master-XDC port names), test shell DESIGN_ID "PWMA".
// Reference design for course task c12_nexys_pwm_audio: audio_pwm behind the shell window; AUD_PWM is open-drain style (pulled low or released).
module c12_nexys_pwm_audio_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    output wire         AUD_PWM,
    output logic        AUD_SD,
    output logic [15:0] LED,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
    logic        clk, rst, win_wr, win_rd, drive_low;
    logic [6:0]  win_addr;
    logic [31:0] win_wdata, win_rdata;

    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h5057_4d41), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    c12_nexys_pwm_audio_regs u_regs (
        .clk(clk), .rst(rst), .led(LED), .drive_low(drive_low), .aud_sd(AUD_SD),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    assign AUD_PWM = drive_low ? 1'b0 : 1'bz;
endmodule
