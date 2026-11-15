// cic_decim.sv: three-stage CIC decimator by 16 for a one-bit stream, with a 16-entry result queue (v2_b_cic_decim).
module cic_decim (
    input  logic        clk_cd,
    input  logic        rst_cd,
    input  logic [6:0]  win_addr_cd,
    input  logic        win_wr_cd,
    input  logic        win_rd_cd,
    input  logic [31:0] win_wdata_cd,
    output logic [31:0] win_rdata_cd
);
    localparam int W = 16;
    logic signed [W-1:0] i1_cd, i2_cd, i3_cd, d1_cd, d2_cd, d3_cd;
    logic [3:0]          phase_cd;
    logic                warm1_cd, warm0_cd;          // set once outputs 0 and 1 have gone by
    logic [31:0]         shreg_cd;
    logic [5:0]          left_cd;
    logic signed [31:0]  q_cd [16];
    logic [3:0]          rp_cd, wp_cd;
    logic [4:0]          cnt_cd;
    logic                ovr_cd;

    wire clr_cd  = win_wr_cd && win_addr_cd == 7'h00 && win_wdata_cd[0];
    wire load_cd = win_wr_cd && win_addr_cd == 7'h01 && left_cd == 6'd0;
    wire pop_cd  = win_wr_cd && win_addr_cd == 7'h04 && cnt_cd != 5'd0;
    wire bit_v_cd = left_cd != 6'd0;
    wire signed [W-1:0] s_cd  = shreg_cd[0] ? 16'sd1 : -16'sd1;
    wire signed [W-1:0] n1_cd = i1_cd + s_cd;
    wire signed [W-1:0] n2_cd = i2_cd + n1_cd;
    wire signed [W-1:0] n3_cd = i3_cd + n2_cd;
    wire signed [W-1:0] c1_cd = n3_cd - d1_cd;
    wire signed [W-1:0] c2_cd = c1_cd - d2_cd;
    wire signed [W-1:0] c3_cd = c2_cd - d3_cd;
    wire out_v_cd = bit_v_cd && phase_cd == 4'd15;
    wire push_cd  = out_v_cd && warm1_cd;

    always_ff @(posedge clk_cd) begin
        if (rst_cd || clr_cd) begin
            i1_cd <= '0; i2_cd <= '0; i3_cd <= '0; d1_cd <= '0; d2_cd <= '0; d3_cd <= '0;
            phase_cd <= '0; warm1_cd <= 1'b0; warm0_cd <= 1'b0; left_cd <= '0; shreg_cd <= '0;
            rp_cd <= '0; wp_cd <= '0; cnt_cd <= '0; ovr_cd <= 1'b0;
        end else begin
            if (load_cd) begin
                shreg_cd <= win_wdata_cd;
                left_cd  <= 6'd32;
            end else if (bit_v_cd) begin
                shreg_cd <= {1'b0, shreg_cd[31:1]};
                left_cd  <= left_cd - 6'd1;
                i1_cd <= n1_cd; i2_cd <= n2_cd; i3_cd <= n3_cd;
                phase_cd <= phase_cd + 4'd1;
                if (out_v_cd) begin
                    d1_cd <= n3_cd; d2_cd <= c1_cd; d3_cd <= c2_cd;
                    warm0_cd <= 1'b1;
                    warm1_cd <= warm0_cd;
                end
            end
            if (push_cd) begin
                if (cnt_cd == 5'd16) ovr_cd <= 1'b1;
                else if (cnt_cd != 5'd16) begin
                    q_cd[wp_cd] <= 32'(c3_cd);
                    wp_cd <= wp_cd + 4'd1;
                end
            end
            if (pop_cd) rp_cd <= rp_cd + 4'd1;
            cnt_cd <= cnt_cd + {4'd0, push_cd && cnt_cd != 5'd16} - {4'd0, pop_cd};
        end
    end

    always_ff @(posedge clk_cd) begin
        if (rst_cd) win_rdata_cd <= '0;
        else if (win_rd_cd) begin
            case (win_addr_cd)
                7'h02:   win_rdata_cd <= {22'd0, left_cd != 6'd0, ovr_cd, 3'd0, cnt_cd};
                7'h03:   win_rdata_cd <= (cnt_cd != 5'd0) ? q_cd[rp_cd] : 32'd0;
                default: win_rdata_cd <= '0;
            endcase
        end
    end
endmodule
