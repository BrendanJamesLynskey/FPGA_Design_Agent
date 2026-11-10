// press_classifier.sv: debounced BTNC press timing and short/long classification
// for t1_press_classifier, behind the shell's register window.
module press_classifier #(
    parameter int DEBOUNCE_CYCLES = 1_000_000,
    parameter int LONG_CYCLES     = 50_000_000,
    parameter int TICK_CYCLES     = 100_000
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        btn,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam logic [6:0] R_SHORT = 7'h00, R_LONG = 7'h01, R_LAST = 7'h02, R_STATUS = 7'h03;
    localparam int HW = $clog2(LONG_CYCLES + 1);
    localparam int TW = $clog2(TICK_CYCLES + 1);

    logic          lvl, lvl_d, rise, fall;
    logic [HW-1:0] hi;
    logic [TW-1:0] pre;
    logic [15:0]   ticks, short_cnt, long_cnt, last;
    logic          last_long, tog_s, tog_l, is_long;

    bm_debounce #(.CYCLES(DEBOUNCE_CYCLES)) u_db (.clk(clk), .rst(rst), .d_async(btn), .level(lvl), .rise(rise));

    assign fall    = lvl_d && !lvl;
    assign is_long = hi >= HW'(LONG_CYCLES);

    always_ff @(posedge clk) begin
        if (rst) begin
            lvl_d <= 1'b0; hi <= '0; pre <= '0; ticks <= '0;
            short_cnt <= '0; long_cnt <= '0; last <= '0; last_long <= 1'b0;
            tog_s <= 1'b0; tog_l <= 1'b0;
        end else begin
            lvl_d <= lvl;
            if (lvl) begin
                if (hi != HW'(LONG_CYCLES)) hi <= hi + 1'b1;
                if (pre == TW'(TICK_CYCLES - 1)) begin
                    pre <= '0;
                    if (ticks != 16'hFFFF) ticks <= ticks + 1'b1;
                end else begin
                    pre <= pre + 1'b1;
                end
            end else begin
                hi <= '0; pre <= '0; ticks <= '0;
            end
            if (fall) begin
                last      <= ticks;
                last_long <= is_long;
                if (is_long) begin
                    long_cnt <= long_cnt + 1'b1;
                    tog_l    <= ~tog_l;
                end else begin
                    short_cnt <= short_cnt + 1'b1;
                    tog_s     <= ~tog_s;
                end
            end
            if (win_wr && win_addr == R_SHORT) short_cnt <= '0;
            if (win_wr && win_addr == R_LONG)  long_cnt  <= '0;
        end
    end

    assign led = {short_cnt[7:0], 6'd0, tog_l, tog_s};

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                R_SHORT:  win_rdata <= {16'd0, short_cnt};
                R_LONG:   win_rdata <= {16'd0, long_cnt};
                R_LAST:   win_rdata <= {15'd0, last_long, last};
                R_STATUS: win_rdata <= {29'd0, tog_l, tog_s, lvl};
                default:  win_rdata <= '0;
            endcase
        end
    end
endmodule
