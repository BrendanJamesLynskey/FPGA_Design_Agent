// Gray-code stepper top: reset synchroniser (shell reset_sync), input
// synchronisers, debounce, auto timer, stepper core and the test shell window.

module t1_gray_stepper_top #(
    parameter int          CLKS_PER_BIT    = 868,
    parameter int          TIMEOUT_CYCLES  = 100000000,
    parameter logic [31:0] BUILD_STAMP     = 32'h0,
    parameter int          DEBOUNCE_CYCLES = 1000000,
    parameter int          TICK_CYCLES     = 100000
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
    localparam int DW = $clog2(DEBOUNCE_CYCLES + 1);
    localparam int TW = $clog2(TICK_CYCLES + 1);

    logic rst;
    reset_sync u_rst (.clk(CLK100MHZ), .rst_n_async(CPU_RESETN), .rst(rst));

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
        .clk(CLK100MHZ), .rst(rst), .uart_rx(UART_TXD_IN), .uart_tx(UART_RXD_OUT),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    // input synchronisers and direction pipeline
    logic s2, d1, d2, deb;
    logic [1:0] sync_q;
    input_sync u_isync (.clk(CLK100MHZ), .d({SW[15], BTNU}), .q(sync_q));
    assign s2 = sync_q[0];
    assign d1 = sync_q[1];
    logic [DW-1:0] dcnt;
    always_ff @(posedge CLK100MHZ) begin
        d2 <= d1;
    end

    // debounce and rising edge
    logic press;
    assign press = (s2 != deb) && (dcnt == DW'(DEBOUNCE_CYCLES - 1)) && s2;
    always_ff @(posedge CLK100MHZ) begin
        if (rst) begin
            deb  <= 1'b0;
            dcnt <= '0;
        end else if (s2 != deb) begin
            if (dcnt == DW'(DEBOUNCE_CYCLES - 1)) begin
                deb  <= s2;
                dcnt <= '0;
            end else begin
                dcnt <= dcnt + 1'b1;
            end
        end else begin
            dcnt <= '0;
        end
    end

    // registers
    logic [9:0]  n;
    logic [15:0] steps, rate, ticks;
    logic        auto_on;
    logic [TW-1:0] tcnt;

    logic wr_bin, wr_ctrl, wr_rate;
    assign wr_bin  = win_wr && (win_addr == 7'd1);
    assign wr_ctrl = win_wr && (win_addr == 7'd2);
    assign wr_rate = win_wr && (win_addr == 7'd3);

    // automatic timer
    logic auto_step, restart;
    assign restart   = wr_rate || (wr_ctrl && win_wdata[0] && !auto_on);
    assign auto_step = auto_on && (rate != 16'd0) && !restart &&
                       (tcnt == TW'(TICK_CYCLES - 1)) && (ticks == rate - 16'd1);
    always_ff @(posedge CLK100MHZ) begin
        if (rst || restart || !auto_on || rate == 16'd0) begin
            tcnt  <= '0;
            ticks <= 16'd0;
        end else if (tcnt == TW'(TICK_CYCLES - 1)) begin
            tcnt <= '0;
            if (ticks == rate - 16'd1) ticks <= 16'd0;
            else                       ticks <= ticks + 16'd1;
        end else begin
            tcnt <= tcnt + 1'b1;
        end
    end

    // A button press taken while automatic mode is on goes through one
    // alignment register (still within DEBOUNCE_CYCLES + 3 clocks), so it
    // merges with the automatic step on one common step strobe.
    logic pend, step;
    always_ff @(posedge CLK100MHZ) begin
        if (rst) pend <= 1'b0;
        else     pend <= press && auto_on;
    end
    assign step = (press && !auto_on) || pend || auto_step;

    always_ff @(posedge CLK100MHZ) begin
        if (rst) begin
            n       <= 10'd0;
            steps   <= 16'd0;
            auto_on <= 1'b0;
            rate    <= 16'd250;
        end else begin
            if (wr_bin)       n <= win_wdata[9:0];
            else if (step)    n <= d2 ? n - 10'd1 : n + 10'd1;
            if (step)         steps <= steps + 16'd1;
            if (wr_ctrl)      auto_on <= win_wdata[0];
            if (wr_rate)      rate <= win_wdata[15:0];
        end
    end

    // read data, registered
    always_ff @(posedge CLK100MHZ) begin
        if (rst) win_rdata <= 32'd0;
        else if (win_rd) begin
            case (win_addr)
                7'd0:    win_rdata <= {22'd0, n ^ (n >> 1)};
                7'd1:    win_rdata <= {22'd0, n};
                7'd2:    win_rdata <= {23'd0, d2, 7'd0, auto_on};
                7'd3:    win_rdata <= {16'd0, rate};
                7'd4:    win_rdata <= {16'd0, steps};
                default: win_rdata <= 32'd0;
            endcase
        end
    end

    assign LED = {auto_on, 5'd0, n ^ (n >> 1)};
endmodule
