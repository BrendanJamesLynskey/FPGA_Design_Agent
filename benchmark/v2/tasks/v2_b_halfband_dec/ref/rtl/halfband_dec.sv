// halfband_dec.sv: seven-tap half-band decimate-by-two, convergent rounding, saturating, 8-entry queue (v2_b_halfband_dec).
module halfband_dec (
    input  logic        clk_hb,
    input  logic        rst_hb,
    input  logic [6:0]  win_addr_hb,
    input  logic        win_wr_hb,
    input  logic        win_rd_hb,
    input  logic [31:0] win_wdata_hb,
    output logic [31:0] win_rdata_hb
);
    logic signed [15:0] h_hb [6];                       // x[n-1] .. x[n-6]
    logic signed [15:0] q_hb [8];
    logic [2:0]         rp_hb, wp_hb;
    logic [3:0]         cnt_hb;
    logic               odd_hb, sat_hb, ovr_hb;

    wire clr_hb  = win_wr_hb && win_addr_hb == 7'h00 && win_wdata_hb[0];
    wire smp_hb  = win_wr_hb && win_addr_hb == 7'h01;
    wire pop_hb  = win_wr_hb && win_addr_hb == 7'h04 && cnt_hb != 4'd0;
    wire signed [15:0] x0_hb = win_wdata_hb[15:0];

    wire signed [31:0] acc_hb = -32'sd1 * x0_hb + 32'sd9 * h_hb[1] + 32'sd16 * h_hb[2] + 32'sd9 * h_hb[3] - 32'sd1 * h_hb[5];
    wire signed [31:0] qf_hb  = acc_hb >>> 5;
    wire [4:0]         rem_hb = acc_hb[4:0];
    wire               up_hb  = (rem_hb > 5'd16) || (rem_hb == 5'd16 && qf_hb[0]);
    wire signed [31:0] rnd_hb = qf_hb + (up_hb ? 32'sd1 : 32'sd0);
    wire               hi_hb  = rnd_hb > 32'sd32767;
    wire               lo_hb  = rnd_hb < -32'sd32768;
    wire signed [15:0] y_hb   = hi_hb ? 16'sh7FFF : lo_hb ? 16'sh8000 : rnd_hb[15:0];
    wire               res_hb = smp_hb && odd_hb;             // the second sample of a pair makes a result

    always_ff @(posedge clk_hb) begin
        if (rst_hb || clr_hb) begin
            for (int i_hb = 0; i_hb < 6; i_hb++) h_hb[i_hb] <= '0;
            rp_hb <= '0; wp_hb <= '0; cnt_hb <= '0; odd_hb <= 1'b0; sat_hb <= 1'b0; ovr_hb <= 1'b0;
        end else begin
            if (smp_hb) begin
                h_hb[0] <= x0_hb;
                for (int i_hb = 1; i_hb < 6; i_hb++) h_hb[i_hb] <= h_hb[i_hb-1];
                odd_hb <= ~odd_hb;
            end
            if (res_hb) begin
                if (hi_hb || lo_hb) sat_hb <= 1'b1;
                if (cnt_hb == 4'd8) ovr_hb <= 1'b1;
                else begin
                    q_hb[wp_hb] <= y_hb;
                    wp_hb    <= wp_hb + 3'd1;
                    cnt_hb   <= cnt_hb + 4'd1;
                end
            end else if (pop_hb) begin
                rp_hb  <= rp_hb + 3'd1;
                cnt_hb <= cnt_hb - 4'd1;
            end
        end
    end

    always_ff @(posedge clk_hb) begin
        if (rst_hb) win_rdata_hb <= '0;
        else if (win_rd_hb) begin
            case (win_addr_hb)
                7'h02:   win_rdata_hb <= {25'd0, odd_hb, sat_hb, ovr_hb, cnt_hb};
                7'h03:   win_rdata_hb <= (cnt_hb != 4'd0) ? 32'(q_hb[rp_hb]) : 32'd0;
                default: win_rdata_hb <= '0;
            endcase
        end
    end
endmodule
