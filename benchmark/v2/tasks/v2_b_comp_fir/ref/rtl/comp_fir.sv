// comp_fir.sv: nine-tap symmetric FIR, round-to-nearest and saturating, with an 8-entry newest-wins queue (v2_b_comp_fir).
module comp_fir (
    input  logic        clk_cf,
    input  logic        rst_cf,
    input  logic [6:0]  win_addr_cf,
    input  logic        win_wr_cf,
    input  logic        win_rd_cf,
    input  logic [31:0] win_wdata_cf,
    output logic [31:0] win_rdata_cf
);
    logic signed [15:0] h_cf [8];                       // x[n-1] .. x[n-8]
    logic signed [15:0] q_cf [8];
    logic [2:0]         rp_cf, wp_cf;
    logic [3:0]         cnt_cf;
    logic               sat_cf, lost_cf;

    wire clr_cf  = win_wr_cf && win_addr_cf == 7'h00 && win_wdata_cf[0];
    wire smp_cf  = win_wr_cf && win_addr_cf == 7'h01;
    wire pop_cf  = win_wr_cf && win_addr_cf == 7'h04 && cnt_cf != 4'd0;
    wire signed [15:0] x0_cf = win_wdata_cf[15:0];

    wire signed [31:0] acc_cf = 32'sd2   * x0_cf   + -32'sd6  * h_cf[0] + 32'sd16 * h_cf[1] + -32'sd48 * h_cf[2]
                           + 32'sd584 * h_cf[3] + -32'sd48 * h_cf[4] + 32'sd16 * h_cf[5] + -32'sd6  * h_cf[6] + 32'sd2 * h_cf[7];

    wire signed [31:0] rnd_cf = (acc_cf + 32'sd256) >>> 9;
    wire               hi_cf  = rnd_cf > 32'sd32767;
    wire               lo_cf  = rnd_cf < -32'sd32768;
    wire signed [15:0] y_cf   = hi_cf ? 16'sh7FFF : lo_cf ? 16'sh8000 : rnd_cf[15:0];

    always_ff @(posedge clk_cf) begin
        if (rst_cf || clr_cf) begin
            for (int i_cf = 0; i_cf < 8; i_cf++) h_cf[i_cf] <= '0;
            rp_cf <= '0; wp_cf <= '0; cnt_cf <= '0; sat_cf <= 1'b0; lost_cf <= 1'b0;
        end else begin
            if (smp_cf) begin
                h_cf[0] <= x0_cf;
                for (int i_cf = 1; i_cf < 8; i_cf++) h_cf[i_cf] <= h_cf[i_cf-1];
                if (hi_cf || lo_cf) sat_cf <= 1'b1;
                q_cf[wp_cf] <= y_cf;
                wp_cf <= wp_cf + 3'd1;
                if (cnt_cf == 4'd8) begin
                    rp_cf   <= rp_cf + 3'd1;
                    lost_cf <= 1'b1;
                end else begin
                    cnt_cf <= cnt_cf + 4'd1;
                end
            end else if (pop_cf) begin
                rp_cf  <= rp_cf + 3'd1;
                cnt_cf <= cnt_cf - 4'd1;
            end
        end
    end

    always_ff @(posedge clk_cf) begin
        if (rst_cf) win_rdata_cf <= '0;
        else if (win_rd_cf) begin
            case (win_addr_cf)
                7'h02:   win_rdata_cf <= {26'd0, lost_cf, sat_cf, cnt_cf};
                7'h03:   win_rdata_cf <= (cnt_cf != 4'd0) ? 32'(q_cf[rp_cf]) : 32'd0;
                default: win_rdata_cf <= '0;
            endcase
        end
    end
endmodule
