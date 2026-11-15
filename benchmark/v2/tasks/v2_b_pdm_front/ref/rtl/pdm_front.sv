// pdm_front.sv: PDM microphone clock, sampler, 32-bit packer, 4-word queue and stuck detector (v2_b_pdm_front).
module pdm_front #(
    parameter int CLK_HALF = 16,
    parameter int STUCK_N  = 40
) (
    input  logic        clk_pf,
    input  logic        rst_pf,
    output logic        m_clk_pf,
    input  logic        m_data_pf,
    output logic        m_lrsel_pf,
    output logic [15:0] led_pf,
    input  logic [6:0]  win_addr_pf,
    input  logic        win_wr_pf,
    input  logic        win_rd_pf,
    input  logic [31:0] win_wdata_pf,
    output logic [31:0] win_rdata_pf
);
    logic        run_pf;
    logic [15:0] div_pf;
    logic        d1_pf, rise_d1_pf;                        // M_DATA register and the delayed rise strobe
    logic [31:0] sh_pf;
    logic [4:0]  bcnt_pf;
    logic [31:0] q_pf [4];
    logic [1:0]  rp_pf, wp_pf;
    logic [2:0]  cnt_pf;
    logic        ovr_pf, hi_pf, lo_pf;
    logic [31:0] words_pf;
    logic [7:0]  runlen_pf;
    logic        last_pf;

    wire ctrl_wr_pf = win_wr_pf && win_addr_pf == 7'h00;
    wire clr_pf     = ctrl_wr_pf && win_wdata_pf[1];
    wire pop_pf     = win_wr_pf && win_addr_pf == 7'h03 && cnt_pf != 3'd0;
    wire rise_pf    = run_pf && !m_clk_pf && div_pf == 16'(CLK_HALF - 1);
    wire take_pf    = rise_d1_pf;
    wire [31:0] word_pf = {d1_pf, sh_pf[31:1]};
    wire        done_pf = take_pf && bcnt_pf == 5'd31;
    wire [7:0]  rl_pf   = (runlen_pf != 8'd0 && d1_pf == last_pf) ? ((runlen_pf == 8'd255) ? runlen_pf : runlen_pf + 8'd1) : 8'd1;

    assign m_lrsel_pf = 1'b0;
    assign led_pf = {14'd0, hi_pf | lo_pf, run_pf};

    always_ff @(posedge clk_pf) begin
        if (rst_pf) begin
            run_pf <= 1'b0; div_pf <= '0; m_clk_pf <= 1'b0; d1_pf <= 1'b0; rise_d1_pf <= 1'b0;
            sh_pf <= '0; bcnt_pf <= '0; rp_pf <= '0; wp_pf <= '0; cnt_pf <= '0; ovr_pf <= 1'b0; hi_pf <= 1'b0; lo_pf <= 1'b0;
            words_pf <= '0; runlen_pf <= '0; last_pf <= 1'b0;
        end else begin
            d1_pf <= m_data_pf;
            if (ctrl_wr_pf) run_pf <= win_wdata_pf[0];
            if (!run_pf || (ctrl_wr_pf && !win_wdata_pf[0])) begin
                div_pf <= '0; m_clk_pf <= 1'b0; rise_d1_pf <= 1'b0; bcnt_pf <= '0; runlen_pf <= '0;
            end else begin
                rise_d1_pf <= rise_pf;
                if (div_pf == 16'(CLK_HALF - 1)) begin
                    div_pf   <= '0;
                    m_clk_pf <= ~m_clk_pf;
                end else begin
                    div_pf <= div_pf + 16'd1;
                end
                if (take_pf) begin
                    sh_pf      <= word_pf;
                    bcnt_pf    <= bcnt_pf + 5'd1;
                    runlen_pf  <= rl_pf;
                    last_pf    <= d1_pf;
                    if (rl_pf >= 8'(STUCK_N)) begin
                        if (d1_pf) hi_pf <= 1'b1; else lo_pf <= 1'b1;
                    end
                    if (done_pf) begin
                        words_pf <= words_pf + 32'd1;
                        if (cnt_pf == 3'd4) ovr_pf <= 1'b1;
                        else if (cnt_pf != 3'd4) begin
                            q_pf[wp_pf] <= word_pf;
                            wp_pf    <= wp_pf + 2'd1;
                        end
                    end
                end
            end
            if (done_pf && cnt_pf != 3'd4) begin
                if (!pop_pf) cnt_pf <= cnt_pf + 3'd1;
            end else if (pop_pf) begin
                cnt_pf <= cnt_pf - 3'd1;
            end
            if (pop_pf) rp_pf <= rp_pf + 2'd1;
            if (clr_pf) begin
                rp_pf <= '0; wp_pf <= '0; cnt_pf <= '0; ovr_pf <= 1'b0; hi_pf <= 1'b0; lo_pf <= 1'b0;
            end
        end
    end

    always_ff @(posedge clk_pf) begin
        if (rst_pf) win_rdata_pf <= '0;
        else if (win_rd_pf) begin
            case (win_addr_pf)
                7'h00:   win_rdata_pf <= {31'd0, run_pf};
                7'h01:   win_rdata_pf <= {25'd0, lo_pf, hi_pf, ovr_pf, 1'b0, cnt_pf};
                7'h02:   win_rdata_pf <= (cnt_pf != 3'd0) ? q_pf[rp_pf] : 32'd0;
                7'h04:   win_rdata_pf <= words_pf;
                default: win_rdata_pf <= '0;
            endcase
        end
    end
endmodule
