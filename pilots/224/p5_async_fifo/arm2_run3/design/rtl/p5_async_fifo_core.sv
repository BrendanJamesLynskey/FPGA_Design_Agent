// Register core: clk_25 writer + register port, gt_refclk reader/checker, async FIFO between them.
/* verilator lint_off DECLFILENAME */
module fifo_core #(
    parameter logic [31:0] DESIGN_ID = 32'd546635777,
    parameter logic [30:0] PRBS_SEED = 31'h7FFFFFFF,
    parameter int          SLOW_READ_DIV_CYCLES = 8
) (
    input  logic        clk_25,
    input  logic        gt_refclk,
    input  logic        rst,             // active high, synchronous to clk_25
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    assign sfp_tx_disable = 1'b1;

    // ------------------------------------------------------------------ reset into the reader domain
    logic rst_ref;
    reset_gen u_rg (.dest_clk(gt_refclk), .rst_in(rst), .rst_out(rst_ref));

    // ------------------------------------------------------------------ BUILD word
    logic [31:0] build_word;
    /* verilator lint_off PINCONNECTEMPTY */
    USR_ACCESSE2 u_usr (.CFGCLK(), .DATA(build_word), .DATAVALID());
    /* verilator lint_on PINCONNECTEMPTY */

    // ================================================================== clk_25 domain
    logic [31:0] scratch;
    logic        run, slow;
    logic        inj_t, clr_t, snap_t;
    logic [2:0]  hold;
    logic [31:0] cnt_ww, cnt_ovf, cnt_stall, cnt_occ;
    logic [31:0] snap_r [7];
    logic [30:0] wseed;

    wire wr_ctrl   = h_we && (h_addr == 12'h010);
    wire clear_cmd = wr_ctrl && h_wdata[2] && !run;

    // FIFO
    logic        w_full, w_overflow, r_empty, r_underflow, r_clr, r_en;
    logic [9:0]  w_fill;
    logic [31:0] w_word, r_data;
    logic [30:0] wseed_n;
    wire         w_en = run && (hold == 3'd0);
    wire         do_w = w_en && !w_full;
    wire [9:0]   new_fill = w_fill + {9'd0, do_w};

    prbs31_word u_wprbs (.state(wseed), .next_state(wseed_n), .word(w_word));

    async_fifo u_fifo (
        .wclk(clk_25), .w_clr(rst || clear_cmd), .w_en(do_w), .w_data(w_word),
        .w_full(w_full), .w_fill(w_fill), .w_overflow(w_overflow),
        .rclk(gt_refclk), .r_clr(r_clr), .r_en(r_en), .r_data(r_data),
        .r_empty(r_empty), .r_underflow(r_underflow));

    // reader -> writer: snapshot handshake and error flag
    logic        snap_req, snap_dest_req;
    logic [95:0] snap_dest_out;
    logic        err_any_gt, err_any_s;

    always_ff @(posedge clk_25) begin
        if (hold != 3'd0) hold <= hold - 3'd1;
        if (rst) begin
            run <= 1'b0; slow <= 1'b0; scratch <= '0;
            inj_t <= 1'b0; clr_t <= 1'b0; snap_t <= 1'b0; hold <= '0;
            cnt_ww <= '0; cnt_ovf <= '0; cnt_stall <= '0; cnt_occ <= '0;
            wseed <= PRBS_SEED;
            for (int i = 0; i < 7; i++) snap_r[i] <= '0;
        end else begin
            if (h_we && h_addr == 12'h008) scratch <= h_wdata;
            if (wr_ctrl) begin
                run  <= h_wdata[0];
                slow <= h_wdata[1];
                if (h_wdata[3]) inj_t <= ~inj_t;
            end
            if (h_we && h_addr == 12'h030) snap_t <= ~snap_t;
            if (clear_cmd) begin
                clr_t <= ~clr_t;
                hold  <= 3'd6;
                cnt_ww <= '0; cnt_ovf <= '0; cnt_stall <= '0; cnt_occ <= '0;
                wseed <= PRBS_SEED;
            end else begin
                if (do_w) begin
                    cnt_ww <= cnt_ww + 32'd1;
                    wseed  <= wseed_n;
                end
                if (w_overflow)       cnt_ovf   <= cnt_ovf + 32'd1;
                if (w_en && w_full)   cnt_stall <= cnt_stall + 32'd1;
                if (hold == 3'd0 && {22'd0, new_fill} > cnt_occ) cnt_occ <= {22'd0, new_fill};
            end
            if (snap_dest_req) begin
                snap_r[0] <= cnt_ww;
                snap_r[1] <= snap_dest_out[95:64];
                snap_r[2] <= snap_dest_out[63:32];
                snap_r[3] <= cnt_ovf;
                snap_r[4] <= snap_dest_out[31:0];
                snap_r[5] <= cnt_stall;
                snap_r[6] <= cnt_occ;
            end
        end
    end

    // register read port: value registered on h_re and held
    always_ff @(posedge clk_25) begin
        if (rst) h_rdata <= '0;
        else if (h_re) begin
            case (h_addr)
                12'h000: h_rdata <= DESIGN_ID;
                12'h004: h_rdata <= build_word;
                12'h008: h_rdata <= scratch;
                12'h010: h_rdata <= {30'd0, slow, run};
                12'h014: h_rdata <= snap_r[0];
                12'h018: h_rdata <= snap_r[1];
                12'h01C: h_rdata <= snap_r[2];
                12'h020: h_rdata <= snap_r[3];
                12'h024: h_rdata <= snap_r[4];
                12'h028: h_rdata <= snap_r[5];
                12'h02C: h_rdata <= snap_r[6];
                default: h_rdata <= '0;
            endcase
        end
    end

    assign led = {err_any_s | (cnt_ovf != 32'd0), run};

    // ================================================================== clk_25 -> gt_refclk control
    logic [3:0] ctrl_s;
    logic [2:0] tq;
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0), .WIDTH(4)) u_ctrl (
        .src_clk(clk_25), .src_in({snap_t, clr_t, inj_t, slow}), .dest_clk(gt_refclk), .dest_out(ctrl_s));

    // ================================================================== gt_refclk domain
    wire inj_ev  = ctrl_s[1] != tq[0];
    wire clr_ev  = ctrl_s[2] != tq[1];
    wire snap_ev = ctrl_s[3] != tq[2];
    wire slow_s  = ctrl_s[0];

    logic [3:0]  rd_hold;
    logic [2:0]  slow_cnt;
    logic        rd_valid, inj_pend, snap_pend, snd, snap_rcv;
    logic [30:0] rseed, rseed_n;
    logic [31:0] exp_word, got_word;
    logic [31:0] cnt_wr, cnt_err, cnt_unf;
    logic [95:0] snap_data;

    always_ff @(posedge gt_refclk) tq <= ctrl_s[3:1];

    wire rd_clear = rst_ref || clr_ev;
    assign r_clr  = rd_clear;
    assign r_en   = !r_empty && (rd_hold == 4'd0) && (slow_cnt == 3'd0) && !rd_clear;

    prbs31_word u_rprbs (.state(rseed), .next_state(rseed_n), .word(exp_word));
    assign got_word = r_data ^ {31'd0, inj_pend};

    always_ff @(posedge gt_refclk) begin
        if (rst_ref) begin
            rd_hold <= 4'd8; slow_cnt <= '0; rd_valid <= 1'b0; inj_pend <= 1'b0;
            snap_pend <= 1'b0; snd <= 1'b0;
            cnt_wr <= '0; cnt_err <= '0; cnt_unf <= '0; rseed <= PRBS_SEED;
            err_any_gt <= 1'b0;
        end else begin
            rd_valid <= r_en;
            if (inj_ev) inj_pend <= 1'b1;
            else if (rd_valid) inj_pend <= 1'b0;

            if (clr_ev) begin
                rd_hold <= 4'd8; slow_cnt <= '0;
                cnt_wr <= '0; cnt_err <= '0; cnt_unf <= '0; rseed <= PRBS_SEED;
            end else begin
                if (rd_hold != 4'd0) rd_hold <= rd_hold - 4'd1;
                if (r_en && slow_s)  slow_cnt <= 3'(SLOW_READ_DIV_CYCLES - 1);
                else if (slow_cnt != 3'd0) slow_cnt <= slow_cnt - 3'd1;
                if (rd_valid) begin
                    cnt_wr <= cnt_wr + 32'd1;
                    rseed  <= rseed_n;
                    if (got_word != exp_word) cnt_err <= cnt_err + 32'd1;
                end
                if (r_underflow) cnt_unf <= cnt_unf + 32'd1;
            end
            err_any_gt <= (cnt_err != 32'd0) || (cnt_unf != 32'd0);

            // snapshot of the reader counters, sent through the handshake
            if (snap_ev) snap_pend <= 1'b1;
            if (snd) begin
                if (snap_rcv) snd <= 1'b0;
            end else if (snap_pend && !snap_rcv) begin
                snap_data <= {cnt_wr, cnt_err, cnt_unf};
                snd <= 1'b1;
                if (!snap_ev) snap_pend <= 1'b0;
            end
        end
    end

    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(2), .WIDTH(96)) u_snap (
        .src_clk(gt_refclk), .src_in(snap_data), .src_send(snd), .src_rcv(snap_rcv),
        .dest_clk(clk_25), .dest_req(snap_dest_req), .dest_ack(1'b0), .dest_out(snap_dest_out));

    assign snap_req = snd;

    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0), .WIDTH(1)) u_err (
        .src_clk(gt_refclk), .src_in(err_any_gt), .dest_clk(clk_25), .dest_out(err_any_s));

    /* verilator lint_off UNUSEDSIGNAL */
    logic unused_ok;
    assign unused_ok = snap_req;
    /* verilator lint_on UNUSEDSIGNAL */
endmodule
