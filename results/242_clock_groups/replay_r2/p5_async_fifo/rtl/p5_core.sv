// p5_core: register file, CTRL/CLEAR/INJECT/SNAPSHOT control, async FIFO soak datapath, LED and pin tie-offs.
// clk is the 25 MHz writer / register-bus clock, gt_clk the 156.25 MHz reader clock (asynchronous to clk).
// Every crossing goes through an XPM CDC primitive.
module p5_core #(
    parameter int          DATA_WIDTH           = 32,
    parameter int          FIFO_DEPTH           = 512,
    parameter logic [30:0] PRBS_SEED            = 31'h7FFFFFFF,
    parameter logic [31:0] DESIGN_ID            = 32'h20950001,
    parameter int          SLOW_READ_DIV_CYCLES = 8
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        gt_clk,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    localparam int CW = $clog2(FIFO_DEPTH) + 1;

    if (DATA_WIDTH != 32) begin : g_width_check
        $error("p5_core: DATA_WIDTH must be 32");
    end

    assign sfp_tx_disable = 1'b1;

    // ------------------------------------------------------------------ build stamp
    logic [31:0] build_word;
    /* verilator lint_off UNUSEDSIGNAL */
    logic        usr_cfgclk;
    logic        usr_valid;
    /* verilator lint_on UNUSEDSIGNAL */
    USR_ACCESSE2 u_usr (.CFGCLK(usr_cfgclk), .DATA(build_word), .DATAVALID(usr_valid));

    // ------------------------------------------------------------------ reset into gt_clk
    logic rst_rd;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst_sync_rd (
        .dest_arst(rst_rd), .dest_clk(gt_clk), .src_arst(rst));

    // ------------------------------------------------------------------ control registers (clk domain)
    typedef enum logic [1:0] {CS_IDLE, CS_RST, CS_WAIT, CS_TAIL} cs_t;
    cs_t         cs;
    logic [4:0]  cs_cnt;
    logic        fifo_clr;
    logic        clr_now;       // one-clock pulse: writer side zeroes
    logic        clr_src;       // one-clock pulse towards the reader
    logic        inj_src;       // one-clock pulse towards the reader
    logic        inj_hold;      // INJECT written while a CLEAR sequence runs: sent after it
    logic [31:0] scratch;
    logic        run;
    logic        slow;

    logic        wr_rst_busy;
    logic        rd_rst_busy;

    wire ctrl_we = h_we && (h_addr == 12'h010);
    wire snap_we = h_we && (h_addr == 12'h030);

    always_ff @(posedge clk) begin
        if (rst) begin
            scratch  <= 32'd0;
            run      <= 1'b0;
            slow     <= 1'b0;
            cs       <= CS_IDLE;
            cs_cnt   <= 5'd0;
            fifo_clr <= 1'b0;
            clr_now  <= 1'b0;
            clr_src  <= 1'b0;
            inj_src  <= 1'b0;
            inj_hold <= 1'b0;
        end else begin
            clr_now <= 1'b0;
            clr_src <= 1'b0;
            inj_src <= 1'b0;
            if (h_we && h_addr == 12'h008) scratch <= h_wdata;
            if (ctrl_we) begin
                run     <= h_wdata[0];
                slow    <= h_wdata[1];
                if (h_wdata[3]) begin
                    if (cs == CS_IDLE && !(h_wdata[2] && !run)) inj_src <= 1'b1;
                    else                                         inj_hold <= 1'b1;
                end
                if (h_wdata[2] && !run && cs == CS_IDLE) begin
                    cs       <= CS_RST;
                    cs_cnt   <= 5'd0;
                    fifo_clr <= 1'b1;
                    clr_now  <= 1'b1;
                end
            end
            case (cs)
                CS_RST: begin
                    cs_cnt <= cs_cnt + 5'd1;
                    if (cs_cnt == 5'd7) begin
                        fifo_clr <= 1'b0;
                        cs       <= CS_WAIT;
                        cs_cnt   <= 5'd0;
                    end
                end
                CS_WAIT: begin
                    if (cs_cnt != 5'd31) cs_cnt <= cs_cnt + 5'd1;
                    if (cs_cnt >= 5'd2 && !wr_rst_busy) begin
                        clr_src <= 1'b1;
                        cs      <= CS_TAIL;
                        cs_cnt  <= 5'd0;
                    end
                end
                CS_TAIL: begin
                    cs_cnt <= cs_cnt + 5'd1;
                    if (cs_cnt == 5'd7) begin
                        cs <= CS_IDLE;
                        if (inj_hold || (ctrl_we && h_wdata[3])) begin
                            inj_src  <= 1'b1;
                            inj_hold <= 1'b0;
                        end
                    end
                end
                default: begin
                end
            endcase
        end
    end

    // ------------------------------------------------------------------ crossings clk -> gt_clk
    logic slow_gt;
    logic inj_gt;
    logic clr_gt;
    xpm_cdc_array_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(1), .WIDTH(1)) u_cdc_slow (
        .src_clk(clk), .src_in(slow), .dest_clk(gt_clk), .dest_out(slow_gt));
    xpm_cdc_pulse #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_cdc_inject (
        .src_clk(clk), .src_pulse(inj_src), .src_rst(1'b0), .dest_clk(gt_clk), .dest_rst(1'b0), .dest_pulse(inj_gt));
    xpm_cdc_pulse #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .REG_OUTPUT(0), .RST_USED(0), .SIM_ASSERT_CHK(0)) u_cdc_clear (
        .src_clk(clk), .src_pulse(clr_src), .src_rst(1'b0), .dest_clk(gt_clk), .dest_rst(1'b0), .dest_pulse(clr_gt));

    // ------------------------------------------------------------------ async FIFO
    logic          fifo_wr_en;
    logic [31:0]   fifo_din;
    logic          fifo_full;
    logic          fifo_ovf;
    logic [CW-1:0] fifo_wcnt;
    logic          fifo_rd_en;
    logic [31:0]   fifo_dout;
    logic          fifo_empty;
    logic          fifo_unf;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [CW-1:0] fifo_rcnt;
    logic          fifo_prog_full;
    logic          fifo_prog_empty;
    logic          fifo_almost_full;
    logic          fifo_almost_empty;
    logic          fifo_wr_ack;
    logic          fifo_data_valid;
    logic          fifo_dbiterr;
    logic          fifo_sbiterr;
    /* verilator lint_on UNUSEDSIGNAL */

    // distributed (LUTRAM) memory: the flow's FIFO-memory max-delay exception finds RAM32M/RAM64M clock pins (WCLK);
    // the UltraScale+ RAMB36E2 clock pins (CLKARDCLK/CLKBWRCLK) are not matched by it and the build fails.
    xpm_fifo_async #(
        .CDC_SYNC_STAGES(2), .DOUT_RESET_VALUE("0"), .ECC_MODE("no_ecc"), .FIFO_MEMORY_TYPE("distributed"),
        .FIFO_READ_LATENCY(1), .FIFO_WRITE_DEPTH(FIFO_DEPTH), .FULL_RESET_VALUE(0),
        .PROG_EMPTY_THRESH(10), .PROG_FULL_THRESH(10), .RD_DATA_COUNT_WIDTH(CW),
        .READ_DATA_WIDTH(DATA_WIDTH), .READ_MODE("std"), .RELATED_CLOCKS(0), .SIM_ASSERT_CHK(0),
        .USE_ADV_FEATURES("0105"), .WAKEUP_TIME(0), .WRITE_DATA_WIDTH(DATA_WIDTH), .WR_DATA_COUNT_WIDTH(CW)
    ) u_fifo (
        .almost_empty(fifo_almost_empty), .almost_full(fifo_almost_full), .data_valid(fifo_data_valid),
        .dbiterr(fifo_dbiterr), .dout(fifo_dout), .empty(fifo_empty), .full(fifo_full),
        .overflow(fifo_ovf), .prog_empty(fifo_prog_empty), .prog_full(fifo_prog_full),
        .rd_data_count(fifo_rcnt), .rd_rst_busy(rd_rst_busy), .sbiterr(fifo_sbiterr),
        .underflow(fifo_unf), .wr_ack(fifo_wr_ack), .wr_data_count(fifo_wcnt), .wr_rst_busy(wr_rst_busy),
        .din(fifo_din), .injectdbiterr(1'b0), .injectsbiterr(1'b0), .rd_clk(gt_clk), .rd_en(fifo_rd_en),
        .rst(rst | fifo_clr), .sleep(1'b0), .wr_clk(clk), .wr_en(fifo_wr_en));

    // ------------------------------------------------------------------ writer (clk) and reader (gt_clk)
    logic [31:0]   words_w;
    logic [31:0]   overflows;
    logic [31:0]   stall_w;
    logic [CW-1:0] occ_max;

    p5_wr_side #(.CW(CW), .PRBS_SEED(PRBS_SEED), .DEPTH(FIFO_DEPTH)) u_wr (
        .clk(clk), .rst(rst), .run(run), .blocked(cs != CS_IDLE), .clr(clr_now),
        .full(fifo_full | wr_rst_busy), .ovf_flag(fifo_ovf), .fill(fifo_wcnt), .fill_ok(~wr_rst_busy),
        .wr_en(fifo_wr_en), .din(fifo_din), .words_w(words_w), .overflows(overflows),
        .stall_w(stall_w), .occ_max(occ_max));

    logic [31:0] words_r;
    logic [31:0] data_errs;
    logic [31:0] underflows;
    logic        err_seen;

    p5_rd_side #(.PRBS_SEED(PRBS_SEED), .DIV(SLOW_READ_DIV_CYCLES)) u_rd (
        .clk(gt_clk), .rst(rst_rd), .slow(slow_gt), .inject(inj_gt), .clr(clr_gt),
        .empty(fifo_empty), .rd_busy(rd_rst_busy), .dout(fifo_dout), .unf_flag(fifo_unf),
        .rd_en(fifo_rd_en), .words_r(words_r), .data_errs(data_errs), .underflows(underflows),
        .err_seen(err_seen));

    // ------------------------------------------------------------------ error flag to clk for the LED
    logic err_c3;
    xpm_cdc_single #(.DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_cdc_err (
        .src_clk(gt_clk), .src_in(err_seen), .dest_clk(clk), .dest_out(err_c3));
    assign led = {err_c3, run};

    // ------------------------------------------------------------------ snapshot: clk -> gt_clk request, gt_clk -> clk data
    typedef enum logic [1:0] {RQ_IDLE, RQ_SEND, RQ_LOW} rq_t;
    rq_t         rq;
    logic        snap_send;
    logic        snap_rcv;
    logic        snap_pend;
    logic        resp_got;
    logic        lat_run;
    logic [2:0]  lat_cnt;
    wire         snap_busy  = (rq != RQ_IDLE) || !resp_got;
    wire         snap_start = (snap_we || snap_pend) && !snap_busy;

    logic [31:0]   s_words_w;
    logic [31:0]   s_words_r;
    logic [31:0]   s_errs;
    logic [31:0]   s_ovf;
    logic [31:0]   s_unf;
    logic [31:0]   s_stall;
    logic [CW-1:0] s_occ;

    logic          resp_req;
    logic [95:0]   resp_data;

    always_ff @(posedge clk) begin
        if (rst) begin
            rq        <= RQ_IDLE;
            snap_pend <= 1'b0;
            resp_got  <= 1'b1;
            lat_run   <= 1'b0;
            lat_cnt   <= 3'd0;
            s_words_w <= 32'd0;
            s_words_r <= 32'd0;
            s_errs    <= 32'd0;
            s_ovf     <= 32'd0;
            s_unf     <= 32'd0;
            s_stall   <= 32'd0;
            s_occ     <= '0;
        end else begin
            if (snap_we && snap_busy) snap_pend <= 1'b1;
            if (snap_start) begin
                snap_pend <= 1'b0;
                rq        <= RQ_SEND;
                resp_got  <= 1'b0;
                lat_run   <= 1'b1;
                lat_cnt   <= 3'd0;
            end
            case (rq)
                RQ_SEND: if (snap_rcv)  rq <= RQ_LOW;
                RQ_LOW:  if (!snap_rcv) rq <= RQ_IDLE;
                default: begin
                end
            endcase
            // the clk-side counters are latched a few clocks after the request, so the gt side is captured first
            if (lat_run) begin
                lat_cnt <= lat_cnt + 3'd1;
                if (lat_cnt == 3'd3) begin
                    lat_run   <= 1'b0;
                    s_words_w <= words_w;
                    s_ovf     <= overflows;
                    s_stall   <= stall_w;
                    s_occ     <= occ_max;
                end
            end
            if (resp_req) begin
                resp_got  <= 1'b1;
                s_words_r <= resp_data[95:64];
                s_errs    <= resp_data[63:32];
                s_unf     <= resp_data[31:0];
            end
        end
    end
    assign snap_send = (rq == RQ_SEND);

    // request handshake clk -> gt_clk
    logic req_gt;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [0:0] req_data_unused;
    /* verilator lint_on UNUSEDSIGNAL */
    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_SYNC_FF(2), .WIDTH(1)) u_cdc_snap_req (
        .dest_ack(1'b0), .dest_clk(gt_clk), .dest_out(req_data_unused), .dest_req(req_gt),
        .src_clk(clk), .src_in(1'b1), .src_rcv(snap_rcv), .src_send(snap_send));

    // gt_clk side: capture the reader counters, send them back
    typedef enum logic [1:0] {GS_IDLE, GS_SEND, GS_LOW} gs_t;
    gs_t         gs;
    logic        g_send;
    logic        g_rcv;
    logic        g_pend;
    logic [95:0] g_data;

    always_ff @(posedge gt_clk) begin
        if (rst_rd) begin
            gs     <= GS_IDLE;
            g_send <= 1'b0;
            g_pend <= 1'b0;
            g_data <= 96'd0;
        end else begin
            if (req_gt && gs != GS_IDLE) g_pend <= 1'b1;
            case (gs)
                GS_IDLE: if (req_gt || g_pend) begin
                    g_data <= {words_r, data_errs, underflows};
                    g_send <= 1'b1;
                    g_pend <= 1'b0;
                    gs     <= GS_SEND;
                end
                GS_SEND: if (g_rcv) begin
                    g_send <= 1'b0;
                    gs     <= GS_LOW;
                end
                GS_LOW: if (!g_rcv) gs <= GS_IDLE;
                default: gs <= GS_IDLE;
            endcase
        end
    end

    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(2), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_SYNC_FF(2), .WIDTH(96)) u_cdc_snap_rsp (
        .dest_ack(1'b0), .dest_clk(clk), .dest_out(resp_data), .dest_req(resp_req),
        .src_clk(gt_clk), .src_in(g_data), .src_rcv(g_rcv), .src_send(g_send));

    // ------------------------------------------------------------------ register read mux (registered, holds until the next h_re)
    always_ff @(posedge clk) begin
        if (h_re) begin
            case (h_addr)
                12'h000: h_rdata <= DESIGN_ID;
                12'h004: h_rdata <= build_word;
                12'h008: h_rdata <= scratch;
                12'h010: h_rdata <= {30'd0, slow, run};
                12'h014: h_rdata <= s_words_w;
                12'h018: h_rdata <= s_words_r;
                12'h01C: h_rdata <= s_errs;
                12'h020: h_rdata <= s_ovf;
                12'h024: h_rdata <= s_unf;
                12'h028: h_rdata <= s_stall;
                12'h02C: h_rdata <= {{(32 - CW){1'b0}}, s_occ};
                default: h_rdata <= 32'd0;
            endcase
        end
    end
endmodule
