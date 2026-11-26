// Register core of the async FIFO soak: map, control, snapshot, PRBS-31 writer (clk_c3), PRBS-31 checker (clk_gt).
/* verilator lint_off DECLFILENAME */
module fifo_core #(
    parameter int DEPTH = 512,
    parameter int DATA_WIDTH = 32,
    parameter int ADDR_WIDTH = 9,
    parameter int PRBS_SEED = 2147483647,
    parameter int DESIGN_ID = 546635777,
    parameter int SLOW_READ_DIV_CLOCKS = 8,
    parameter int SYNC_STAGES = 2
) (
    input  logic        clk_c3,
    input  logic        clk_gt,
    input  logic        rst_c3,      // active high, clk_c3 domain
    input  logic        rst_gt,      // active high, clk_gt domain
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    input  logic [31:0] build_word,
    output logic        sfp_tx_disable,
    output logic [1:0]  led
);
    localparam logic [30:0] SEED = 31'(PRBS_SEED);

    function automatic logic [30:0] adv32(input logic [30:0] s);
        logic [30:0] t;
        t = s;
        for (int i = 0; i < 32; i++) t = {t[29:0], t[30] ^ t[27]};
        return t;
    endfunction

    localparam logic [30:0] INIT = adv32(SEED);

    assign sfp_tx_disable = 1'b1;

    // ------------------------------------------------------------ clk_c3 domain
    logic        run, slow, inj_tog, clr_tog, snap_tog;
    logic [31:0] scratch;
    logic [30:0] cur_w;
    logic [31:0] words_w, ovf_cnt, stall_cnt, occ_max;
    logic [31:0] sh_ww, sh_ov, sh_st, sh_om;          // writer shadow at SNAPSHOT
    logic [31:0] v_ww, v_wr, v_de, v_ov, v_un, v_st, v_om;  // visible snapshot
    logic [2:0]  clr_cnt;
    logic        fifo_rst, ovf_seen;
    logic        full, wr_busy, fifo_ovf, rd_busy, fifo_unf, empty;
    logic [ADDR_WIDTH:0] wr_count;
    logic [31:0] rd_word;

    // reader -> writer status, and the handshake result
    logic        done_tog_s, rd_err_s;
    logic        hs_req;
    logic [95:0] hs_out;

    wire inj_pending = inj_tog ^ done_tog_s;
    wire w_go = run & ~full & ~wr_busy & ~fifo_rst;
    wire [ADDR_WIDTH:0] occ_now = full ? (ADDR_WIDTH + 1)'(DEPTH) :
                                  (wr_count > (ADDR_WIDTH + 1)'(DEPTH)) ? (ADDR_WIDTH + 1)'(DEPTH) : wr_count;

    always_ff @(posedge clk_c3) begin
        fifo_rst <= rst_c3 | (clr_cnt != 3'd0);
        if (rst_c3) begin
            run <= 1'b0; slow <= 1'b0; inj_tog <= 1'b0; clr_tog <= 1'b0; snap_tog <= 1'b0;
            scratch <= '0; cur_w <= INIT; words_w <= '0; ovf_cnt <= '0; stall_cnt <= '0; occ_max <= '0;
            sh_ww <= '0; sh_ov <= '0; sh_st <= '0; sh_om <= '0;
            v_ww <= '0; v_wr <= '0; v_de <= '0; v_ov <= '0; v_un <= '0; v_st <= '0; v_om <= '0;
            clr_cnt <= '0; ovf_seen <= 1'b0;
        end else begin
            if (clr_cnt != 3'd0) clr_cnt <= clr_cnt - 3'd1;
            // writer
            if (w_go) begin
                cur_w <= adv32(cur_w);
                words_w <= words_w + 32'd1;
            end
            if (run & full & ~wr_busy & ~fifo_rst) stall_cnt <= stall_cnt + 32'd1;
            if (fifo_ovf) begin ovf_cnt <= ovf_cnt + 32'd1; ovf_seen <= 1'b1; end
            if (!fifo_rst && !wr_busy && clr_cnt == 3'd0 && {22'd0, occ_now} > occ_max) occ_max <= {22'd0, occ_now};
            // register writes
            if (h_we) begin
                case (h_addr)
                    12'h008: scratch <= h_wdata;
                    12'h010: begin
                        run  <= h_wdata[0];
                        slow <= h_wdata[1];
                        if (h_wdata[3]) inj_tog <= ~inj_tog;
                        if (h_wdata[2] && !h_wdata[0]) begin
                            clr_tog <= ~clr_tog;
                            clr_cnt <= 3'd4;
                            cur_w <= INIT; words_w <= '0; ovf_cnt <= '0; stall_cnt <= '0; occ_max <= '0;
                            ovf_seen <= 1'b0;
                        end
                    end
                    12'h030: begin
                        snap_tog <= ~snap_tog;
                        sh_ww <= words_w; sh_ov <= ovf_cnt; sh_st <= stall_cnt; sh_om <= occ_max;
                    end
                    default: ;
                endcase
            end
            // snapshot result arrives: all seven registers change together
            if (hs_req) begin
                v_ww <= sh_ww; v_ov <= sh_ov; v_st <= sh_st; v_om <= sh_om;
                v_wr <= hs_out[95:64]; v_de <= hs_out[63:32]; v_un <= hs_out[31:0];
            end
        end
    end

    // register read
    always_ff @(posedge clk_c3) begin
        if (rst_c3) h_rdata <= '0;
        else if (h_re) begin
            case (h_addr)
                12'h000: h_rdata <= 32'(DESIGN_ID);
                12'h004: h_rdata <= build_word;
                12'h008: h_rdata <= scratch;
                12'h010: h_rdata <= {28'd0, inj_pending, 1'b0, slow, run};
                12'h014: h_rdata <= v_ww;
                12'h018: h_rdata <= v_wr;
                12'h01C: h_rdata <= v_de;
                12'h020: h_rdata <= v_ov;
                12'h024: h_rdata <= v_un;
                12'h028: h_rdata <= v_st;
                12'h02C: h_rdata <= v_om;
                default: h_rdata <= '0;
            endcase
        end
    end

    assign led = {rd_err_s | ovf_seen, run};

    // ------------------------------------------------------------ crossings
    logic slow_s, snap_tog_s, clr_tog_s, inj_tog_s;
    xpm_cdc_array_single #(.DEST_SYNC_FF(SYNC_STAGES), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                           .SRC_INPUT_REG(1), .WIDTH(4)) u_ctl_cdc (
        .src_clk(clk_c3), .src_in({snap_tog, clr_tog, inj_tog, slow}),
        .dest_clk(clk_gt), .dest_out({snap_tog_s, clr_tog_s, inj_tog_s, slow_s}));

    logic done_tog, rd_err;
    xpm_cdc_array_single #(.DEST_SYNC_FF(SYNC_STAGES), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                           .SRC_INPUT_REG(1), .WIDTH(2)) u_sts_cdc (
        .src_clk(clk_gt), .src_in({done_tog, rd_err}),
        .dest_clk(clk_c3), .dest_out({done_tog_s, rd_err_s}));

    // ------------------------------------------------------------ FIFO
    logic rd_en;
    async_fifo #(.DEPTH(DEPTH), .DATA_WIDTH(DATA_WIDTH), .ADDR_WIDTH(ADDR_WIDTH), .SYNC_STAGES(SYNC_STAGES)) u_fifo (
        .rst(fifo_rst), .wr_clk(clk_c3), .wr_en(w_go), .din({1'b0, cur_w}), .full(full),
        .wr_count(wr_count), .wr_busy(wr_busy), .overflow(fifo_ovf),
        .rd_clk(clk_gt), .rd_en(rd_en), .dout(rd_word), .empty(empty), .rd_busy(rd_busy),
        .underflow(fifo_unf));

    // ------------------------------------------------------------ clk_gt domain
    logic [30:0] exp_r;
    logic [31:0] words_r, data_errs, unf_cnt;
    logic [3:0]  cool;
    logic [5:0]  hold_cnt;
    logic        hold, clr_seen, snap_seen, hs_send, hs_rcv;
    logic [95:0] hs_data;

    wire inj_arm = inj_tog_s ^ done_tog;
    wire clr_diff = clr_tog_s ^ clr_seen;
    wire snap_diff = snap_tog_s ^ snap_seen;
    assign rd_en = ~empty & ~rd_busy & ~hold & (cool == 4'd0);
    wire [31:0] chk_word = inj_arm ? (rd_word ^ 32'd1) : rd_word;
    wire mismatch = (chk_word != {1'b0, exp_r});

    always_ff @(posedge clk_gt) begin
        if (rst_gt) begin
            exp_r <= INIT; words_r <= '0; data_errs <= '0; unf_cnt <= '0; cool <= '0;
            hold_cnt <= '0; hold <= 1'b0; clr_seen <= 1'b0; snap_seen <= 1'b0; done_tog <= 1'b0;
            hs_send <= 1'b0; hs_data <= '0; rd_err <= 1'b0;
        end else begin
            if (cool != 4'd0) cool <= cool - 4'd1;
            if (rd_en) begin
                exp_r <= adv32(exp_r);
                words_r <= words_r + 32'd1;
                if (slow_s) cool <= 4'(SLOW_READ_DIV_CLOCKS - 1);
                if (inj_arm) done_tog <= inj_tog_s;
                if (mismatch) begin data_errs <= data_errs + 32'd1; rd_err <= 1'b1; end
            end
            if (fifo_unf) begin unf_cnt <= unf_cnt + 32'd1; rd_err <= 1'b1; end
            // CLEAR: restart sequence and counters, wait out the FIFO reset
            if (hold) begin
                if (hold_cnt != 6'd0) hold_cnt <= hold_cnt - 6'd1;
                else if (!rd_busy) hold <= 1'b0;
            end
            if (clr_diff) begin
                clr_seen <= clr_tog_s;
                exp_r <= INIT; words_r <= '0; data_errs <= '0; unf_cnt <= '0; rd_err <= 1'b0;
                cool <= '0; done_tog <= inj_tog_s;
                hold <= 1'b1; hold_cnt <= 6'd63;
            end
            // SNAPSHOT: latch reader counters and hand them over
            if (snap_diff && !clr_diff && !hs_send && !hs_rcv) begin
                snap_seen <= snap_tog_s;
                hs_data <= {words_r, data_errs, unf_cnt};
                hs_send <= 1'b1;
            end
            if (hs_rcv) hs_send <= 1'b0;
        end
    end

    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(SYNC_STAGES), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(SYNC_STAGES), .WIDTH(96)) u_snap_cdc (
        .src_clk(clk_gt), .src_in(hs_data), .src_send(hs_send), .src_rcv(hs_rcv),
        .dest_clk(clk_c3), .dest_out(hs_out), .dest_req(hs_req), .dest_ack(1'b0));
endmodule
