// Gray-code stepper core: count, step counter, auto timer and register window.
module gray_core #(
    parameter int TICK_CYCLES = 100_000
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        btn_step,   // one-clock pulse
    input  logic        dir_down,   // synchronised SW[15]
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    /* verilator lint_off UNUSEDSIGNAL */
    input  logic [31:0] win_wdata,
    /* verilator lint_on UNUSEDSIGNAL */
    output logic [31:0] win_rdata,
    output logic [9:0]  gray,
    output logic        auto_on
);
    localparam int TW = (TICK_CYCLES > 1) ? $clog2(TICK_CYCLES) : 1;

    logic [9:0]  bin;
    logic [15:0] steps;
    logic [15:0] rate;
    logic [TW-1:0] tick_cnt;
    logic [15:0] rate_cnt;
    logic        auto_step;
    logic        step;
    logic        auto_off_wr;

    assign gray = bin ^ (bin >> 1);
    // a write turning auto mode off on this clock cancels a pending auto step,
    // so LED[15] is never 0 on the clock an automatic step lands
    assign auto_off_wr = win_wr && (win_addr == 7'd2) && !win_wdata[0];
    assign step = btn_step | (auto_step & auto_on & ~auto_off_wr);

    // automatic step generator: runs only while auto mode is on and RATE != 0
    always_ff @(posedge clk) begin
        auto_step <= 1'b0;
        if (rst || !auto_on || rate == 16'd0) begin
            tick_cnt <= '0;
            rate_cnt <= 16'd0;
        end else if (tick_cnt == TW'(TICK_CYCLES - 1)) begin
            tick_cnt <= '0;
            if ({1'b0, rate_cnt} + 17'd1 >= {1'b0, rate}) begin
                rate_cnt  <= 16'd0;
                auto_step <= 1'b1;
            end else begin
                rate_cnt <= rate_cnt + 16'd1;
            end
        end else begin
            tick_cnt <= tick_cnt + 1'b1;
        end
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            bin     <= 10'd0;
            steps   <= 16'd0;
            auto_on <= 1'b0;
            rate    <= 16'd250;
        end else begin
            if (step) begin
                steps <= steps + 16'd1;
                bin   <= dir_down ? bin - 10'd1 : bin + 10'd1;
            end
            if (win_wr) begin
                case (win_addr)
                    7'd1: bin     <= win_wdata[9:0];
                    7'd2: auto_on <= win_wdata[0];
                    7'd3: rate    <= win_wdata[15:0];
                    default: ;
                endcase
            end
        end
    end

    always_ff @(posedge clk) begin
        if (win_rd) begin
            case (win_addr)
                7'd0:    win_rdata <= {22'd0, gray};
                7'd1:    win_rdata <= {22'd0, bin};
                7'd2:    win_rdata <= {23'd0, dir_down, 7'd0, auto_on};
                7'd3:    win_rdata <= {16'd0, rate};
                7'd4:    win_rdata <= {16'd0, steps};
                default: win_rdata <= 32'd0;
            endcase
        end
    end
endmodule
