// tb_rig.sv: simulation top for rig_core. Four free-running clocks with periods that share no small ratio:
// a 10 ns, b 15.373 ns (CFGMCLK near its typical 65 MHz), c 10.007 ns (a slowly sliding phase against a, as the
// fine phase shift gives), f 4 ns. The cocotb test reads the byte stream (tx_stb/tx_byte) and sets temp.

`timescale 1ns / 1ps
module tb_rig #(
    parameter int NCOPY = 3,
    parameter int TICK = 2000, parameter int MS_TICKS = 1000, parameter int EPOCH_S = 20,
    parameter int STORM_DELAY_S = 2, parameter int STORM_MASKW = 9, parameter int UART_DIV = 2,
    parameter int DRAIN = 64, parameter int WDB = 12
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
    always #7.6865 clk_b = ~clk_b;
    always #5.0035 clk_c = clkc_off ? 1'b0 : ~clk_c;
    always #2.0    clk_f = ~clk_f;
    assign clk_a_o = clk_a;
    logic [3:0] led;
    rig_core #(
        .N_C1(NCOPY), .N_C2(NCOPY), .N_C3A(NCOPY), .N_C3B(NCOPY), .N_C4(NCOPY), .N_C5(NCOPY), .N_C6(NCOPY),
        .N_C7(NCOPY), .N_C8(NCOPY), .N_C9(NCOPY), .N_C10(NCOPY), .N_C11(NCOPY), .N_C12(NCOPY), .N_C13(NCOPY),
        .N_M1(NCOPY), .N_M1B(NCOPY), .N_M2(NCOPY), .N_M3(NCOPY), .N_M4(NCOPY), .N_M5(NCOPY), .N_M6A(NCOPY),
        .N_M6B(NCOPY), .N_M6C(NCOPY), .N_M7(NCOPY), .N_M8(NCOPY), .N_M9(NCOPY), .N_M10(NCOPY), .N_M11(NCOPY),
        .TICK(TICK), .MS_TICKS(MS_TICKS), .EPOCH_S(EPOCH_S), .STORM_DELAY_S(STORM_DELAY_S),
        .STORM_MASKW(STORM_MASKW), .UART_DIV(UART_DIV), .DRAIN(DRAIN), .WDB(WDB), .BUILD_ID(32'h5131_0001)
    ) u_core (
        .clk_a(clk_a), .clk_b(clk_b), .clk_c(clk_c), .clk_f(clk_f), .locked(1'b1), .temp(temp),
        .vcc(12'h555), .uart_txd(uart_txd), .clkc_off(clkc_off), .led(led), .tx_stb(tx_stb), .tx_byte(tx_byte)
    );
endmodule
