// p6_clkmux_core: register map, BUFGCTRL clock mux, mux-domain checker, frequency gate.
// clk is clk_c3 (25 MHz, clock A); clk_b is the BUFG_GT output (clock B). B_DIV is only reported
// (the divide is applied in the top); active-clock detection assumes clock B is faster than clock A.
/* verilator lint_off PROCASSINIT */
module p6_clkmux_core #(
    parameter logic [31:0] ID_VALUE         = 32'h20960001,
    parameter int          B_DIV            = 1,
    parameter logic [31:0] GATE_LEN_DEFAULT = 32'd25000000
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        clk_b,
    input  logic        h_we,
    input  logic        h_re,
    input  logic [11:0] h_addr,
    input  logic [31:0] h_wdata,
    output logic [31:0] h_rdata,
    output logic [1:0]  led,
    output logic        sfp_tx_disable
);
    assign sfp_tx_disable = 1'b1;

    // ---------------- BUILD word ----------------
    logic [31:0] build_w;
`ifdef SYNTHESIS
    USR_ACCESSE2 u_usr (.CFGCLK(), .DATA(build_w), .DATAVALID());
`else
    assign build_w = 32'd0;
`endif

    // ---------------- clock mux ----------------
    logic sel_q, mux_clk, sel_n;
    assign sel_n = ~sel_q;
    logic bg_ce, bg_ign;
    assign bg_ce  = 1'b1;
    assign bg_ign = 1'b0;
    BUFGCTRL #(.INIT_OUT(0), .PRESELECT_I0("TRUE"), .PRESELECT_I1("FALSE")) u_bufgctrl (.I0(clk), .I1(clk_b), .S0(sel_n), .S1(sel_q), .CE0(bg_ce), .CE1(bg_ce), .IGNORE0(bg_ign), .IGNORE1(bg_ign), .O(mux_clk));

    // reset into the muxed domain
    logic rst_m;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .RST_ACTIVE_HIGH(1)) u_rst_m (
        .dest_clk(mux_clk), .src_arst(rst), .dest_arst(rst_m));

    // ---------------- muxed domain: counter, Gray twin, checker ----------------
    logic [31:0] cnt = '0, gry = '0, prev = '0, errs;
    logic        valid;
    logic [31:0] cnt_n;
    assign cnt_n = cnt + 32'd1;

    function automatic logic [31:0] gray2bin(input logic [31:0] g);
        logic [31:0] b;
        b[31] = g[31];
        for (int i = 30; i >= 0; i--) b[i] = b[i+1] ^ g[i];
        return b;
    endfunction

    logic bad;
    assign bad = valid && ((gray2bin(gry) != cnt) || (cnt != prev + 32'd1));

    always_ff @(posedge mux_clk) begin
        // free-running datapath (no reset needed); only the checker state resets
        cnt  <= cnt_n;
        gry  <= cnt_n ^ (cnt_n >> 1);
        prev <= cnt;
        if (rst_m) begin
            valid <= 1'b0; errs <= '0;
        end else begin
            valid <= 1'b1;
            if (bad && errs != 32'hFFFFFFFF) errs <= errs + 32'd1;
        end
    end

    // continuous counter hand-over (snapshot source)
    logic [31:0] hold_m = '0;
    logic        send_m = 1'b0, rcv_m;
    logic [1:0]  hs_st = 2'd0;
    always_ff @(posedge mux_clk) begin
        case (hs_st)
            2'd0: begin hold_m <= cnt; send_m <= 1'b1; hs_st <= 2'd1; end
            2'd1: if (rcv_m) begin send_m <= 1'b0; hs_st <= 2'd2; end
            default: if (!rcv_m) hs_st <= 2'd0;
        endcase
    end
    logic [31:0] latest_w;
    logic        latest_req;
    xpm_cdc_handshake #(.DEST_EXT_HSK(0), .DEST_SYNC_FF(4), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0),
                        .SRC_SYNC_FF(4), .WIDTH(32)) u_snap (
        .src_clk(mux_clk), .src_in(hold_m), .src_send(send_m), .src_rcv(rcv_m),
        .dest_clk(clk), .dest_req(latest_req), .dest_ack(1'b0), .dest_out(latest_w));

    // gate and frequency counter in the muxed domain
    logic gate_c, gate_m, gate_mq;
    logic [31:0] fcnt;
    xpm_cdc_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_gate (
        .src_clk(clk), .src_in(gate_c), .dest_clk(mux_clk), .dest_out(gate_m));
    always_ff @(posedge mux_clk) begin
        gate_mq <= gate_m;
        if (gate_m) fcnt <= gate_mq ? fcnt + 32'd1 : 32'd1;
    end

    // slow tap bit for active-clock detection
    logic tap_m;
    always_ff @(posedge mux_clk) tap_m <= cnt[4];

    // ---------------- crossings into clk ----------------
    logic [31:0] errs_s, fcnt_s;
    logic        tap_s;
    xpm_cdc_array_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0), .WIDTH(32)) u_errs (
        .src_clk(mux_clk), .src_in(errs), .dest_clk(clk), .dest_out(errs_s));
    xpm_cdc_array_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0), .WIDTH(32)) u_fcnt (
        .src_clk(mux_clk), .src_in(fcnt), .dest_clk(clk), .dest_out(fcnt_s));
    xpm_cdc_single #(.DEST_SYNC_FF(3), .INIT_SYNC_FF(0), .SIM_ASSERT_CHK(0), .SRC_INPUT_REG(0)) u_tap (
        .src_clk(mux_clk), .src_in(tap_m), .dest_clk(clk), .dest_out(tap_s));

    // ---------------- clk domain ----------------
    logic [31:0] scratch, gate_len, gate_left, freq_count, mux_count, swcnt;
    logic [31:0] mux_latest = '0;
    always_ff @(posedge clk) if (latest_req) mux_latest <= latest_w;
    logic        active, done, busy;
    logic [3:0]  settle;
    logic        tap_q, pc;
    logic [5:0]  win, tc, tc_n;
    logic        edge_t;

    assign edge_t = tap_s ^ tap_q;
    assign tc_n   = tc + {5'd0, edge_t};

    logic switching;
    assign switching = (sel_q != active);
    assign led = {switching, active};

    always_ff @(posedge clk) begin
        tap_q <= tap_s;
        if (rst) begin
            pc <= 1'b0;
            scratch <= '0; sel_q <= 1'b0; gate_len <= GATE_LEN_DEFAULT; gate_c <= 1'b0; busy <= 1'b0;
            done <= 1'b0; gate_left <= '0; freq_count <= '0; mux_count <= '0; swcnt <= '0;
            active <= 1'b0; settle <= '0; win <= '0; tc <= '0;
        end else begin
            // register writes
            if (h_we) begin
                case (h_addr)
                    12'h008: scratch  <= h_wdata;
                    12'h010: sel_q    <= h_wdata[0];
                    12'h01C: gate_len <= h_wdata;
                    12'h038: mux_count <= mux_latest;
                    12'h020: if (h_wdata[0] && !busy) begin
                        busy <= 1'b1; done <= 1'b0; freq_count <= '0; gate_c <= 1'b1;
                        gate_left <= (gate_len == 32'd0) ? 32'd1 : gate_len; settle <= 4'd0;
                    end
                    default: ;
                endcase
            end
            // gate timer
            if (gate_c) begin
                gate_left <= gate_left - 32'd1;
                if (gate_left == 32'd1) gate_c <= 1'b0;
            end else if (busy && !(h_we && h_addr == 12'h020)) begin
                settle <= settle + 4'd1;
                if (settle == 4'd11) begin
                    busy <= 1'b0; done <= 1'b1; freq_count <= fcnt_s;
                end
            end
            // active clock detection: count slow-tap toggles in a 64-clock window
            win <= win + 6'd1;
            if (win == 6'd63) begin
                // two consecutive windows must agree before ACTIVE_SEL changes
                if (tc_n != 6'd0) begin
                    pc <= (tc_n >= 6'd12);
                    if (pc == (tc_n >= 6'd12) && pc != active) begin
                        active <= pc;
                        swcnt  <= swcnt + 32'd1;
                    end
                end
                tc <= '0;
            end else tc <= tc_n;
        end
    end

    // read port
    always_ff @(posedge clk) begin
        if (h_re) begin
            case (h_addr)
                12'h000: h_rdata <= ID_VALUE;
                12'h004: h_rdata <= build_w;
                12'h008: h_rdata <= scratch;
                12'h010: h_rdata <= {31'd0, sel_q};
                12'h014: h_rdata <= {30'd0, active, switching};
                12'h018: h_rdata <= 32'(B_DIV);
                12'h01C: h_rdata <= gate_len;
                12'h020: h_rdata <= 32'd0;
                12'h024: h_rdata <= {30'd0, done, busy};
                12'h028: h_rdata <= freq_count;
                12'h02C: h_rdata <= errs_s;
                12'h030: h_rdata <= mux_count;
                12'h034: h_rdata <= swcnt;
                default: h_rdata <= 32'd0;
            endcase
        end
    end
endmodule
