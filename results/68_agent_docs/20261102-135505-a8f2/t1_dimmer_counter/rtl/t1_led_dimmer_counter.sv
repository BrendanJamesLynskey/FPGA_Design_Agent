`default_nettype none

module t1_led_dimmer_counter #(
    parameter integer DEBOUNCE_CYCLES = 1000000,
    parameter integer PWM_PERIOD_CYCLES = 4096,
    parameter integer DISPLAY_DIGIT_CYCLES = 100000,
    parameter integer UART_BAUD_DIVIDER_CYCLES = 868
) (
    input  wire logic        clk,
    input  wire logic        cpu_resetn,
    input  wire logic        btn_up,
    input  wire logic        btn_down,
    input  wire logic        btn_center,
    input  wire logic [7:0]  switches,
    output      logic [15:0] leds,
    output      logic [6:0]  seg,
    output      logic        dp,
    output      logic [7:0]  an,
    input  wire logic        uart_rxd,
    output      logic        uart_txd
);
    localparam integer DB_W = (DEBOUNCE_CYCLES < 2) ? 1 : $clog2(DEBOUNCE_CYCLES + 1);
    localparam integer PWM_W = (PWM_PERIOD_CYCLES < 2) ? 1 : $clog2(PWM_PERIOD_CYCLES);
    localparam integer DISP_W = (DISPLAY_DIGIT_CYCLES < 2) ? 1 : $clog2(DISPLAY_DIGIT_CYCLES);

    logic [1:0] reset_sync;
    logic rst;
    logic shell_rst;
    logic [6:0] win_addr;
    logic win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;
    logic [15:0] counter;
    logic [7:0] brightness;
    logic [1:0] control;
    logic [31:0] up_count, down_count, center_count;

    logic [2:0] btn_meta, btn_sync, btn_debounced, debounce_candidate;
    logic [DB_W-1:0] debounce_count [0:2];
    logic [PWM_W-1:0] pwm_phase;
    logic [DISP_W-1:0] display_count;
    logic [2:0] display_digit;
    logic [7:0] effective_brightness;
    logic pwm_on;
    logic [3:0] hex_digit;

    always_ff @(posedge clk or negedge cpu_resetn) begin
        if (!cpu_resetn)
            reset_sync <= 2'b00;
        else
            reset_sync <= {reset_sync[0], 1'b1};
    end
    assign shell_rst = ~reset_sync[1];
    assign rst = ~cpu_resetn;

    fpga_shell #(
        .CLKS_PER_BIT(UART_BAUD_DIVIDER_CYCLES),
        .TIMEOUT_CYCLES(100_000),
        .DESIGN_ID(32'h5431_4443),
        .BUILD_STAMP(32'h0000_0000)
    ) u_fpga_shell (
        .clk(clk), .rst(shell_rst), .uart_rx(uart_rxd), .uart_tx(uart_txd),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata)
    );

    always @* begin
        effective_brightness = control[0] ? switches : brightness;
        pwm_on = (effective_brightness == 8'hff) ||
                 ((effective_brightness != 0) &&
                  (int'(pwm_phase) < ((effective_brightness * PWM_PERIOD_CYCLES + 254) / 255)));
        leds = pwm_on ? counter : 16'h0000;
        dp = 1'b1;
        an = 8'hff;
        seg = 7'h7f;
        hex_digit = 4'h0;
        if (!control[1] && (display_digit != 3'd4) && (display_digit != 3'd5)) begin
            an = 8'hff ^ (8'b1 << display_digit);
            if (display_digit == 3'd7)
                hex_digit = effective_brightness[7:4];
            else if (display_digit == 3'd6)
                hex_digit = effective_brightness[3:0];
            else
                hex_digit = counter[(display_digit * 4) +: 4];
            case (hex_digit)
                4'h0: seg=7'h01; 4'h1: seg=7'h4f; 4'h2: seg=7'h12; 4'h3: seg=7'h06;
                4'h4: seg=7'h4c; 4'h5: seg=7'h24; 4'h6: seg=7'h20; 4'h7: seg=7'h0f;
                4'h8: seg=7'h00; 4'h9: seg=7'h04; 4'ha: seg=7'h08; 4'hb: seg=7'h60;
                4'hc: seg=7'h31; 4'hd: seg=7'h42; 4'he: seg=7'h30; 4'hf: seg=7'h38;
            endcase
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            counter <= 16'd0;
            brightness <= 8'hff;
            control <= 2'b00;
            up_count <= 32'd0;
            down_count <= 32'd0;
            center_count <= 32'd0;
            btn_meta <= 3'b000;
            btn_sync <= 3'b000;
            btn_debounced <= 3'b000;
            debounce_candidate <= 3'b000;
            debounce_count[0] <= '0;
            debounce_count[1] <= '0;
            debounce_count[2] <= '0;
            pwm_phase <= '0;
            display_count <= '0;
            display_digit <= '0;
            win_rdata <= 32'd0;
        end else begin
            btn_meta <= {btn_center, btn_down, btn_up};
            btn_sync <= btn_meta;
            if (int'(pwm_phase) == PWM_PERIOD_CYCLES-1) pwm_phase <= '0;
            else pwm_phase <= pwm_phase + 1'b1;
            if (int'(display_count) == DISPLAY_DIGIT_CYCLES-1) begin
                display_count <= '0;
                display_digit <= display_digit + 1'b1;
            end else display_count <= display_count + 1'b1;

            // Debounce each synchronized active-high button; count a press only on qualification.
            if (btn_sync[0] == btn_debounced[0]) begin
                debounce_candidate[0] <= btn_sync[0]; debounce_count[0] <= '0;
            end else if (btn_sync[0] != debounce_candidate[0]) begin
                debounce_candidate[0] <= btn_sync[0]; debounce_count[0] <= 1;
            end else if (int'(debounce_count[0]) + 1 >= DEBOUNCE_CYCLES) begin
                btn_debounced[0] <= btn_sync[0]; debounce_count[0] <= '0;
                if (btn_sync[0]) up_count <= up_count + 1'b1;
            end else debounce_count[0] <= debounce_count[0] + 1'b1;

            if (btn_sync[1] == btn_debounced[1]) begin
                debounce_candidate[1] <= btn_sync[1]; debounce_count[1] <= '0;
            end else if (btn_sync[1] != debounce_candidate[1]) begin
                debounce_candidate[1] <= btn_sync[1]; debounce_count[1] <= 1;
            end else if (int'(debounce_count[1]) + 1 >= DEBOUNCE_CYCLES) begin
                btn_debounced[1] <= btn_sync[1]; debounce_count[1] <= '0;
                if (btn_sync[1]) down_count <= down_count + 1'b1;
            end else debounce_count[1] <= debounce_count[1] + 1'b1;

            if (btn_sync[2] == btn_debounced[2]) begin
                debounce_candidate[2] <= btn_sync[2]; debounce_count[2] <= '0;
            end else if (btn_sync[2] != debounce_candidate[2]) begin
                debounce_candidate[2] <= btn_sync[2]; debounce_count[2] <= 1;
            end else if (int'(debounce_count[2]) + 1 >= DEBOUNCE_CYCLES) begin
                btn_debounced[2] <= btn_sync[2]; debounce_count[2] <= '0;
                if (btn_sync[2]) center_count <= center_count + 1'b1;
            end else debounce_count[2] <= debounce_count[2] + 1'b1;

            if (win_wr) begin
                case (win_addr)
                    7'd0: counter <= win_wdata[15:0];
                    7'd4: brightness <= win_wdata[7:0];
                    7'd8: control <= win_wdata[1:0];
                    default: begin end
                endcase
            end else if (btn_sync[2] && !btn_debounced[2] && (int'(debounce_count[2]) + 1 >= DEBOUNCE_CYCLES))
                counter <= 16'd0;
            else if (btn_sync[0] && !btn_debounced[0] && (int'(debounce_count[0]) + 1 >= DEBOUNCE_CYCLES))
                counter <= counter + 1'b1;
            else if (btn_sync[1] && !btn_debounced[1] && (int'(debounce_count[1]) + 1 >= DEBOUNCE_CYCLES))
                counter <= counter - 1'b1;

            if (win_rd) begin
                case (win_addr)
                    7'd0: win_rdata <= {16'd0, counter};
                    7'd4: win_rdata <= {24'd0, brightness};
                    7'd8: win_rdata <= {30'd0, control};
                    7'd12: win_rdata <= {21'd0, btn_center, btn_down, btn_up, switches};
                    7'd16: win_rdata <= up_count;
                    7'd20: win_rdata <= down_count;
                    7'd24: win_rdata <= center_count;
                    7'd28: win_rdata <= 32'h5431_4443;
                    default: win_rdata <= 32'd0;
                endcase
            end
        end
    end

    logic unused_uart;
    always @* unused_uart = uart_rxd ^ win_wr ^ (^win_wdata[31:16]) ^ win_addr[6];
endmodule

`default_nettype wire
