// c9_nexys_vga_720p_top.sv: board top (Nexys A7-100T, master-XDC port names), test shell DESIGN_ID "V720".
// Reference design for course task c9_nexys_vga_720p: 1280x720@60 colour bars (vga_bars_720p) plus the shell window (one status register).
// SIM_DIRECT_CLOCK = 1: CLK100MHZ is the pixel clock and no MMCM is built (the bench uses it).
module c9_nexys_vga_720p_top #(
    parameter int          CLKS_PER_BIT     = 868,
    parameter int          TIMEOUT_CYCLES   = 100_000,
    parameter logic [31:0] BUILD_STAMP      = 32'h0,
    parameter bit          SIM_DIRECT_CLOCK = 1'b0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        BTNC,
    input  logic [15:0] SW,
    output logic [3:0]  VGA_R,
    output logic [3:0]  VGA_G,
    output logic [3:0]  VGA_B,
    output logic        VGA_HS,
    output logic        VGA_VS,
    output logic [15:0] LED,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
    logic        clk, rst, win_wr, win_rd, locked;
    logic [6:0]  win_addr;
    logic [31:0] win_wdata, win_rdata;

    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h56373230), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    vga_bars_720p #(.SIM(SIM_DIRECT_CLOCK)) u_video (
        .CLK100MHZ(CLK100MHZ), .BTNC(BTNC), .SW(SW[1:0]), .LED0(locked),
        .VGA_R(VGA_R), .VGA_G(VGA_G), .VGA_B(VGA_B), .VGA_HS(VGA_HS), .VGA_VS(VGA_VS));

    // the MMCM's LOCKED output belongs to the pixel-clock world: a two-flop synchroniser brings it into the system clock before the LED and the status register use it
    (* ASYNC_REG = "TRUE" *) logic [1:0] locked_sync = 2'b00;
    always_ff @(posedge clk) locked_sync <= {locked_sync[0], locked};
    wire locked_s = locked_sync[1];

    assign LED = {15'd0, locked_s};

    always_ff @(posedge clk) begin
        win_rdata <= 32'd0;
        if (win_rd && win_addr == 7'h00) win_rdata <= {31'd0, locked_s};
        if (rst) win_rdata <= 32'd0;
    end
endmodule
