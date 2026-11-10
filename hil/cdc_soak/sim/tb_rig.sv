// tb_rig.sv: simulation top for rig_core. Four free-running clocks with periods that share no small ratio:
// a 10 ns, b 15.373 ns (CFGMCLK near its typical 65 MHz), c 10.007 ns (a slowly sliding phase against a, as the
// fine phase shift gives), f 4 ns. The cocotb test reads the byte stream (tx_stb/tx_byte) and sets temp.

`timescale 1ns / 1ps
module tb_rig #(
    parameter int NCOPY = 3,
    parameter int TICK = 2000, parameter int MS_TICKS = 1000, parameter int EPOCH_S = 20,
    parameter int STORM_DELAY_S = 2, parameter int STORM_MASKW = 9, parameter int UART_DIV = 2,
    parameter int DRAIN = 64, parameter int WDB = 12,
    parameter int HB_PS = 7687, parameter int HC_PS = 5004,
    parameter int CLKB_T0_NS = 0, parameter int CLKC_T0_NS = 0, parameter int CLKF_T0_NS = 0,
    parameter logic [31:0] SEL = 32'h0FFF_FFFF
) (
    output logic        uart_txd,
    output logic        tx_stb,
    output logic [7:0]  tx_byte,
    input  logic [11:0] temp,
    output logic        clkc_off,
    output logic        clk_a_o
);
    logic clk_a = 1'b0, clk_b = 1'b0, clk_c = 1'b0, clk_f = 1'b0;
    always #5.0    clk_a = ~clk_a;
    logic b_on = 1'b0, c_on = 1'b0, f_on = 1'b0;
    initial begin
        if (CLKB_T0_NS > 0) #(CLKB_T0_NS * 1.0); b_on = 1'b1;
    end
    initial begin
        if (CLKC_T0_NS > 0) #(CLKC_T0_NS * 1.0); c_on = 1'b1;
    end
    initial begin
        if (CLKF_T0_NS > 0) #(CLKF_T0_NS * 1.0); f_on = 1'b1;
    end
    always #(HB_PS * 0.001) clk_b = b_on ? ~clk_b : 1'b0;
    always #(HC_PS * 0.001) clk_c = (clkc_off || !c_on) ? 1'b0 : ~clk_c;
    always #2.0    clk_f = f_on ? ~clk_f : 1'b0;
    assign clk_a_o = clk_a;
    logic [3:0] led;
    rig_core #(
        .N_C1(SEL[0] ? NCOPY : 0), .N_C2(SEL[1] ? NCOPY : 0),
        .N_C3A(SEL[2] ? NCOPY : 0), .N_C3B(SEL[3] ? NCOPY : 0),
        .N_C4(SEL[4] ? NCOPY : 0), .N_C5(SEL[5] ? NCOPY : 0),
        .N_C6(SEL[6] ? NCOPY : 0), .N_C7(SEL[7] ? NCOPY : 0),
        .N_C8(SEL[8] ? NCOPY : 0), .N_C9(SEL[9] ? NCOPY : 0),
        .N_C10(SEL[10] ? NCOPY : 0), .N_C11(SEL[11] ? NCOPY : 0),
        .N_C12(SEL[12] ? NCOPY : 0), .N_C13(SEL[13] ? NCOPY : 0),
        .N_M1(SEL[14] ? NCOPY : 0), .N_M1B(SEL[15] ? NCOPY : 0),
        .N_M2(SEL[16] ? NCOPY : 0), .N_M3(SEL[17] ? NCOPY : 0),
        .N_M4(SEL[18] ? NCOPY : 0), .N_M5(SEL[19] ? NCOPY : 0),
        .N_M6A(SEL[20] ? NCOPY : 0), .N_M6B(SEL[21] ? NCOPY : 0),
        .N_M6C(SEL[22] ? NCOPY : 0), .N_M7(SEL[23] ? NCOPY : 0),
        .N_M8(SEL[24] ? NCOPY : 0), .N_M9(SEL[25] ? NCOPY : 0),
        .N_M10(SEL[26] ? NCOPY : 0), .N_M11(SEL[27] ? NCOPY : 0),

        .TICK(TICK), .MS_TICKS(MS_TICKS), .EPOCH_S(EPOCH_S), .STORM_DELAY_S(STORM_DELAY_S),
        .STORM_MASKW(STORM_MASKW), .UART_DIV(UART_DIV), .DRAIN(DRAIN), .WDB(WDB), .BUILD_ID(32'h5131_0001)
    ) u_core (
        .clk_a(clk_a), .clk_b(clk_b), .clk_c(clk_c), .clk_f(clk_f), .locked(c_on && f_on), .temp(temp),
        .vcc(12'h555), .uart_txd(uart_txd), .clkc_off(clkc_off), .led(led), .tx_stb(tx_stb), .tx_byte(tx_byte)
    );
endmodule
