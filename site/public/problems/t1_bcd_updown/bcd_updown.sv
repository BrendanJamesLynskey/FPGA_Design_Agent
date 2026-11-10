// bcd_updown.sv: the counter, wrap count, binary-to-BCD converter, LEDs and
// display contents of t1_bcd_updown, behind the shell's register window.
module bcd_updown #(
    parameter int DEBOUNCE_CYCLES = 1_000_000
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        btn_up,
    input  logic        btn_down,
    input  logic [1:0]  sw_async,
    output logic [15:0] led,
    output logic [7:0][6:0] seg_lit,
    output logic [7:0]  blank,
    input  logic [6:0]  win_addr,
    input  logic        win_wr,
    input  logic        win_rd,
    input  logic [31:0] win_wdata,
    output logic [31:0] win_rdata
);
    localparam logic [6:0] R_COUNT = 7'h00, R_BCD = 7'h01, R_WRAPS = 7'h02, R_STEP = 7'h03;

    logic       up_lvl, dn_lvl, p_up, p_dn;
    logic [1:0] sw;
    logic [13:0] count, step;
    logic [7:0]  wraps;
    logic [14:0] sum;
    logic signed [14:0] diff;

    bm_debounce #(.CYCLES(DEBOUNCE_CYCLES)) u_up (.clk(clk), .rst(rst), .d_async(btn_up),   .level(up_lvl), .rise(p_up));
    bm_debounce #(.CYCLES(DEBOUNCE_CYCLES)) u_dn (.clk(clk), .rst(rst), .d_async(btn_down), .level(dn_lvl), .rise(p_dn));
    sync2 #(.WIDTH(2)) u_sw (.clk(clk), .rst(rst), .d(sw_async), .q(sw));

    always_comb begin
        case (sw)
            2'd0: step = 14'd1;
            2'd1: step = 14'd2;
            2'd2: step = 14'd5;
            default: step = 14'd10;
        endcase
    end

    assign sum  = {1'b0, count} + {1'b0, step};
    assign diff = $signed({1'b0, count}) - $signed({1'b0, step});

    wire wr_count = win_wr && win_addr == R_COUNT && win_wdata < 32'd10000;

    always_ff @(posedge clk) begin
        if (rst) begin
            count <= '0;
            wraps <= '0;
        end else begin
            if (wr_count) begin
                count <= win_wdata[13:0];
            end else if (p_up && !p_dn) begin
                if (sum >= 15'd10000) begin
                    count <= 14'(sum - 15'd10000);
                    wraps <= wraps + 1'b1;
                end else begin
                    count <= sum[13:0];
                end
            end else if (p_dn && !p_up) begin
                if (diff < 0) begin
                    count <= 14'(diff + 15'sd10000);
                    wraps <= wraps + 1'b1;
                end else begin
                    count <= diff[13:0];
                end
            end
            if (win_wr && win_addr == R_WRAPS) wraps <= '0;
        end
    end

    // Iterative binary-to-BCD (shift and add 3): one conversion every 15 clocks.
    logic [13:0] sh_bin;
    logic [15:0] sh_bcd, bcd;
    logic [3:0]  sh_n;
    function automatic logic [15:0] add3(input logic [15:0] b);
        for (int i = 0; i < 4; i++)
            if (b[4*i +: 4] >= 4'd5) b[4*i +: 4] = b[4*i +: 4] + 4'd3;
        return b;
    endfunction
    always_ff @(posedge clk) begin
        if (rst) begin
            sh_n <= '0; sh_bin <= '0; sh_bcd <= '0; bcd <= '0;
        end else if (sh_n == 4'd0) begin
            sh_bin <= count; sh_bcd <= '0; sh_n <= 4'd1;
        end else begin
            {sh_bcd, sh_bin} <= {add3(sh_bcd), sh_bin} << 1;
            if (sh_n == 4'd14) begin
                bcd  <= add3(sh_bcd) << 1 | 16'(sh_bin[13]);
                sh_n <= 4'd0;
            end else begin
                sh_n <= sh_n + 1'b1;
            end
        end
    end

    function automatic logic [6:0] glyph(input logic [3:0] d);
        case (d)                       // bit 0 = a ... bit 6 = g, 1 = lit
            4'd0: glyph = 7'b0111111;  4'd1: glyph = 7'b0000110;
            4'd2: glyph = 7'b1011011;  4'd3: glyph = 7'b1001111;
            4'd4: glyph = 7'b1100110;  4'd5: glyph = 7'b1101101;
            4'd6: glyph = 7'b1111101;  4'd7: glyph = 7'b0000111;
            4'd8: glyph = 7'b1111111;  4'd9: glyph = 7'b1101111;
            default: glyph = 7'b0000000;
        endcase
    endfunction

    always_comb begin
        for (int k = 0; k < 8; k++) seg_lit[k] = (k < 4) ? glyph(bcd[4*k +: 4]) : 7'b0;
        blank[0] = 1'b0;
        blank[1] = bcd[15:4] == 12'd0;
        blank[2] = bcd[15:8] == 8'd0;
        blank[3] = bcd[15:12] == 4'd0;
        blank[7:4] = 4'hF;
    end

    assign led = {2'b00, count};

    always_ff @(posedge clk) begin
        if (rst) win_rdata <= '0;
        else if (win_rd) begin
            case (win_addr)
                R_COUNT: win_rdata <= {18'd0, count};
                R_BCD:   win_rdata <= {16'd0, bcd};
                R_WRAPS: win_rdata <= {24'd0, wraps};
                R_STEP:  win_rdata <= {28'd0, step[3:0]};
                default: win_rdata <= '0;
            endcase
        end
    end
endmodule
