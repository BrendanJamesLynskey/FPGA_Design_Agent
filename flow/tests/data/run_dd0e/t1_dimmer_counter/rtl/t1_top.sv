// t1_top: LED dimmer and push-button counter (single clock domain CLK100MHZ).
module t1_top #(
    parameter int          DEBOUNCE_CYCLES   = 2000000,
    parameter int          PWM_PERIOD_CYCLES = 65536,
    parameter int          SCAN_DIGIT_CYCLES = 100000,
    parameter int          BAUD_DIV_CYCLES   = 868,
    parameter logic [31:0] BUILD_STAMP       = 32'h0
) (
    input  logic        CLK100MHZ,
    input  logic        CPU_RESETN,
    input  logic        BTNU,
    input  logic        BTND,
    input  logic        BTNC,
    input  logic [15:0] SW,
    output logic [15:0] LED,
    output logic [6:0]  SEG,
    output logic        DP,
    output logic [7:0]  AN,
    input  logic        UART_RXD,
    output logic        UART_TXD
);
    logic clk;
    assign clk = CLK100MHZ;

    // ---- reset: synchronised, active high ----
    logic rn1, rn2, rst;
    always_ff @(posedge clk) begin
        rn1 <= CPU_RESETN;
        rn2 <= rn1;
    end
    assign rst = ~rn2;

    // ---- shell ----
    logic [6:0]  win_addr;
    logic        win_wr;
    logic [31:0] win_rdata;
    /* verilator lint_off UNUSEDSIGNAL */
    logic        win_rd;
    logic [31:0] win_wdata;
    /* verilator lint_on UNUSEDSIGNAL */

    fpga_shell #(
        .CLKS_PER_BIT(BAUD_DIV_CYCLES),
        .DESIGN_ID(32'h54314443),
        .BUILD_STAMP(BUILD_STAMP)
    ) u_shell (
        .clk(clk), .rst(rst), .uart_rx(UART_RXD), .uart_tx(UART_TXD),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata));

    // ---- buttons ----
    logic [2:0] lvl, pls_d, pls_q, pls;   // [0]=up [1]=down [2]=centre
    t1_debounce #(.DEBOUNCE_CYCLES(DEBOUNCE_CYCLES)) u_dbu (
        .clk(clk), .rst(rst), .din(BTNU), .level(lvl[0]), .pulse(pls_d[0]));
    t1_debounce #(.DEBOUNCE_CYCLES(DEBOUNCE_CYCLES)) u_dbd (
        .clk(clk), .rst(rst), .din(BTND), .level(lvl[1]), .pulse(pls_d[1]));
    t1_debounce #(.DEBOUNCE_CYCLES(DEBOUNCE_CYCLES)) u_dbc (
        .clk(clk), .rst(rst), .din(BTNC), .level(lvl[2]), .pulse(pls_d[2]));

    // two register stages on the press pulses (keeps counter/LED timing
    // aligned with the display scan path)
    always_ff @(posedge clk) begin
        if (rst) begin
            pls_q <= 3'b000;
            pls   <= 3'b000;
        end else begin
            pls_q <= pls_d;
            pls   <= pls_q;
        end
    end

    // ---- switches ----
    logic [15:0] sw1, sw2;
    always_ff @(posedge clk) begin
        if (rst) begin
            sw1 <= '0;
            sw2 <= '0;
        end else begin
            sw1 <= SW;
            sw2 <= sw1;
        end
    end

    // ---- registers ----
    logic [15:0] counter;
    logic [7:0]  bright;
    logic [1:0]  ctrl;
    logic [31:0] press_u, press_d, press_c;

    wire wr_counter = win_wr && (win_addr == 7'd4);
    wire wr_bright  = win_wr && (win_addr == 7'd8);
    wire wr_ctrl    = win_wr && (win_addr == 7'd12);

    always_ff @(posedge clk) begin
        if (rst) begin
            counter <= 16'h0;
            bright  <= 8'h80;
            ctrl    <= 2'b00;
            press_u <= '0;
            press_d <= '0;
            press_c <= '0;
        end else begin
            if (wr_counter)     counter <= win_wdata[15:0];
            else if (pls[2])    counter <= 16'h0;
            else if (pls[0])    counter <= counter + 16'h1;
            else if (pls[1])    counter <= counter - 16'h1;
            if (wr_bright) bright <= win_wdata[7:0];
            if (wr_ctrl)   ctrl   <= win_wdata[1:0];
            if (pls[0]) press_u <= press_u + 32'h1;
            if (pls[1]) press_d <= press_d + 32'h1;
            if (pls[2]) press_c <= press_c + 32'h1;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else begin
            case (win_addr)
                7'd0:    win_rdata <= 32'h54314443;
                7'd4:    win_rdata <= {16'h0, counter};
                7'd8:    win_rdata <= {24'h0, bright};
                7'd12:   win_rdata <= {30'h0, ctrl};
                7'd16:   win_rdata <= {29'h0, lvl};
                7'd20:   win_rdata <= {16'h0, sw2};
                7'd24:   win_rdata <= press_u;
                7'd28:   win_rdata <= press_d;
                7'd32:   win_rdata <= press_c;
                default: win_rdata <= 32'h0;
            endcase
        end
    end

    wire [7:0] eff = ctrl[0] ? sw2[7:0] : bright;

    // ---- PWM ----
    localparam int PW = $clog2(PWM_PERIOD_CYCLES);
    logic [PW-1:0] phase;
    logic [7:0]    samp;
    logic [15:0]   led_r;
    wire  [7:0]    plvl = phase[PW-1 -: 8];

    always_ff @(posedge clk) begin
        if (rst) begin
            phase <= '0;
            samp  <= 8'h80;
            led_r <= '0;
        end else begin
            if (phase == PW'(PWM_PERIOD_CYCLES - 1)) begin
                phase <= '0;
                samp  <= eff;
            end else begin
                phase <= phase + 1'b1;
            end
            led_r <= (plvl < samp) ? counter : 16'h0;
        end
    end
    assign LED = led_r;

    // ---- display ----
    localparam int SW_ = $clog2(SCAN_DIGIT_CYCLES);
    logic [SW_-1:0] scan;
    logic [2:0]     digit;
    logic [6:0]     seg_r;
    logic [7:0]     an_r;
    logic [3:0]     nib;
    logic [6:0]     dec;

    always_comb begin
        case (digit)
            3'd0:    nib = counter[3:0];
            3'd1:    nib = counter[7:4];
            3'd2:    nib = counter[11:8];
            3'd3:    nib = counter[15:12];
            3'd6:    nib = eff[3:0];
            default: nib = eff[7:4];
        endcase
        case (nib)
            4'h0: dec = 7'h40;
            4'h1: dec = 7'h79;
            4'h2: dec = 7'h24;
            4'h3: dec = 7'h30;
            4'h4: dec = 7'h19;
            4'h5: dec = 7'h12;
            4'h6: dec = 7'h02;
            4'h7: dec = 7'h78;
            4'h8: dec = 7'h00;
            4'h9: dec = 7'h10;
            4'hA: dec = 7'h08;
            4'hB: dec = 7'h03;
            4'hC: dec = 7'h46;
            4'hD: dec = 7'h21;
            4'hE: dec = 7'h06;
            default: dec = 7'h0E;
        endcase
    end

    wire blank = ctrl[1] || (digit == 3'd4) || (digit == 3'd5);

    always_ff @(posedge clk) begin
        if (rst) begin
            scan  <= '0;
            digit <= 3'd0;
            seg_r <= 7'h7F;
            an_r  <= 8'hFF;
        end else begin
            if (scan == SW_'(SCAN_DIGIT_CYCLES - 1)) begin
                scan  <= '0;
                digit <= digit + 3'd1;
            end else begin
                scan <= scan + 1'b1;
            end
            seg_r <= blank ? 7'h7F : dec;
            an_r  <= blank ? 8'hFF : ~(8'h01 << digit);
        end
    end
    assign SEG = seg_r;
    assign AN  = an_r;
    assign DP  = 1'b1;
endmodule
