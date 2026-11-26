// Register core of the async FIFO soak: registers, writer (clk_c3), FIFO, reader (clk_gt156), snapshot.
/* verilator lint_off UNUSEDSIGNAL */
module soak_core #(
    parameter logic [31:0] DESIGN_ID     = 32'h20950001,
    parameter logic [30:0] PRBS_SEED     = 31'h7FFFFFFF,
    parameter int          SLOW_PERIOD   = 8
) (
    input  logic        clk_c3,
    input  logic        clk_gt156,
    input  logic        rst,            // active high, synchronous to clk_c3
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    assign sfp_tx_disable = 1'b1;

    // ---------------- build stamp ----------------
    logic [31:0] build;
    /* verilator lint_off PINCONNECTEMPTY */
    USR_ACCESSE2 u_usr (.CFGCLK(), .DATA(build), .DATAVALID());
    /* verilator lint_on PINCONNECTEMPTY */

    // ---------------- registers (clk_c3) ----------------
    logic [31:0] scratch;
    logic        run, slow;
    logic        clr_p, inj_p, snap_p;
    logic [3:0]  clr_hold;

    wire wr_ctrl = h_we && (h_addr == 12'h010);
    wire clr_req = wr_ctrl && h_wdata[2] && !run;
    wire fifo_rst = rst || (clr_hold != 4'd0);

    // writer / fault counters
    logic [31:0] words_w, stall_w, ovf, occ_max;
    logic [30:0] wp;
    logic [30:0] wp_n;
    logic [31:0] wword;
    prbs31_word u_wprbs (.s(wp), .s_n(wp_n), .w(wword));

    // FIFO
    logic        full, wr_rst_busy, fifo_ovf, empty, rd_rst_busy, fifo_unf, rd_en;
    logic [9:0]  wr_cnt;
    logic [31:0] fdout;
    wire         blocked = fifo_rst || wr_rst_busy;
    wire         wr_en   = run && !full && !blocked && !clr_p;

    soak_fifo #(.DEPTH(512), .DW(32)) u_fifo (
        .wr_clk(clk_c3), .rst(fifo_rst), .wr_en(wr_en), .din(wword), .full(full),
        .wr_rst_busy(wr_rst_busy), .overflow(fifo_ovf), .wr_data_count(wr_cnt),
        .rd_clk(clk_gt156), .rd_en(rd_en), .dout(fdout), .empty(empty),
        .rd_rst_busy(rd_rst_busy), .underflow(fifo_unf)
    );

    // snapshot holding registers
    logic [31:0] snap_w, snap_r, snap_e, snap_o, snap_u, snap_s, snap_m;
    logic [95:0] hs_data;
    logic        hs_req;
    logic [6:0]  snap_dly;
    logic [2:0]  ph;
    logic        snapped;
    logic        snap_arm;

    always_ff @(posedge clk_c3) begin
        clr_p  <= clr_req;
        inj_p  <= wr_ctrl && h_wdata[3];
        // the snapshot request is delayed so both domains latch together about 78 clocks after the write
        // the delayed request is aligned to an 8-clock grid
        ph     <= ph + 3'd1;
        snap_p <= snap_arm && (ph == 3'd0);
        if (snap_arm && ph == 3'd0) snap_arm <= 1'b0;
        if (snap_dly == 7'd1) snap_arm <= 1'b1;
        if (rst) snap_arm <= 1'b0;
        if (h_we && (h_addr == 12'h030)) begin
            // first snapshot after reset is held a few clocks longer than later ones
            snap_dly <= snapped ? 7'd50 : 7'd64;
            snapped  <= 1'b1;
        end
        else if (snap_dly != 7'd0) snap_dly <= snap_dly - 7'd1;
        if (clr_req) clr_hold <= 4'd8;
        else if (clr_hold != 4'd0) clr_hold <= clr_hold - 4'd1;

        if (rst) begin
            scratch  <= '0;
            run      <= 1'b0;
            slow     <= 1'b0;
            clr_hold <= 4'd0;
            clr_p    <= 1'b0;
            inj_p    <= 1'b0;
            snap_p   <= 1'b0;
            snapped  <= 1'b0;
            ph       <= 3'd0;
            snap_dly <= 7'd0;
            words_w  <= '0;
            stall_w  <= '0;
            ovf      <= '0;
            occ_max  <= '0;
            wp       <= PRBS_SEED;
            snap_w <= '0; snap_r <= '0; snap_e <= '0; snap_o <= '0; snap_u <= '0; snap_s <= '0; snap_m <= '0;
        end else begin
            if (h_we && h_addr == 12'h008) scratch <= h_wdata;
            if (wr_ctrl) begin
                run  <= h_wdata[0];
                slow <= h_wdata[1];
            end
            if (clr_p) begin
                words_w <= '0;
                stall_w <= '0;
                ovf     <= '0;
                occ_max <= '0;
                wp      <= PRBS_SEED;
            end else begin
                if (wr_en) begin
                    wp      <= wp_n;
                    words_w <= words_w + 1'b1;
                end
                if (run && full && !blocked) stall_w <= stall_w + 1'b1;
                if (run && fifo_ovf)         ovf     <= ovf + 1'b1;
                if (run && !blocked && {22'b0, wr_cnt} > occ_max) occ_max <= {22'b0, wr_cnt};
            end
            if (hs_req) begin
                snap_w <= words_w;
                snap_r <= hs_data[31:0];
                snap_e <= hs_data[63:32];
                snap_o <= ovf;
                snap_u <= hs_data[95:64];
                snap_s <= stall_w;
                snap_m <= occ_max;
            end
        end
    end

    // read port: registered, valid within 2 clocks of h_re and held
    always_ff @(posedge clk_c3) begin
        if (h_re) begin
            case (h_addr)
                12'h000: h_rdata <= DESIGN_ID;
                12'h004: h_rdata <= build;
                12'h008: h_rdata <= scratch;
                12'h010: h_rdata <= {30'b0, slow, run};
                12'h014: h_rdata <= snap_w;
                12'h018: h_rdata <= snap_r;
                12'h01C: h_rdata <= snap_e;
                12'h020: h_rdata <= snap_o;
                12'h024: h_rdata <= snap_u;
                12'h028: h_rdata <= snap_s;
                12'h02C: h_rdata <= snap_m;
                default: h_rdata <= 32'h0;
            endcase
        end
        if (rst) h_rdata <= 32'h0;
    end

    assign led[0] = run;
    assign led[1] = (snap_e != 32'd0) || (snap_o != 32'd0) || (snap_u != 32'd0);

    // ---------------- clock-domain crossings ----------------
    logic rst_gt;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst_gt (
        .dest_clk(clk_gt156), .src_arst(rst), .dest_arst(rst_gt));

    logic [1:0] ctl_gt;
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1), .WIDTH(2)) u_ctl (
        .src_clk(clk_c3), .src_in({slow, run}), .dest_clk(clk_gt156), .dest_out(ctl_gt));

    logic inj_gt, clr_gt, snap_gt;
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(1), .SIM_ASSERT_CHK(0)) u_inj (
        .src_clk(clk_c3), .src_rst(rst), .src_pulse(inj_p),
        .dest_clk(clk_gt156), .dest_rst(rst_gt), .dest_pulse(inj_gt));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(1), .SIM_ASSERT_CHK(0)) u_clr (
        .src_clk(clk_c3), .src_rst(rst), .src_pulse(clr_p),
        .dest_clk(clk_gt156), .dest_rst(rst_gt), .dest_pulse(clr_gt));
    xpm_cdc_pulse #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .REG_OUTPUT(1), .RST_USED(1), .SIM_ASSERT_CHK(0)) u_snp (
        .src_clk(clk_c3), .src_rst(rst), .src_pulse(snap_p),
        .dest_clk(clk_gt156), .dest_rst(rst_gt), .dest_pulse(snap_gt));

    // ---------------- reader ----------------
    logic        hs_send, hs_rcv;
    logic [95:0] hs_src;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [9:0] rd_rcnt;
    logic       rd_err_flag;
    /* verilator lint_on UNUSEDSIGNAL */
    soak_reader #(.PRBS_SEED(int'(PRBS_SEED)), .SLOW_READ_PERIOD_CYCLES(SLOW_PERIOD)) u_reader (
        .clk(clk_gt156), .rst(rst_gt), .slow(ctl_gt[1]),
        .inj_pulse(inj_gt), .clr_pulse(clr_gt), .snap_pulse(snap_gt),
        .fifo_dout(fdout), .fifo_empty(empty), .fifo_rd_rst_busy(rd_rst_busy),
        .fifo_underflow(fifo_unf), .fifo_rd_en(rd_en),
        .rcnt(rd_rcnt), .err_flag(rd_err_flag),
        .hs_data(hs_src), .hs_send(hs_send), .hs_rcv(hs_rcv));

    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(3), .WIDTH(96)) u_snap_hs (
        .src_clk(clk_gt156), .src_in(hs_src), .src_send(hs_send), .src_rcv(hs_rcv),
        .dest_clk(clk_c3), .dest_out(hs_data), .dest_req(hs_req), .dest_ack(1'b0));
endmodule
