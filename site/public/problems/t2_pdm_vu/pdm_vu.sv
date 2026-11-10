// pdm_vu.sv: PDM microphone clock (registered, period 2 * CLK_HALF), samples at
// the M_CLK falling edge (M_LRSEL = 1 channel), ones per WINDOW-sample block,
// LEVEL = |ones - WINDOW/2|, PEAK with hold and decay, LED bar.
module pdm_vu #(
    parameter int CLK_HALF = 20,
    parameter int WINDOW   = 4096
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        mdata,       // synchronised
    output logic        mclk,
    output logic [15:0] led,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam int HW = $clog2(CLK_HALF + 1);
    localparam int NW = $clog2(WINDOW + 1);
    localparam int STEP = WINDOW / 32;

    logic [HW-1:0] hc;
    logic [NW-1:0] n, ones, ones_last;
    logic [15:0]   level, peak;
    logic [7:0]    hold_set, hold;
    logic [3:0]    decay;
    logic [31:0]   blocks;

    wire fall = mclk && hc == HW'(CLK_HALF - 1);
    wire last = fall && n == NW'(WINDOW - 1);
    wire [NW-1:0] ones_n = ones + {{(NW-1){1'b0}}, mdata};
    wire [15:0] lvl_n = (ones_n >= NW'(WINDOW / 2)) ? 16'(ones_n - NW'(WINDOW / 2)) : 16'(NW'(WINDOW / 2) - ones_n);

    always_ff @(posedge clk) begin
        if (rst) begin
            hc <= '0; mclk <= 1'b0; n <= '0; ones <= '0; ones_last <= '0; level <= '0; peak <= '0;
            hold_set <= 8'd8; decay <= 4'd1; hold <= '0; blocks <= '0; led <= '0;
        end else begin
            if (win_wr && win_addr == 7'h00) {decay, hold_set} <= win_wdata[11:0];
            if (hc == HW'(CLK_HALF - 1)) begin
                hc <= '0;
                mclk <= ~mclk;
            end else begin
                hc <= hc + 1'b1;
            end
            if (fall) begin
                if (last) begin
                    n <= '0; ones <= '0; ones_last <= ones_n; level <= lvl_n; blocks <= blocks + 1'b1;
                    for (int i = 0; i < 16; i++) led[i] <= lvl_n >= 16'((i + 1) * STEP);
                    if (lvl_n > peak)      begin peak <= lvl_n; hold <= hold_set; end
                    else if (hold != '0)   hold <= hold - 1'b1;
                    else                   peak <= (peak < {12'd0, decay}) ? 16'd0 : peak - {12'd0, decay};
                end else begin
                    n <= n + 1'b1; ones <= ones_n;
                end
            end
            if (win_wr && win_addr == 7'h02) begin peak <= '0; hold <= '0; end
        end
    end

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                7'h00:   win_rdata <= {20'd0, decay, hold_set};
                7'h01:   win_rdata <= {16'd0, level};
                7'h02:   win_rdata <= {16'd0, peak};
                7'h03:   win_rdata <= 32'(ones_last);
                7'h04:   win_rdata <= blocks;
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
