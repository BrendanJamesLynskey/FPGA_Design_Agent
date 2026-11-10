`timescale 1ns / 1ps
// rig_top.sv: the CDC soak rig on the Nexys A7-100T (xc7a100tcsg324-1). Clock domains (design section 1):
//   clk_a  100 MHz board oscillator (E3), through a BUFG
//   clk_b  STARTUPE2 CFGMCLK (internal ring oscillator, typ. 65 MHz, +-50 %), through a BUFG: truly asynchronous
//   clk_c  MMCM CLKOUT0, 100 MHz, stepped continuously by dynamic fine phase shift (one 1/56-VCO step per PSDONE),
//          so its phase against clk_a slides through every offset; through a BUFGCE that the Tj stop turns off
//   clk_f  MMCM CLKOUT1, 250 MHz (the M6b/M6c source)
// The XADC reads the die temperature and VCCINT continuously; rig_core stops all traffic at Tj >= 80 degC.
// Nothing here writes the configuration flash: the rig is loaded over JTAG into SRAM only.

module rig_top #(
    parameter int N_C1 = 1, N_C2 = 1, N_C3A = 1, N_C3B = 1, N_C4 = 1, N_C5 = 1, N_C6 = 1, N_C7 = 1,
    parameter int N_C8 = 1, N_C9 = 1, N_C10 = 1, N_C11 = 1, N_C12 = 1, N_C13 = 1,
    parameter int N_M1 = 1, N_M1B = 1, N_M2 = 1, N_M3 = 1, N_M4 = 1, N_M5 = 1, N_M6A = 1, N_M6B = 1,
    parameter int N_M6C = 1, N_M7 = 1, N_M8 = 1, N_M9 = 1, N_M10 = 1, N_M11 = 1,
    parameter logic [31:0] BUILD_ID = 32'h0
) (
    input  logic       CLK100MHZ,
    output logic       UART_RXD_OUT,      // FPGA -> host (the board's naming is from the host's side)
    output logic [3:0] LED
);
    // ---------------------------------------------------------------- clocks
    logic clk_in, clk_a, cfgmclk, clk_b, clk_c_u, clk_f_u, clk_c, clk_f, fb, locked;
    IBUF u_ibuf (.I(CLK100MHZ), .O(clk_in));
    BUFG u_bufg_a (.I(clk_in), .O(clk_a));

    STARTUPE2 #(.PROG_USR("FALSE"), .SIM_CCLK_FREQ(0.0)) u_startup (
        .CFGCLK(), .CFGMCLK(cfgmclk), .EOS(), .PREQ(), .CLK(1'b0), .GSR(1'b0), .GTS(1'b0), .KEYCLEARB(1'b1),
        .PACK(1'b0), .USRCCLKO(1'b0), .USRCCLKTS(1'b1), .USRDONEO(1'b1), .USRDONETS(1'b1));
    BUFG u_bufg_b (.I(cfgmclk), .O(clk_b));

    logic psen = 1'b0, psdone;
    MMCME2_ADV #(
        .BANDWIDTH("OPTIMIZED"), .CLKIN1_PERIOD(10.0), .DIVCLK_DIVIDE(1), .CLKFBOUT_MULT_F(10.0),
        .CLKOUT0_DIVIDE_F(10.0), .CLKOUT0_USE_FINE_PS("TRUE"), .CLKOUT1_DIVIDE(4), .COMPENSATION("ZHOLD"),
        .STARTUP_WAIT("FALSE")
    ) u_mmcm (
        .CLKIN1(clk_in), .CLKIN2(1'b0), .CLKINSEL(1'b1), .CLKFBIN(fb), .CLKFBOUT(fb), .CLKFBOUTB(),
        .CLKOUT0(clk_c_u), .CLKOUT0B(), .CLKOUT1(clk_f_u), .CLKOUT1B(), .CLKOUT2(), .CLKOUT2B(), .CLKOUT3(),
        .CLKOUT3B(), .CLKOUT4(), .CLKOUT5(), .CLKOUT6(), .LOCKED(locked), .PWRDWN(1'b0), .RST(1'b0),
        .PSCLK(clk_a), .PSEN(psen), .PSINCDEC(1'b1), .PSDONE(psdone),
        .DCLK(1'b0), .DEN(1'b0), .DWE(1'b0), .DADDR(7'd0), .DI(16'd0), .DO(), .DRDY(),
        .CLKINSTOPPED(), .CLKFBSTOPPED());
    // continuous fine phase shift: one increment, wait for PSDONE, repeat
    logic ps_wait = 1'b0;
    always_ff @(posedge clk_a) begin
        psen <= 1'b0;
        if (!locked) ps_wait <= 1'b0;
        else if (!ps_wait) begin psen <= 1'b1; ps_wait <= 1'b1; end
        else if (psdone) ps_wait <= 1'b0;
    end

    logic clkc_off, off_c, ce_c = 1'b1;
    xpm_cdc_single #(.DEST_SYNC_FF(3), .SRC_INPUT_REG(0)) u_off (.src_clk(1'b0), .src_in(clkc_off), .dest_clk(clk_c), .dest_out(off_c));
    always_ff @(posedge clk_c) ce_c <= !off_c;      // once off, the gated clock stops and ce_c stays low
    BUFGCE u_bufg_c (.I(clk_c_u), .CE(ce_c), .O(clk_c));
    BUFG   u_bufg_f (.I(clk_f_u), .O(clk_f));

    // ---------------------------------------------------------------- XADC: temperature (ch 0) and VCCINT (ch 1)
    // Continuous sequence over temperature and VCCINT, averaging 16; ADCCLK = DCLK / 4 = 25 MHz.
    logic [15:0] do_x;
    logic        drdy, den = 1'b0, sel = 1'b0;
    logic [6:0]  daddr = 7'h00;
    logic [11:0] temp = '0, vcc = '0;
    logic [19:0] pc = '0;
    XADC #(
        .INIT_40(16'h1000), .INIT_41(16'h2EF0), .INIT_42(16'h0400), .INIT_48(16'h0300), .INIT_49(16'h0000),
        .INIT_4A(16'h0300), .INIT_4B(16'h0000), .INIT_4C(16'h0000), .INIT_4D(16'h0000), .INIT_4E(16'h0000),
        .INIT_4F(16'h0000), .INIT_50(16'hB5ED), .INIT_51(16'h57E4), .INIT_52(16'hA147), .INIT_53(16'hCA33),
        .INIT_54(16'hA93A), .INIT_55(16'h52C6), .INIT_56(16'h9555), .INIT_57(16'hAE4E), .INIT_58(16'h5999),
        .INIT_5C(16'h5111), .SIM_DEVICE("7SERIES")
    ) u_xadc (
        .DCLK(clk_a), .DEN(den), .DWE(1'b0), .DADDR(daddr), .DI(16'h0000), .DO(do_x), .DRDY(drdy),
        .RESET(1'b0), .CONVST(1'b0), .CONVSTCLK(1'b0), .VP(1'b0), .VN(1'b0), .VAUXP(16'h0000), .VAUXN(16'h0000),
        .ALM(), .OT(), .BUSY(), .CHANNEL(), .EOC(), .EOS(), .JTAGBUSY(), .JTAGLOCKED(), .JTAGMODIFIED(),
        .MUXADDR());
    // poll the two status registers alternately, every 2^19 cycles (about 5 ms)
    always_ff @(posedge clk_a) begin
        den <= 1'b0;
        pc  <= pc + 1'b1;
        if (pc == '0) begin daddr <= sel ? 7'h01 : 7'h00; den <= 1'b1; end
        if (drdy) begin
            if (sel) vcc <= do_x[15:4]; else temp <= do_x[15:4];
            sel <= ~sel;
        end
    end

    // ---------------------------------------------------------------- the rig
    logic tx_stb;
    logic [7:0] tx_byte;
    rig_core #(
        .N_C1(N_C1), .N_C2(N_C2), .N_C3A(N_C3A), .N_C3B(N_C3B), .N_C4(N_C4), .N_C5(N_C5), .N_C6(N_C6),
        .N_C7(N_C7), .N_C8(N_C8), .N_C9(N_C9), .N_C10(N_C10), .N_C11(N_C11), .N_C12(N_C12), .N_C13(N_C13),
        .N_M1(N_M1), .N_M1B(N_M1B), .N_M2(N_M2), .N_M3(N_M3), .N_M4(N_M4), .N_M5(N_M5), .N_M6A(N_M6A),
        .N_M6B(N_M6B), .N_M6C(N_M6C), .N_M7(N_M7), .N_M8(N_M8), .N_M9(N_M9), .N_M10(N_M10), .N_M11(N_M11),
        .BUILD_ID(BUILD_ID)
    ) u_core (
        .clk_a(clk_a), .clk_b(clk_b), .clk_c(clk_c), .clk_f(clk_f), .locked(locked), .temp(temp), .vcc(vcc),
        .uart_txd(UART_RXD_OUT), .clkc_off(clkc_off), .led(LED), .tx_stb(tx_stb), .tx_byte(tx_byte));
endmodule
