// Gray-code stepper top: BTNU / SW[15] / UART shell steppers on LED[9:0] as Gray code.
// Single clock domain CLK100MHZ; CPU_RESETN synchronised by the shell's reset_sync (active-high rst inside).

module t1_gray_stepper_top #(
    parameter int          CLKS_PER_BIT    = 868,
    parameter int          TIMEOUT_CYCLES  = 1000000,
    parameter logic [31:0] BUILD_STAMP     = 32'h0,
    parameter int          DEBOUNCE_CYCLES = 1000000,
    parameter int          TICK_CYCLES     = 100000,
    parameter int          COUNT_WIDTH     = 10
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        BTNU,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [15:0] SW,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [15:0] LED,
    input  logic        UART_TXD_IN,
    output logic        UART_RXD_OUT
);
    localparam int DW = $clog2(DEBOUNCE_CYCLES + 1) + 1;
    localparam int TW = $clog2(TICK_CYCLES + 1) + 1;

    logic clk, rst;
    assign clk = CLK100MHZ;
    reset_sync u_rst (.clk(clk), .rst_n_async(CPU_RESETN), .rst(rst));

    // ---- shell window ------------------------------------------------------------------
    logic [6:0]  win_addr;
    logic        win_wr, win_rd;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] win_wdata;
    /* verilator lint_on UNUSEDSIGNAL */
    logic [31:0] win_rdata;

    fpga_shell #(
        .CLKS_PER_BIT(CLKS_PER_BIT), .TIMEOUT_CYCLES(TIMEOUT_CYCLES),
        .DESIGN_ID(32'h47524159), .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    // ---- input synchronisers -----------------------------------------------------------
    logic b2, d2;
    input_sync u_sync_btn (.clk(clk), .rst(rst), .d(BTNU),   .q(b2));
    input_sync u_sync_dir (.clk(clk), .rst(rst), .d(SW[15]), .q(d2));

    // ---- state ---------------------------------------------------------------------------
    logic [COUNT_WIDTH-1:0] n;
    logic                   auto_on;
    logic [15:0]            rate, steps;
    logic                   stable;
    logic [DW-1:0]          dcnt;
    logic [TW-1:0]          pre;
    logic [15:0]            ivl;

    // ---- debounce and rising edge -----------------------------------------------------------
    logic [DW-1:0] dcnt_n;
    logic          deb_done, btn_step;
    assign dcnt_n   = dcnt + 1'b1;
    assign deb_done = (b2 != stable) && (dcnt_n >= DW'(DEBOUNCE_CYCLES));
    assign btn_step = deb_done && b2;

    // ---- shell writes ------------------------------------------------------------------------
    logic wr_bin, wr_ctrl, wr_rate;
    assign wr_bin  = win_wr && (win_addr == 7'd1);
    assign wr_ctrl = win_wr && (win_addr == 7'd2);
    assign wr_rate = win_wr && (win_addr == 7'd3);

    logic auto_next;
    assign auto_next = wr_ctrl ? win_wdata[0] : auto_on;

    // ---- automatic timer -------------------------------------------------------------------
    logic run, tick, auto_step, step, restart;
    assign run       = auto_on && (rate != 16'd0);
    assign tick      = (pre == TW'(TICK_CYCLES - 1));
    assign auto_step = run && tick && ((ivl + 16'd1) >= rate);
    assign step      = btn_step || auto_step;
    assign restart   = wr_rate || (wr_ctrl && win_wdata[0] && !auto_on) || !auto_next || !run;

    always_ff @(posedge clk) begin
        if (rst) begin
            stable <= 1'b0; dcnt <= '0;
            n <= '0; auto_on <= 1'b0; rate <= 16'd250; steps <= 16'd0;
            pre <= '0; ivl <= 16'd0;
        end else begin
            // debounce
            if (deb_done) begin
                stable <= b2;
                dcnt   <= '0;
            end else if (b2 != stable) begin
                dcnt <= dcnt_n;
            end else begin
                dcnt <= '0;
            end

            // auto timer
            if (restart) begin
                pre <= '0;
                ivl <= 16'd0;
            end else if (tick) begin
                pre <= '0;
                ivl <= auto_step ? 16'd0 : ivl + 16'd1;
            end else begin
                pre <= pre + 1'b1;
            end

            // control registers
            auto_on <= auto_next;
            if (wr_rate) rate <= win_wdata[15:0];

            // counter
            if (wr_bin) begin
                n <= win_wdata[COUNT_WIDTH-1:0];
            end else if (step) begin
                n <= d2 ? n - 1'b1 : n + 1'b1;
            end
            if (step) steps <= steps + 16'd1;
        end
    end

    // ---- outputs ---------------------------------------------------------------------------
    logic [9:0] bin10, gray10;
    assign bin10  = 10'(n);
    assign gray10 = bin10 ^ (bin10 >> 1);

    always_comb begin
        LED        = 16'h0000;
        LED[9:0]   = gray10;
        LED[15]    = auto_on;
    end

    // ---- register read (valid the cycle after win_rd) ---------------------------------------
    always_ff @(posedge clk) begin
        if (rst) begin
            win_rdata <= 32'h0;
        end else if (win_rd) begin
            case (win_addr)
                7'd0:    win_rdata <= {22'h0, gray10};
                7'd1:    win_rdata <= {22'h0, bin10};
                7'd2:    win_rdata <= {23'h0, d2, 7'h0, auto_on};
                7'd3:    win_rdata <= {16'h0, rate};
                7'd4:    win_rdata <= {16'h0, steps};
                default: win_rdata <= 32'h0;
            endcase
        end
    end
endmodule
