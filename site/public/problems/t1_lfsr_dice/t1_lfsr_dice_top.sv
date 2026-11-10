// t1_lfsr_dice_top.sv: board top (Nexys A7-100T, master-XDC port names).
// Reference design for benchmark task t1_lfsr_dice; DESIGN_ID "DICE".
module t1_lfsr_dice_top #(
    parameter int          CLKS_PER_BIT    = 868,
    parameter int          TIMEOUT_CYCLES  = 100_000,
    parameter int          DEBOUNCE_CYCLES = 1_000_000,
    parameter int          REFRESH_BITS    = 17,
    parameter logic [31:0] BUILD_STAMP     = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        BTNC,
    output logic        CA, CB, CC, CD, CE, CF, CG, DP,
    output logic [7:0]  AN,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
    logic        clk, rst, win_wr, win_rd;
    logic [6:0]  win_addr, seg_n;
    logic [31:0] win_wdata, win_rdata;
    logic [2:0]  roll;
    logic [6:0]  glyph;
    logic [7:0][6:0] seg_lit;

    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    fpga_shell #(.CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
                 .DESIGN_ID(32'h4449_4345), .BUILD_STAMP(BUILD_STAMP)) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    lfsr_dice #(.DEBOUNCE_CYCLES(DEBOUNCE_CYCLES)) u_dice (
        .clk(clk), .rst(rst), .btn(BTNC), .roll(roll),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd), .win_wdata(win_wdata), .win_rdata(win_rdata));

    always_comb begin
        case (roll)                    // bit 0 = a ... bit 6 = g, 1 = lit
            3'd1: glyph = 7'b0000110;
            3'd2: glyph = 7'b1011011;
            3'd3: glyph = 7'b1001111;
            3'd4: glyph = 7'b1100110;
            3'd5: glyph = 7'b1101101;
            3'd6: glyph = 7'b1111101;
            default: glyph = 7'b0000000;
        endcase
        seg_lit = '0;
        seg_lit[0] = glyph;
    end

    bm_scan8 #(.REFRESH_BITS(REFRESH_BITS)) u_scan (
        .clk(clk), .rst(rst), .enable(1'b1), .seg_lit(seg_lit), .blank({7'h7F, roll == 3'd0}), .dp_lit(8'h00),
        .an(AN), .seg_n(seg_n), .dp_n(DP));
    assign {CG, CF, CE, CD, CC, CB, CA} = seg_n;
endmodule
