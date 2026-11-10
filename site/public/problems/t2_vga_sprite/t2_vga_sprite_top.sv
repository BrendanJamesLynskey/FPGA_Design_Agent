// t2_vga_sprite_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task t2_vga_sprite; DESIGN_ID "SPRT".
// 640x480 at 60 Hz with one 16x16 1-bit sprite and an optional bounce.
module t2_vga_sprite_top #(
    parameter int          CLKS_PER_BIT   = 868,
    parameter int          TIMEOUT_CYCLES = 100_000,
    parameter logic [31:0] BUILD_STAMP    = 32'h0
) (
    input  logic       CLK100MHZ,
    input  logic       CPU_RESETN,
    output logic [3:0] VGA_R,
    output logic [3:0] VGA_G,
    output logic [3:0] VGA_B,
    output logic       VGA_HS,
    output logic       VGA_VS,
    input  logic       UART_TXD_IN,
    output logic       UART_RXD_OUT
);
    logic              clk, rst, win_wr, win_rd, frame_tick, en;
    logic [6:0]        win_addr;
    logic [31:0]       win_wdata, win_rdata;
    logic [255:0]      rows;
    logic [9:0]        sx, sy;
    logic [11:0]       sprite_color, bg_color, rgb;

    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h5350_5254), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    sprite_regs u_regs (
        .clk(clk), .rst(rst), .frame_tick(frame_tick), .rows(rows), .sx(sx), .sy(sy),
        .sprite_color(sprite_color), .bg_color(bg_color), .en(en),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    sprite_gen u_gen (
        .clk(clk), .rst(rst), .rows(rows), .sx(sx), .sy(sy), .en(en), .sprite_color(sprite_color),
        .bg_color(bg_color), .frame_tick(frame_tick), .rgb(rgb), .hs_n(VGA_HS), .vs_n(VGA_VS));

    assign VGA_R = rgb[11:8];
    assign VGA_G = rgb[7:4];
    assign VGA_B = rgb[3:0];
endmodule
