// pdm_chain.sv: PDM microphone clock and sampler, CIC, scale, two half-band decimators, compensating FIR and DC blocker,
// then a 64-sample capture memory (v2_b_pdm_chain). Each stage takes a one-clock valid pulse and answers with another.

module cic_stage (
    input  logic               clk_pc,
    input  logic               clr_pc,
    input  logic               in_v_pc,
    input  logic               in_b_pc,
    output logic               ov_pc,
    output logic signed [15:0] oy_pc
);
    logic signed [15:0] i1_pc, i2_pc, i3_pc, d1_pc, d2_pc, d3_pc;
    logic [3:0]         phase_pc;
    logic               w0_pc, w1_pc;                       // outputs 0 and 1 have gone by
    wire signed [15:0] s_pc  = in_b_pc ? 16'sd1 : -16'sd1;
    wire signed [15:0] n1_pc = i1_pc + s_pc;
    wire signed [15:0] n2_pc = i2_pc + n1_pc;
    wire signed [15:0] n3_pc = i3_pc + n2_pc;
    wire signed [15:0] c1_pc = n3_pc - d1_pc;
    wire signed [15:0] c2_pc = c1_pc - d2_pc;
    wire signed [15:0] c3_pc = c2_pc - d3_pc;
    wire               out_v_pc = in_v_pc && phase_pc == 4'd15;
    always_ff @(posedge clk_pc) begin
        ov_pc <= 1'b0;
        if (clr_pc) begin
            i1_pc <= '0; i2_pc <= '0; i3_pc <= '0; d1_pc <= '0; d2_pc <= '0; d3_pc <= '0; phase_pc <= '0; w0_pc <= 1'b0; w1_pc <= 1'b0;
        end else if (in_v_pc) begin
            i1_pc <= n1_pc; i2_pc <= n2_pc; i3_pc <= n3_pc;
            phase_pc <= phase_pc + 4'd1;
            if (out_v_pc) begin
                d1_pc <= n3_pc; d2_pc <= c1_pc; d3_pc <= c2_pc;
                w0_pc <= 1'b1;
                w1_pc <= w0_pc;
                if (w1_pc) begin
                    ov_pc <= 1'b1;
                    oy_pc <= c3_pc;
                end
            end
        end
    end
endmodule

module scale_stage (
    input  logic               clk_pc,
    input  logic               clr_pc,
    input  logic               in_v_pc,
    input  logic signed [15:0] in_x_pc,
    output logic               ov_pc,
    output logic signed [15:0] oy_pc,
    output logic               sat_pc
);
    wire signed [31:0] v_pc  = 32'(in_x_pc) * 32'sd8;
    wire               hi_pc = v_pc > 32'sd32767;
    wire               lo_pc = v_pc < -32'sd32768;
    always_ff @(posedge clk_pc) begin
        ov_pc <= in_v_pc;
        if (in_v_pc) oy_pc <= hi_pc ? 16'sh7FFF : lo_pc ? 16'sh8000 : v_pc[15:0];
        if (clr_pc) sat_pc <= 1'b0;
        else if (in_v_pc && (hi_pc || lo_pc)) sat_pc <= 1'b1;
    end
endmodule

module hb_stage (
    input  logic               clk_pc,
    input  logic               clr_pc,
    input  logic               in_v_pc,
    input  logic signed [15:0] in_x_pc,
    output logic               ov_pc,
    output logic signed [15:0] oy_pc,
    output logic               sat_pc
);
    logic signed [15:0] h_pc [6];
    logic               odd_pc;
    wire signed [31:0] acc_pc = -32'sd1 * in_x_pc + 32'sd9 * h_pc[1] + 32'sd16 * h_pc[2] + 32'sd9 * h_pc[3] - 32'sd1 * h_pc[5];
    wire signed [31:0] qf_pc  = acc_pc >>> 5;
    wire [4:0]         rem_pc = acc_pc[4:0];
    wire               up_pc  = (rem_pc > 5'd16) || (rem_pc == 5'd16 && qf_pc[0]);
    wire signed [31:0] rnd_pc = qf_pc + (up_pc ? 32'sd1 : 32'sd0);
    wire               hi_pc  = rnd_pc > 32'sd32767;
    wire               lo_pc  = rnd_pc < -32'sd32768;
    wire               res_pc = in_v_pc && odd_pc;
    always_ff @(posedge clk_pc) begin
        ov_pc <= 1'b0;
        if (clr_pc) begin
            for (int i_pc = 0; i_pc < 6; i_pc++) h_pc[i_pc] <= '0;
            odd_pc <= 1'b0; sat_pc <= 1'b0;
        end else if (in_v_pc) begin
            h_pc[0] <= in_x_pc;
            for (int i_pc = 1; i_pc < 6; i_pc++) h_pc[i_pc] <= h_pc[i_pc-1];
            odd_pc <= ~odd_pc;
            if (res_pc) begin
                ov_pc <= 1'b1;
                oy_pc <= hi_pc ? 16'sh7FFF : lo_pc ? 16'sh8000 : rnd_pc[15:0];
                if (hi_pc || lo_pc) sat_pc <= 1'b1;
            end
        end
    end
endmodule

module fir_stage (
    input  logic               clk_pc,
    input  logic               clr_pc,
    input  logic               in_v_pc,
    input  logic signed [15:0] in_x_pc,
    output logic               ov_pc,
    output logic signed [15:0] oy_pc,
    output logic               sat_pc
);
    logic signed [15:0] h_pc [8];
    wire signed [31:0] acc_pc = 32'sd2   * in_x_pc + -32'sd6  * h_pc[0] + 32'sd16 * h_pc[1] + -32'sd48 * h_pc[2]
                           + 32'sd584 * h_pc[3] + -32'sd48 * h_pc[4] + 32'sd16 * h_pc[5] + -32'sd6  * h_pc[6] + 32'sd2 * h_pc[7];
    wire signed [31:0] rnd_pc = (acc_pc + 32'sd256) >>> 9;
    wire               hi_pc  = rnd_pc > 32'sd32767;
    wire               lo_pc  = rnd_pc < -32'sd32768;
    always_ff @(posedge clk_pc) begin
        ov_pc <= 1'b0;
        if (clr_pc) begin
            for (int i_pc = 0; i_pc < 8; i_pc++) h_pc[i_pc] <= '0;
            sat_pc <= 1'b0;
        end else if (in_v_pc) begin
            h_pc[0] <= in_x_pc;
            for (int i_pc = 1; i_pc < 8; i_pc++) h_pc[i_pc] <= h_pc[i_pc-1];
            ov_pc <= 1'b1;
            oy_pc <= hi_pc ? 16'sh7FFF : lo_pc ? 16'sh8000 : rnd_pc[15:0];
            if (hi_pc || lo_pc) sat_pc <= 1'b1;
        end
    end
endmodule

module dc_stage (
    input  logic               clk_pc,
    input  logic               clr_pc,
    input  logic               in_v_pc,
    input  logic signed [15:0] in_x_pc,
    output logic               ov_pc,
    output logic signed [15:0] oy_pc,
    output logic               sat_pc
);
    logic signed [15:0] xp_pc, yp_pc;
    wire signed [31:0] w_pc  = 32'(in_x_pc) - 32'(xp_pc) + 32'(yp_pc) - (32'(yp_pc) >>> 7);
    wire               hi_pc = w_pc > 32'sd32767;
    wire               lo_pc = w_pc < -32'sd32768;
    wire signed [15:0] y_pc  = hi_pc ? 16'sh7FFF : lo_pc ? 16'sh8000 : w_pc[15:0];
    always_ff @(posedge clk_pc) begin
        ov_pc <= 1'b0;
        if (clr_pc) begin
            xp_pc <= '0; yp_pc <= '0; sat_pc <= 1'b0;
        end else if (in_v_pc) begin
            xp_pc <= in_x_pc;
            yp_pc <= y_pc;
            ov_pc <= 1'b1;
            oy_pc <= y_pc;
            if (hi_pc || lo_pc) sat_pc <= 1'b1;
        end
    end
endmodule

module pdm_chain #(
    parameter int CLK_HALF = 16
) (
    input  logic        clk_pc,
    input  logic        rst_pc,
    output logic        m_clk_pc,
    input  logic        m_data_pc,
    output logic        m_lrsel_pc,
    output logic [15:0] led_pc,
    input  logic [6:0]  win_addr_pc,
    input  logic        win_wr_pc,
    input  logic        win_rd_pc,
    input  logic [31:0] win_wdata_pc,
    output logic [31:0] win_rdata_pc
);
    logic        run_pc, armed_pc, done_pc;
    logic [15:0] div_pc;
    logic        d1_pc, rise_d1_pc;
    logic [5:0]  idx_pc;
    logic [31:0] count_pc;
    logic signed [15:0] cap_pc [64];

    wire ctrl_wr_pc = win_wr_pc && win_addr_pc == 7'h00;
    wire start_pc   = ctrl_wr_pc && win_wdata_pc[0] && !run_pc;
    wire arm_ok_pc  = ctrl_wr_pc && win_wdata_pc[1] && !run_pc;
    wire rise_pc    = run_pc && !m_clk_pc && div_pc == 16'(CLK_HALF - 1);
    wire clr_pc     = rst_pc || start_pc;

    logic               cv_pc, sv_pc, h1v_pc, h2v_pc, fv_pc, dv_pc;
    logic signed [15:0] cy_pc, sy_pc, h1y_pc, h2y_pc, fy_pc, dy_pc;
    logic               s_sat_pc, h1_sat_pc, h2_sat_pc, f_sat_pc, d_sat_pc;
    wire                sat_pc = s_sat_pc | h1_sat_pc | h2_sat_pc | f_sat_pc | d_sat_pc;

    cic_stage   u_cic_pc (.clk_pc(clk_pc), .clr_pc(clr_pc), .in_v_pc(rise_d1_pc), .in_b_pc(d1_pc), .ov_pc(cv_pc), .oy_pc(cy_pc));
    scale_stage u_sc_pc  (.clk_pc(clk_pc), .clr_pc(clr_pc), .in_v_pc(cv_pc), .in_x_pc(cy_pc), .ov_pc(sv_pc), .oy_pc(sy_pc), .sat_pc(s_sat_pc));
    hb_stage    u_hb1_pc (.clk_pc(clk_pc), .clr_pc(clr_pc), .in_v_pc(sv_pc), .in_x_pc(sy_pc), .ov_pc(h1v_pc), .oy_pc(h1y_pc), .sat_pc(h1_sat_pc));
    hb_stage    u_hb2_pc (.clk_pc(clk_pc), .clr_pc(clr_pc), .in_v_pc(h1v_pc), .in_x_pc(h1y_pc), .ov_pc(h2v_pc), .oy_pc(h2y_pc), .sat_pc(h2_sat_pc));
    fir_stage   u_fir_pc (.clk_pc(clk_pc), .clr_pc(clr_pc), .in_v_pc(h2v_pc), .in_x_pc(h2y_pc), .ov_pc(fv_pc), .oy_pc(fy_pc), .sat_pc(f_sat_pc));
    dc_stage    u_dc_pc  (.clk_pc(clk_pc), .clr_pc(clr_pc), .in_v_pc(fv_pc), .in_x_pc(fy_pc), .ov_pc(dv_pc), .oy_pc(dy_pc), .sat_pc(d_sat_pc));

    assign m_lrsel_pc = 1'b0;
    assign led_pc = {13'd0, sat_pc, done_pc, run_pc};

    always_ff @(posedge clk_pc) begin
        if (rst_pc) begin
            run_pc <= 1'b0; div_pc <= '0; m_clk_pc <= 1'b0; d1_pc <= 1'b0; rise_d1_pc <= 1'b0;
            armed_pc <= 1'b0; done_pc <= 1'b0; idx_pc <= '0; count_pc <= '0;
        end else begin
            d1_pc <= m_data_pc;
            if (ctrl_wr_pc) run_pc <= win_wdata_pc[0];
            if (!run_pc || (ctrl_wr_pc && !win_wdata_pc[0])) begin
                div_pc <= '0; m_clk_pc <= 1'b0; rise_d1_pc <= 1'b0;
            end else begin
                rise_d1_pc <= rise_pc;
                if (div_pc == 16'(CLK_HALF - 1)) begin
                    div_pc   <= '0;
                    m_clk_pc <= ~m_clk_pc;
                end else begin
                    div_pc <= div_pc + 16'd1;
                end
            end
            if (start_pc) count_pc <= '0;
            else if (dv_pc) count_pc <= count_pc + 32'd1;
            if (start_pc && armed_pc && !done_pc) idx_pc <= '0;
            if (dv_pc && armed_pc) begin
                cap_pc[idx_pc] <= dy_pc;
                idx_pc      <= idx_pc + 6'd1;
                if (idx_pc == 6'd63) begin
                    done_pc  <= 1'b1;
                    armed_pc <= 1'b0;
                end
            end
            if (arm_ok_pc) begin
                armed_pc <= 1'b1;
                done_pc  <= 1'b0;
                idx_pc   <= '0;
            end
        end
    end

    always_ff @(posedge clk_pc) begin
        if (rst_pc) win_rdata_pc <= '0;
        else if (win_rd_pc) begin
            if (win_addr_pc[6]) win_rdata_pc <= done_pc ? 32'(cap_pc[win_addr_pc[5:0]]) : 32'd0;
            else case (win_addr_pc)
                7'h00:   win_rdata_pc <= {31'd0, run_pc};
                7'h01:   win_rdata_pc <= {29'd0, sat_pc, armed_pc, done_pc};
                7'h02:   win_rdata_pc <= count_pc;
                default: win_rdata_pc <= '0;
            endcase
        end
    end
endmodule
