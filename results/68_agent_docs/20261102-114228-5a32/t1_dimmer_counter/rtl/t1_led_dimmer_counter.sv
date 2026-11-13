// Board-level T1 LED dimmer/counter.
`default_nettype none
module t1_led_dimmer_counter #(
    parameter int unsigned DEBOUNCE_CYCLES = 1_000_000,
    parameter int unsigned PWM_PERIOD_CYCLES = 256,
    parameter int unsigned DISPLAY_SCAN_CYCLES = 100_000,
    parameter int unsigned UART_BAUD_DIVIDER = 868
) (
    input wire logic clk,
    input wire logic cpu_reset_n,
    input wire logic button_up,
    input wire logic button_down,
    input wire logic button_center,
    input wire logic [7:0] switches,
    input wire logic uart_rx,
    output logic uart_tx,
    output logic [15:0] leds,
    output logic [7:0] segments_n,
    output logic [7:0] digit_enable_n
);
    localparam logic [31:0] DESIGN_ID = 32'h5431_4443;
    localparam int unsigned PWM_W = (PWM_PERIOD_CYCLES > 1) ? $clog2(PWM_PERIOD_CYCLES) : 1;
    localparam int unsigned DEBOUNCE_W = (DEBOUNCE_CYCLES > 1) ? $clog2(DEBOUNCE_CYCLES) : 1;
    localparam int unsigned SCAN_W = (DISPLAY_SCAN_CYCLES > 1) ? $clog2(DISPLAY_SCAN_CYCLES) : 1;

    logic reset_meta, reset_sync;
    wire logic rst = reset_sync;
    logic [6:0] win_addr;
    logic win_wr, win_rd;
    logic [31:0] win_wdata, win_rdata;
    logic [15:0] counter;
    logic [7:0] brightness;
    logic [31:0] control;
    logic [7:0] switches_sync;
    logic [2:0] button_meta, button_sync, button_level, button_rise;
    logic [DEBOUNCE_W-1:0] debounce_count [0:2];
    logic [31:0] up_count, down_count, center_count;
    logic [PWM_W-1:0] pwm_phase;
    logic [SCAN_W-1:0] scan_count;
    logic [2:0] digit;
    logic [7:0] active_brightness;
    logic [3:0] hex_nibble;
    logic [6:0] segments_on;
    logic [15:0] leds_next;
    logic [7:0] segments_next, digit_enable_next;

    fpga_shell #(.CLKS_PER_BIT(UART_BAUD_DIVIDER), .TIMEOUT_CYCLES(100_000),
                 .DESIGN_ID(DESIGN_ID), .BUILD_STAMP(32'h0)) u_fpga_shell (
        .clk(clk), .rst(rst), .uart_rx(uart_rx), .uart_tx(uart_tx),
        .win_addr(win_addr), .win_wr(win_wr), .win_rd(win_rd),
        .win_wdata(win_wdata), .win_rdata(win_rdata)
    );

    // Asynchronous assertion and two-clock synchronous release.
    always_ff @(posedge clk or negedge cpu_reset_n) begin
        if (!cpu_reset_n) begin reset_meta <= 1'b1; reset_sync <= 1'b1; end
        else begin reset_meta <= 1'b0; reset_sync <= reset_meta; end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            switches_sync <= '0;
            button_meta <= '0;
            button_sync <= '0;
        end else begin
            switches_sync <= switches;
            button_meta <= {button_center, button_down, button_up};
            button_sync <= button_meta;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            button_level <= '0;
            for (int i = 0; i < 3; i++) debounce_count[i] <= '0;
        end else begin
            for (int i = 0; i < 3; i++) begin
                if (button_sync[i] == button_level[i]) debounce_count[i] <= '0;
                else if (DEBOUNCE_CYCLES <= 1 || debounce_count[i] == DEBOUNCE_W'(DEBOUNCE_CYCLES - 1)) begin
                    button_level[i] <= button_sync[i];
                    debounce_count[i] <= '0;
                end else debounce_count[i] <= debounce_count[i] + 1'b1;
            end
        end
    end
    always_comb begin
        button_rise = '0;
        for (int i = 0; i < 3; i++)
            if (button_sync[i] && !button_level[i] &&
                (DEBOUNCE_CYCLES <= 1 || debounce_count[i] == DEBOUNCE_W'(DEBOUNCE_CYCLES - 1)))
                button_rise[i] = 1'b1;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            counter <= '0; brightness <= '0; control <= '0;
            up_count <= '0; down_count <= '0; center_count <= '0;
        end else begin
            if (win_wr) begin
                case (win_addr)
                    7'h04: counter <= win_wdata[15:0];
                    7'h08: brightness <= win_wdata[7:0];
                    7'h0C: control <= win_wdata;
                    default: begin end
                endcase
            end
            if (button_rise[0]) up_count <= up_count + 1'b1;
            if (button_rise[1]) down_count <= down_count + 1'b1;
            if (button_rise[2]) center_count <= center_count + 1'b1;
            if (!(win_wr && win_addr == 7'h04)) begin
                if (button_rise[2]) counter <= '0;
                else if (button_rise[0] && !button_rise[1]) counter <= counter + 1'b1;
                else if (button_rise[1] && !button_rise[0]) counter <= counter - 1'b1;
            end
        end
    end

    always_comb active_brightness = control[0] ? switches_sync : brightness;

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00: win_rdata <= DESIGN_ID;
                7'h04: win_rdata <= {16'b0, counter};
                7'h08: win_rdata <= {24'b0, brightness};
                7'h0C: win_rdata <= control;
                7'h10: win_rdata <= {29'b0, button_level};
                7'h14: win_rdata <= {24'b0, switches_sync};
                7'h18: win_rdata <= up_count;
                7'h1C: win_rdata <= down_count;
                7'h20: win_rdata <= center_count;
                default: win_rdata <= '0;
            endcase
        end
    end

    always_ff @(posedge clk) begin
        if (rst) pwm_phase <= '0;
        else if (pwm_phase == PWM_W'(PWM_PERIOD_CYCLES - 1)) pwm_phase <= '0;
        else pwm_phase <= pwm_phase + 1'b1;
    end
    always_comb begin
        if (active_brightness == 8'hFF) leds_next = counter;
        else if (PWM_PERIOD_CYCLES == 256)
            leds_next = (pwm_phase < PWM_W'(active_brightness)) ? counter : 16'b0;
        else leds_next = (pwm_phase < PWM_W'((active_brightness * PWM_PERIOD_CYCLES + 254) / 255)) ? counter : 16'b0;
    end
    // Register board-facing outputs to keep combinational decode and PWM logic
    // off the package-pin timing paths.
    always_ff @(posedge clk) begin
        if (rst) leds <= '0;
        else leds <= leds_next;
    end

    always_ff @(posedge clk) begin
        if (rst) begin scan_count <= '0; digit <= '0; end
        else if (scan_count == SCAN_W'(DISPLAY_SCAN_CYCLES - 1)) begin
            scan_count <= '0;
            digit <= digit + 1'b1;
        end else scan_count <= scan_count + 1'b1;
    end

    always_comb begin
        hex_nibble = '0;
        case (digit)
            3'd0: hex_nibble = counter[3:0];
            3'd1: hex_nibble = counter[7:4];
            3'd2: hex_nibble = counter[11:8];
            3'd3: hex_nibble = counter[15:12];
            3'd6: hex_nibble = active_brightness[3:0];
            3'd7: hex_nibble = active_brightness[7:4];
            default: hex_nibble = '0;
        endcase
        case (hex_nibble)
            4'h0: segments_on = 7'h3F; 4'h1: segments_on = 7'h06;
            4'h2: segments_on = 7'h5B; 4'h3: segments_on = 7'h4F;
            4'h4: segments_on = 7'h66; 4'h5: segments_on = 7'h6D;
            4'h6: segments_on = 7'h7D; 4'h7: segments_on = 7'h07;
            4'h8: segments_on = 7'h7F; 4'h9: segments_on = 7'h6F;
            4'hA: segments_on = 7'h77; 4'hB: segments_on = 7'h7C;
            4'hC: segments_on = 7'h39; 4'hD: segments_on = 7'h5E;
            4'hE: segments_on = 7'h79; default: segments_on = 7'h71;
        endcase
        digit_enable_next = 8'hFF;
        segments_next = 8'hFF;
        if (!control[1]) begin
            digit_enable_next[digit] = 1'b0;
            if (!(digit == 4 || digit == 5)) segments_next[6:0] = ~segments_on;
        end
    end
    always_ff @(posedge clk) begin
        if (rst) begin segments_n <= 8'hFF; digit_enable_n <= 8'hFF; end
        else begin segments_n <= segments_next; digit_enable_n <= digit_enable_next; end
    end
endmodule
`default_nettype wire
