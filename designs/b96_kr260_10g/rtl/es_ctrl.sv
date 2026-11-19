// es_ctrl.sv (brief 96D): the DRP master and the eye-scan point sequencer for the GTHE4 channel, in the free-running clock (the GT's DRPCLK is that clock, so no
// crossing). Two jobs, one DRP port:
//   1. raw DRP access for the host: one read or write of any 10-bit address (DRP_ADDR, DRP_DATA, ES_CMD bits 0 and 1);
//   2. one eye-scan POINT per ES_CMD bit 2: the documented sequence of UG576 (v1.7.1) chapter 4, "RX Margin Analysis", as read-modify-write DRP accesses:
//        ES_HORZ_OFFSET (0x04F [15:4]), RX_EYESCAN_VS_{NEG_DIR,UT_SIGN,CODE,RANGE} (0x097 [10:0]), ES_PRESCALE (0x03C [4:0]), ES_CONTROL.run (0x03C [10]),
//        poll es_control_status (0x253) until the END state (0101), read es_error_count (0x251) and es_sample_count (0x252), clear run.
//      Every read-modify-write keeps the bits the sequencer does not own (the other attributes that share a DRP word).
// The static eye-scan attributes (ES_QUALIFIER, ES_QUAL_MASK, ES_SDATA_MASK) are written by the host through the raw access, once per scan;
// ES_EYE_SCAN_EN and ES_ERRDET_EN come from the build (es.xdc), never from the DRP (UG576: re-enabling eye scan needs a PMA reset).
// While a point is running a raw command is ignored and the `rejected` flag is set (sticky until ES_CMD bit 3).
// Reads of the DRP have no side effects on the GT; the sequencer changes only the attributes named above. It does NOT restore them: the host does (docs).
module es_ctrl (
    input  logic        clk,
    input  logic        rst,
    // host side
    input  logic [9:0]  raw_addr,
    input  logic [15:0] raw_wdata,
    input  logic        raw_rd,          // pulse
    input  logic        raw_wr,          // pulse
    input  logic        pt_start,        // pulse
    input  logic        clr_flags,       // pulse
    input  logic [11:0] pt_horz,         // ES_HORZ_OFFSET[11:0] as written to the attribute (two's complement [10:0], bit 11 phase unification)
    input  logic [6:0]  pt_vs_code,
    input  logic        pt_vs_neg,
    input  logic        pt_vs_ut,
    input  logic [1:0]  pt_vs_range,
    input  logic [4:0]  pt_prescale,
    input  logic [31:0] pt_timeout,      // clocks of the status poll before the point is abandoned
    output logic [15:0] raw_rdata,       // the last DRP read (raw or the sequencer's)
    output logic        busy,
    output logic        pt_done,         // a point finished (cleared by the next start)
    output logic        pt_tmo,          // the last point's poll timed out (results are 0)
    output logic        drp_tmo,         // a DRP access got no DRDY (sticky)
    output logic        rejected,        // a raw command or start arrived while busy (sticky)
    output logic [3:0]  es_status,       // es_control_status as last read by the sequencer
    output logic [7:0]  step_o,
    output logic [15:0] pt_count,        // points completed since reset
    output logic [15:0] res_err,
    output logic [15:0] res_samp,
    // the GT's DRP port
    output logic [9:0]  drp_addr,
    output logic [15:0] drp_di,
    output logic        drp_en,
    output logic        drp_we,
    input  logic [15:0] drp_do,
    input  logic        drp_rdy
);
    // ---- DRP master: one access at a time, request/done
    typedef enum logic [1:0] {M_IDLE, M_ISSUE, M_WAIT} m_t;
    m_t         m;
    logic       rq, rq_we;
    logic [9:0] rq_addr;
    logic [15:0] rq_wd;
    logic       m_done;
    logic [15:0] m_rd;
    logic [7:0] m_cnt;
    always_ff @(posedge clk) begin
        m_done <= 1'b0; drp_en <= 1'b0;
        if (rst) begin m <= M_IDLE; drp_tmo <= 1'b0; m_rd <= '0; drp_addr <= '0; drp_di <= '0; drp_we <= 1'b0; m_cnt <= '0; end
        else begin
            if (clr_flags) drp_tmo <= 1'b0;
            case (m)
                M_IDLE: if (rq) begin drp_addr <= rq_addr; drp_di <= rq_wd; drp_we <= rq_we; drp_en <= 1'b1; m <= M_ISSUE; m_cnt <= '0; end
                M_ISSUE: m <= M_WAIT;
                M_WAIT: begin
                    m_cnt <= m_cnt + 8'd1;
                    if (drp_rdy) begin if (!drp_we) m_rd <= drp_do; m_done <= 1'b1; m <= M_IDLE; end
                    else if (m_cnt == 8'd255) begin drp_tmo <= 1'b1; m_done <= 1'b1; m <= M_IDLE; end
                end
                default: m <= M_IDLE;
            endcase
        end
    end

    // ---- sequencer
    typedef enum logic [4:0] {
        S_IDLE, S_RAW, S_RD4F, S_WR4F, S_RD97, S_WR97, S_RD3C, S_WR3C_A, S_WR3C_RUN, S_POLL, S_RD_ERR, S_RD_SAMP, S_WR3C_STOP, S_END
    } s_t;
    s_t          s;
    logic        rq_sent;          // the request was issued and is not yet answered
    logic [15:0] old4f, old97, old3c;
    logic [31:0] tcnt;
    logic        tmo_hit;
    assign busy = (s != S_IDLE);
    assign raw_rdata = m_rd;
    assign step_o = {3'd0, s};
    always_ff @(posedge clk) begin
        rq <= 1'b0;
        if (rst) begin
            s <= S_IDLE; rq_sent <= 1'b0; pt_done <= 1'b0; pt_tmo <= 1'b0; rejected <= 1'b0; es_status <= '0; pt_count <= '0;
            res_err <= '0; res_samp <= '0; old4f <= '0; old97 <= '0; old3c <= '0; tcnt <= '0; rq_we <= 1'b0; rq_addr <= '0; rq_wd <= '0; tmo_hit <= 1'b0;
        end else begin
            if (clr_flags) rejected <= 1'b0;
            if (s == S_IDLE) begin
                if (raw_rd || raw_wr || pt_start) begin
                    if (raw_rd || raw_wr) begin
                        // a raw command wins over a simultaneous start (the host never does both)
                        rq <= 1'b1; rq_we <= raw_wr; rq_addr <= raw_addr; rq_wd <= raw_wdata; rq_sent <= 1'b1; s <= S_RAW;
                    end else begin
                        pt_done <= 1'b0; pt_tmo <= 1'b0; tmo_hit <= 1'b0; res_err <= '0; res_samp <= '0;
                        rq <= 1'b1; rq_we <= 1'b0; rq_addr <= 10'h04F; rq_sent <= 1'b1; s <= S_RD4F;
                    end
                end
            end else begin
                if (raw_rd || raw_wr || pt_start) rejected <= 1'b1;
                if (rq_sent && m_done) rq_sent <= 1'b0;
                // each state starts its access when the previous one has completed (rq_sent low and m idle)
                case (s)
                    S_RAW: if (rq_sent && m_done) s <= S_IDLE;
                    S_RD4F: if (rq_sent && m_done) begin old4f <= m_rd; rq <= 1'b1; rq_we <= 1'b1; rq_addr <= 10'h04F; rq_wd <= {pt_horz, m_rd[3:0]}; rq_sent <= 1'b1; s <= S_WR4F; end
                    S_WR4F: if (rq_sent && m_done) begin rq <= 1'b1; rq_we <= 1'b0; rq_addr <= 10'h097; rq_sent <= 1'b1; s <= S_RD97; end
                    S_RD97: if (rq_sent && m_done) begin
                        old97 <= m_rd; rq <= 1'b1; rq_we <= 1'b1; rq_addr <= 10'h097;
                        rq_wd <= {m_rd[15:11], pt_vs_neg, pt_vs_ut, pt_vs_code, pt_vs_range}; rq_sent <= 1'b1; s <= S_WR97;
                    end
                    S_WR97: if (rq_sent && m_done) begin rq <= 1'b1; rq_we <= 1'b0; rq_addr <= 10'h03C; rq_sent <= 1'b1; s <= S_RD3C; end
                    S_RD3C: if (rq_sent && m_done) begin
                        old3c <= m_rd; rq <= 1'b1; rq_we <= 1'b1; rq_addr <= 10'h03C;
                        rq_wd <= {6'b000000, m_rd[9:5], pt_prescale}; rq_sent <= 1'b1; s <= S_WR3C_A;
                    end
                    S_WR3C_A: if (rq_sent && m_done) begin
                        rq <= 1'b1; rq_we <= 1'b1; rq_addr <= 10'h03C; rq_wd <= {6'b000001, old3c[9:5], pt_prescale}; rq_sent <= 1'b1; s <= S_WR3C_RUN; tcnt <= '0;
                    end
                    S_WR3C_RUN: if (rq_sent && m_done) begin rq <= 1'b1; rq_we <= 1'b0; rq_addr <= 10'h253; rq_sent <= 1'b1; s <= S_POLL; end
                    S_POLL: if (rq_sent && m_done) begin
                        es_status <= m_rd[3:0];
                        if (m_rd[3:0] == 4'b0101) begin rq <= 1'b1; rq_we <= 1'b0; rq_addr <= 10'h251; rq_sent <= 1'b1; s <= S_RD_ERR; end
                        else if (tcnt >= pt_timeout) begin tmo_hit <= 1'b1; rq <= 1'b1; rq_we <= 1'b1; rq_addr <= 10'h03C; rq_wd <= {6'b000000, old3c[9:5], pt_prescale}; rq_sent <= 1'b1; s <= S_WR3C_STOP; end
                        else begin rq <= 1'b1; rq_we <= 1'b0; rq_addr <= 10'h253; rq_sent <= 1'b1; end
                    end
                    S_RD_ERR: if (rq_sent && m_done) begin res_err <= m_rd; rq <= 1'b1; rq_we <= 1'b0; rq_addr <= 10'h252; rq_sent <= 1'b1; s <= S_RD_SAMP; end
                    S_RD_SAMP: if (rq_sent && m_done) begin
                        res_samp <= m_rd; rq <= 1'b1; rq_we <= 1'b1; rq_addr <= 10'h03C; rq_wd <= {6'b000000, old3c[9:5], pt_prescale}; rq_sent <= 1'b1; s <= S_WR3C_STOP;
                    end
                    S_WR3C_STOP: if (rq_sent && m_done) begin s <= S_END; end
                    S_END: begin pt_done <= 1'b1; pt_tmo <= tmo_hit; pt_count <= pt_count + 16'd1; s <= S_IDLE; end
                    default: s <= S_IDLE;
                endcase
                // the poll timer runs while the sequencer waits for the END state
                if (s == S_POLL || s == S_WR3C_RUN) tcnt <= tcnt + 32'd1;
            end
        end
    end
    logic _unused;
    assign _unused = &{1'b0, old4f, old97};
endmodule
