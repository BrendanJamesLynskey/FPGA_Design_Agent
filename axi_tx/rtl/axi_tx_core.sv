// axi_tx_core: the on-chip AXI4-Lite and AXI4-Stream transactor, protocol checker and scoreboard (brief 59A).
//
//   program RAM --> sequencer --> axil_tx_master ==AXI4-Lite==> m_axil_* (the target)       axil_rules + axil_mon watch it
//                         \-----> axis_tx_source ==AXI4-Stream==> m_axis_* (the stream DUT)
//                         \-----> axis_tx_sink   <==AXI4-Stream== s_axis_* (the DUT's output) axis_rules + axis_mon watch it
//                         \-----> scoreboard (reference memory), transaction log, CRC digest
//
// The host loads a transaction program through the register window (shell/PROTOCOL.md window, offsets 0x00-0x1F here),
// starts it, and reads back verdicts, violations, coverage and performance counters. Changing the test needs no rebuild.
// The instruction set, the register map and the host are in axi_tx/host/ (program.py, regs.py, host.py) and docs/axi_tx.md.
//
// Instructions are 4 words (w0..w3); w0[31:28] is the opcode:
//   0 END      1 WRITE    2 READ     3 WAIT w1 cycles     4 LOOP w1 times (nest 4)     5 ENDLOOP
//   6 SET w0[7:0] := w1  (0 seed data, 1 seed Lite throttle, 2 seed stream throttle, 3 VALID_P, 4 READY_P, 5 S_VALID_P,
//                         6 S_READY_P, 7 AREG, 8 SB_BASE, 9 WATCHDOG cycles, 0 = off)
//   7 SSEND    send a packet: w1[15:0] beats, w2 first word, w0[3:0] last-beat TKEEP, w0[4] no TLAST, w0[5] expect it
//              at the sink, w0[6] first word random, w0[7] wait until sent
//   8 SWAIT    wait until the source is idle and every expected packet has arrived
//   9 WAITEV   wait until (ev_in & w1) != 0; w2 cycles timeout (0: none; a timeout is a hang)
// WRITE / READ flags in w0: [3:0] WSTRB (write) or compared bytes (read, with [24]); [5:4] expected response, [6] check
//   it; [7] random data (write); [8] random address bits w3; [9] address from AREG, then AREG += 4; [11:10] order,
//   [19:12] gap (write); [21:20] inject (axil_tx_master); [22] scoreboard (write: record, read: check); [23] random WSTRB;
//   [24] check the read data's bytes [3:0] against w2. w1 is the address and w2 the data.
// Random fields come from the data LFSR, one step per field, in the order address, data, WSTRB (axi_tx/host/model.py).
/* verilator lint_off UNUSEDSIGNAL */   // the window read strobe, the master's busy flag, spare instruction bits and the low bits of SB_BASE are not used
module axi_tx_core #(
    parameter int SDATA_W = 32,              // stream data width: 32 only in 59A (see the initial check below)
    parameter int LCHK    = 1,               // 1: the AXI4-Lite rule monitor and its log are built
    parameter int SCHK    = 1,               // 1: the AXI4-Stream rule monitor and its log are built
    parameter int MON     = 1                // 1: the performance and coverage counters are built
) (
    input  logic                    clk,
    input  logic                    rst,           // the transactor's own reset (active high)
    input  logic                    aresetn,       // the buses' reset (the target's), as the monitors see it
    input  logic [6:0]              win_addr,
    input  logic                    win_wr,
    input  logic                    win_rd,
    input  logic [31:0]             win_wdata,
    output logic [31:0]             win_rdata,
    input  logic [7:0]              ev_in,         // events for WAITEV
    output logic                    chk_trig,      // one-cycle pulse: a Lite or Stream rule episode started (capture trigger)
    output logic [9:0]              lite_viol,     // the rule vectors, for a capture probe
    output logic [4:0]              strm_viol,
    output logic                    running,
    // AXI4-Lite master
    output logic [31:0]             m_axil_awaddr,
    output logic [2:0]              m_axil_awprot,
    output logic                    m_axil_awvalid,
    input  logic                    m_axil_awready,
    output logic [31:0]             m_axil_wdata,
    output logic [3:0]              m_axil_wstrb,
    output logic                    m_axil_wvalid,
    input  logic                    m_axil_wready,
    input  logic [1:0]              m_axil_bresp,
    input  logic                    m_axil_bvalid,
    output logic                    m_axil_bready,
    output logic [31:0]             m_axil_araddr,
    output logic [2:0]              m_axil_arprot,
    output logic                    m_axil_arvalid,
    input  logic                    m_axil_arready,
    input  logic [31:0]             m_axil_rdata,
    input  logic [1:0]              m_axil_rresp,
    input  logic                    m_axil_rvalid,
    output logic                    m_axil_rready,
    // AXI4-Stream source (to the DUT) and sink (from the DUT)
    output logic [SDATA_W-1:0]      m_axis_tdata,
    output logic [SDATA_W/8-1:0]    m_axis_tkeep,
    output logic [SDATA_W/8-1:0]    m_axis_tstrb,
    output logic                    m_axis_tlast,
    output logic                    m_axis_tvalid,
    input  logic                    m_axis_tready,
    input  logic [SDATA_W-1:0]      s_axis_tdata,
    input  logic [SDATA_W/8-1:0]    s_axis_tkeep,
    input  logic [SDATA_W/8-1:0]    s_axis_tstrb,
    input  logic                    s_axis_tlast,
    input  logic                    s_axis_tvalid,
    output logic                    s_axis_tready
);
    localparam int KW = SDATA_W / 8;
    // The stream ends are 32-bit only in this version: an out-of-context synthesis at SDATA_W = 64 removed part of the
    // sequencer (cause not investigated; results/59a_axi_tx/resources.json "excluded"). An elaboration-time check, so
    // synthesis and lint stop on any other width; the stand-alone axis_checker is measured at 32, 64 and 128 bits.
    if (SDATA_W != 32) begin : g_width_check
        $error("axi_tx_core: SDATA_W must be 32 in this version");
    end
    localparam logic [31:0] VERSION = 32'h59A0_0100;

    // ------------------------------------------------------------------ host-side registers
    logic [9:0]  prog_addr = '0;
    logic [7:0]  log_entry = '0;
    logic [1:0]  log_word  = '0;
    logic [6:0]  lmon_sel = '0;
    logic [5:0]  smon_sel = '0, lchk_sel = '0, schk_sel = '0;
    logic [2:0]  sink_sel = '0;
    logic [9:0]  lchk_en = 10'h3FF;
    logic [4:0]  schk_en = 5'h07;
    logic [15:0] s_maxlen = '0;
    wire host_start = win_wr && win_addr == 7'h00 && win_wdata[0];
    wire host_abort = win_wr && win_addr == 7'h00 && win_wdata[1];
    wire host_clear = win_wr && win_addr == 7'h00 && win_wdata[2];

    // ------------------------------------------------------------------ program RAM: 4 banks x 256 x 32 (one 128-bit instruction a row)
    logic [31:0] pb0 [256], pb1 [256], pb2 [256], pb3 [256];
    logic [31:0] q0, q1, q2, q3;
    logic [7:0]  fetch_idx;
    logic [9:0]  pc = '0;
    wire  prog_we = win_wr && win_addr == 7'h03;
    always_ff @(posedge clk) begin
        if (prog_we) case (prog_addr[1:0])
            2'd0: pb0[prog_addr[9:2]] <= win_wdata;
            2'd1: pb1[prog_addr[9:2]] <= win_wdata;
            2'd2: pb2[prog_addr[9:2]] <= win_wdata;
            default: pb3[prog_addr[9:2]] <= win_wdata;
        endcase
        q0 <= pb0[fetch_idx]; q1 <= pb1[fetch_idx]; q2 <= pb2[fetch_idx]; q3 <= pb3[fetch_idx];
    end

    // ------------------------------------------------------------------ LFSRs: data (one step per random field), throttle (one step per cycle)
    logic        d_load = 1'b0, d_step, t_load = 1'b0, s_load = 1'b0;
    logic [31:0] d_seed = '0, t_seed = '0, s_seed = '0;
    logic [31:0] lfsr_d, lfsr_t, lfsr_s;
    axi_tx_lfsr u_ld (.clk(clk), .load(d_load), .seed(d_seed), .step(d_step), .state(lfsr_d));
    axi_tx_lfsr u_lt (.clk(clk), .load(t_load), .seed(t_seed), .step(running), .state(lfsr_t));
    axi_tx_lfsr u_ls (.clk(clk), .load(s_load), .seed(s_seed), .step(running), .state(lfsr_s));

    // ------------------------------------------------------------------ engines
    logic        m_start = 1'b0, m_is_read = 1'b0;
    logic [31:0] m_addr = '0, m_wdata = '0;
    logic [3:0]  m_wstrb = '0;
    logic [1:0]  m_order = '0, m_inject = '0;
    logic [7:0]  m_gap = '0, valid_p = '0, ready_p = 8'hFF, s_valid_p = '0, s_ready_p = 8'hFF;
    logic        m_busy, m_done;
    logic [1:0]  m_resp;
    logic [31:0] m_rdata, m_lat;
    logic        p_aw, p_w, p_b, p_ar, p_r;
    wire         eng_rst = rst || !aresetn || host_abort;
    axil_tx_master u_m (
        .clk(clk), .rst(eng_rst), .start(m_start), .is_read(m_is_read), .addr(m_addr), .wdata(m_wdata), .wstrb(m_wstrb),
        .order(m_order), .gap(m_gap), .inject(m_inject), .thr(lfsr_t), .valid_p(valid_p), .ready_p(ready_p),
        .busy(m_busy), .done(m_done), .resp(m_resp), .rdata(m_rdata), .latency(m_lat),
        .pend_aw(p_aw), .pend_w(p_w), .pend_b(p_b), .pend_ar(p_ar), .pend_r(p_r),
        .m_awaddr(m_axil_awaddr), .m_awprot(m_axil_awprot), .m_awvalid(m_axil_awvalid), .m_awready(m_axil_awready),
        .m_wdata(m_axil_wdata), .m_wstrb(m_axil_wstrb), .m_wvalid(m_axil_wvalid), .m_wready(m_axil_wready),
        .m_bresp(m_axil_bresp), .m_bvalid(m_axil_bvalid), .m_bready(m_axil_bready),
        .m_araddr(m_axil_araddr), .m_arprot(m_axil_arprot), .m_arvalid(m_axil_arvalid), .m_arready(m_axil_arready),
        .m_rdata(m_axil_rdata), .m_rresp(m_axil_rresp), .m_rvalid(m_axil_rvalid), .m_rready(m_axil_rready));

    logic          s_start = 1'b0, s_push = 1'b0, s_no_last = 1'b0;
    logic [15:0]   s_len = '0;
    logic [31:0]   s_first = '0;
    logic [KW-1:0] s_keep = '0;
    logic          s_busy, x_full, x_empty;
    logic [31:0]   k_beats, k_pkts, k_dm, k_km, k_lm, k_unx, k_first;
    axis_tx_source #(.DATA_W(SDATA_W)) u_src (
        .clk(clk), .rst(eng_rst), .start(s_start), .len(s_len), .first(s_first), .keep_last(s_keep), .no_last(s_no_last),
        .thr(lfsr_s), .valid_p(s_valid_p), .busy(s_busy), .tdata(m_axis_tdata), .tkeep(m_axis_tkeep), .tstrb(m_axis_tstrb),
        .tlast(m_axis_tlast), .tvalid(m_axis_tvalid), .tready(m_axis_tready));
    logic clr = 1'b0;                                  // clear every log and counter (start or host clear)
    axis_tx_sink #(.DATA_W(SDATA_W)) u_sink (
        .clk(clk), .rst(eng_rst), .clear(clr), .exp_push(s_push), .exp_len(s_len), .exp_first(s_first),
        .exp_keep_last(s_keep), .exp_no_last(s_no_last), .exp_full(x_full), .exp_empty(x_empty), .thr(lfsr_s),
        .ready_p(s_ready_p), .tdata(s_axis_tdata), .tkeep(s_axis_tkeep), .tlast(s_axis_tlast), .tvalid(s_axis_tvalid),
        .tready(s_axis_tready), .beats(k_beats), .pkts(k_pkts), .data_mism(k_dm), .keep_mism(k_km), .last_mism(k_lm),
        .unexpected(k_unx), .first_mism(k_first));

    // ------------------------------------------------------------------ checkers and counters on the two buses
    logic [31:0] now = '0;                             // cycles since the last clear: the violation time base
    logic [31:0] lchk_q, schk_q, lmon_q, smon_q;
    logic        l_trig, s_trig, l_any, s_any;
    generate
        if (LCHK != 0) begin : g_lchk
            axil_rules u_lr (
                .aclk(clk), .aresetn(aresetn),
                .awaddr(m_axil_awaddr), .awprot(m_axil_awprot), .awvalid(m_axil_awvalid), .awready(m_axil_awready),
                .wdata(m_axil_wdata), .wstrb(m_axil_wstrb), .wvalid(m_axil_wvalid), .wready(m_axil_wready),
                .bresp(m_axil_bresp), .bvalid(m_axil_bvalid), .bready(m_axil_bready),
                .araddr(m_axil_araddr), .arprot(m_axil_arprot), .arvalid(m_axil_arvalid), .arready(m_axil_arready),
                .rdata(m_axil_rdata), .rresp(m_axil_rresp), .rvalid(m_axil_rvalid), .rready(m_axil_rready), .viol(lite_viol));
            axi_viol_log #(.NR(10)) u_ll (.clk(clk), .clear(clr), .en(lchk_en), .viol(lite_viol), .now(now), .trig(l_trig),
                                         .any(l_any), .rd_sel(lchk_sel), .rd_data(lchk_q));
        end else begin : g_no_lchk
            assign lite_viol = '0; assign l_trig = 1'b0; assign l_any = 1'b0; assign lchk_q = '0;
        end
        if (SCHK != 0) begin : g_schk
            axis_rules #(.DATA_W(SDATA_W)) u_sr (
                .aclk(clk), .aresetn(aresetn), .maxlen(s_maxlen), .tdata(s_axis_tdata), .tkeep(s_axis_tkeep),
                .tstrb(s_axis_tstrb), .tlast(s_axis_tlast), .tvalid(s_axis_tvalid), .tready(s_axis_tready), .viol(strm_viol));
            axi_viol_log #(.NR(5)) u_sl (.clk(clk), .clear(clr), .en(schk_en), .viol(strm_viol), .now(now), .trig(s_trig),
                                         .any(s_any), .rd_sel(schk_sel), .rd_data(schk_q));
        end else begin : g_no_schk
            assign strm_viol = '0; assign s_trig = 1'b0; assign s_any = 1'b0; assign schk_q = '0;
        end
        if (MON != 0) begin : g_mon
            axil_mon u_lm (
                .aclk(clk), .aresetn(aresetn), .clear(clr), .awvalid(m_axil_awvalid), .awready(m_axil_awready),
                .wstrb(m_axil_wstrb), .wvalid(m_axil_wvalid), .wready(m_axil_wready), .bresp(m_axil_bresp),
                .bvalid(m_axil_bvalid), .bready(m_axil_bready), .arvalid(m_axil_arvalid), .arready(m_axil_arready),
                .rresp(m_axil_rresp), .rvalid(m_axil_rvalid), .rready(m_axil_rready), .rd_sel(lmon_sel), .rd_data(lmon_q));
            axis_mon #(.DATA_W(SDATA_W)) u_smn (
                .aclk(clk), .aresetn(aresetn), .clear(clr), .tkeep(s_axis_tkeep), .tlast(s_axis_tlast),
                .tvalid(s_axis_tvalid), .tready(s_axis_tready), .rd_sel(smon_sel), .rd_data(smon_q));
        end else begin : g_no_mon
            assign lmon_q = '0; assign smon_q = '0;
        end
    endgenerate
    assign chk_trig = l_trig || s_trig;

    // ------------------------------------------------------------------ scoreboard: reference memory of one 4 KB window, 1024 x {byte valid[3:0], data}
    logic [35:0] sb [1024];
    logic [35:0] sb_q;
    logic [9:0]  sb_idx = '0;
    logic        sb_we = 1'b0;
    logic [35:0] sb_wd = '0;
    always_ff @(posedge clk) begin
        if (sb_we) sb[sb_idx] <= sb_wd;
        sb_q <= sb[sb_idx];
    end

    // ------------------------------------------------------------------ transaction log: 256 entries x 3 words, and the digest
    logic [31:0] lg0 [256], lg1 [256], lg2 [256];
    logic [31:0] lg_q;
    logic        lg_we = 1'b0;
    logic [7:0]  lg_idx = '0;
    logic [31:0] lg_w0 = '0, lg_w1 = '0, lg_w2 = '0;
    always_ff @(posedge clk) begin
        if (lg_we) begin lg0[lg_idx] <= lg_w0; lg1[lg_idx] <= lg_w1; lg2[lg_idx] <= lg_w2; end
        case (log_word)
            2'd0: lg_q <= lg0[log_entry];
            2'd1: lg_q <= lg1[log_entry];
            default: lg_q <= lg2[log_entry];
        endcase
    end
    function automatic logic [31:0] crc32w(input logic [31:0] c, input logic [31:0] w);   // reflected CRC-32, LSB first
        logic [31:0] x;
        x = c;
        for (int i = 0; i < 32; i++) x = (x[0] ^ w[i]) ? ((x >> 1) ^ 32'hEDB8_8320) : (x >> 1);
        return x;
    endfunction

    // ------------------------------------------------------------------ the sequencer
    typedef enum logic [3:0] {S_IDLE, S_CLR, S_FETCH, S_FETCH2, S_DEC, S_LITE, S_SB, S_SB2, S_LOG, S_WAIT, S_SSEND, S_SWAIT,
                              S_EV, S_END} st_t;
    st_t         st = S_IDLE;
    logic [31:0] i0 = '0, i1 = '0, i2 = '0, i3 = '0;      // the current instruction
    logic [9:0]  lp_pc [4];
    logic [31:0] lp_n [4];
    logic [2:0]  sp = '0;
    logic [31:0] areg = '0, sb_base = '0, wdog = 32'd1_000_000, wcnt = '0, run_cycles = '0, n_txn = '0, digest_c = 32'hFFFF_FFFF;
    logic [31:0] sb_checked = '0, sb_mism = '0, sb_unchk = '0, exp_mism = '0, resp_mism = '0;
    logic [31:0] fm_addr = '0, fm_exp = '0, fm_got = '0, fm_txn = '0;
    logic        f_done = 1'b0, f_hang = 1'b0, f_err = 1'b0;
    logic [7:0]  hang_ch = '0;
    logic [31:0] t_addr = '0, t_data = '0;                 // the transaction's address and data (write data or read data)
    logic [3:0]  t_strb = '0;
    logic [1:0]  t_resp = '0;
    logic [31:0] t_lat = '0;
    logic        t_sbm = 1'b0, t_expm = 1'b0, t_respm = 1'b0;
    logic [1:0]  lg_phase = '0;
    initial for (int i = 0; i < 4; i++) begin lp_pc[i] = '0; lp_n[i] = '0; end

    wire [3:0] op = i0[31:28];
    wire       f_check_resp = i0[6], f_rdata = i0[7], f_raddr = i0[8], f_areg = i0[9], f_sb = i0[22], f_rstrb = i0[23];
    wire       f_cexp = i0[24];
    wire       in_win = (t_addr[31:12] == sb_base[31:12]);
    assign running   = (st != S_IDLE) && (st != S_END) && (st != S_CLR);   // the throttle LFSRs step while running
    wire   busy      = (st != S_IDLE) && (st != S_END);                    // STATUS bit 0: the run (with its clear) is in progress
    assign fetch_idx = (st == S_IDLE || st == S_END) ? prog_addr[9:2] : pc[7:0];

    // data-LFSR draws in S_DEC: address, then data, then WSTRB, each one step (the model does the same)
    logic [1:0] draw;                                       // how many draws this instruction makes (0-3)
    always_comb begin
        draw = 2'd0;
        if (st == S_DEC && (op == 4'd1 || op == 4'd2)) draw = 2'(f_raddr) + ((op == 4'd1) ? 2'(f_rdata) + 2'(f_rstrb) : 2'd0);
        if (st == S_DEC && op == 4'd7) draw = 2'(i0[6]);
    end
    logic [1:0] dk = '0;                                    // draws done for this instruction
    assign d_step = (st == S_DEC) && (dk < draw);

    function automatic logic [31:0] bmask(input logic [3:0] b);
        bmask = {{8{b[3]}}, {8{b[2]}}, {8{b[1]}}, {8{b[0]}}};
    endfunction

    always_ff @(posedge clk) begin
        m_start <= 1'b0; s_start <= 1'b0; s_push <= 1'b0; lg_we <= 1'b0; sb_we <= 1'b0; clr <= 1'b0;
        d_load <= 1'b0; t_load <= 1'b0; s_load <= 1'b0;
        now <= clr ? 32'd0 : now + 1'b1;
        if (running) run_cycles <= run_cycles + 1'b1;
        if (rst) begin
            st <= S_IDLE;
        end else if (host_abort) begin
            st <= S_IDLE;
        end else if (host_start || host_clear) begin
            clr <= 1'b1;
            run_cycles <= '0; n_txn <= '0; digest_c <= 32'hFFFF_FFFF; sb_checked <= '0; sb_mism <= '0; sb_unchk <= '0;
            exp_mism <= '0; resp_mism <= '0; fm_addr <= '0; fm_exp <= '0; fm_got <= '0; fm_txn <= '0;
            f_done <= 1'b0; f_hang <= 1'b0; f_err <= 1'b0; hang_ch <= '0;
            if (host_start) begin
                // defaults of a run (axi_tx/host/program.py DEFAULTS)
                pc <= '0; sp <= '0; areg <= '0; sb_base <= '0; wdog <= 32'd1_000_000; valid_p <= '0; ready_p <= 8'hFF;
                s_valid_p <= '0; s_ready_p <= 8'hFF;
                d_seed <= 32'h1; t_seed <= 32'h1; s_seed <= 32'h1; d_load <= 1'b1; t_load <= 1'b1; s_load <= 1'b1;
                sb_idx <= '0; sb_wd <= '0; sb_we <= 1'b1; st <= S_CLR;
            end
        end else begin
            case (st)
                S_IDLE, S_END: ;
                S_CLR: begin                                // zero the reference memory (1024 cycles)
                    sb_we <= 1'b1; sb_wd <= '0;
                    if (sb_idx == 10'h3FF) begin sb_we <= 1'b0; st <= S_FETCH; end
                    else sb_idx <= sb_idx + 1'b1;
                end
                S_FETCH:  st <= S_FETCH2;                   // the program RAM row at pc
                S_FETCH2: begin i0 <= q0; i1 <= q1; i2 <= q2; i3 <= q3; dk <= '0; wcnt <= '0; st <= S_DEC; end
                S_DEC: begin
                    if (dk < draw) begin
                        // one draw a cycle; the field it fills depends on how many came before
                        dk <= dk + 1'b1;
                        if (op == 4'd7) s_first <= lfsr_d;
                        else if (f_raddr && dk == 0) i1 <= ((i1 & ~i3) | (lfsr_d & i3)) & ~32'h3;
                        else if (op == 4'd1 && f_rdata && dk == 2'(f_raddr)) i2 <= lfsr_d;
                        else i0[3:0] <= lfsr_d[3:0];       // the WSTRB draw comes last
                    end else begin
                        case (op)
                            4'd0: begin f_done <= 1'b1; st <= S_END; end
                            4'd1, 4'd2: begin
                                t_addr <= f_areg ? areg : {i1[31:2], 2'b00};
                                m_addr <= f_areg ? areg : {i1[31:2], 2'b00};
                                if (f_areg) areg <= areg + 32'd4;
                                m_is_read <= (op == 4'd2); m_wdata <= i2; m_wstrb <= i0[3:0]; m_order <= i0[11:10];
                                m_gap <= i0[19:12]; m_inject <= i0[21:20]; m_start <= 1'b1;
                                t_strb <= i0[3:0]; t_sbm <= 1'b0; t_expm <= 1'b0; t_respm <= 1'b0;
                                st <= S_LITE;
                            end
                            4'd3: st <= S_WAIT;
                            4'd4: begin
                                if (sp == 3'd4) begin f_err <= 1'b1; st <= S_END; end
                                else begin lp_pc[sp[1:0]] <= pc + 1'b1; lp_n[sp[1:0]] <= (i1 == 0) ? 32'd1 : i1; sp <= sp + 1'b1;
                                           pc <= pc + 1'b1; st <= S_FETCH; end
                            end
                            4'd5: begin
                                if (sp == 3'd0) begin f_err <= 1'b1; st <= S_END; end
                                else if (lp_n[sp[1:0] - 1'b1] > 1) begin
                                    lp_n[sp[1:0] - 1'b1] <= lp_n[sp[1:0] - 1'b1] - 1'b1; pc <= lp_pc[sp[1:0] - 1'b1]; st <= S_FETCH;
                                end else begin sp <= sp - 1'b1; pc <= pc + 1'b1; st <= S_FETCH; end
                            end
                            4'd6: begin
                                case (i0[7:0])
                                    8'd0: begin d_seed <= i1; d_load <= 1'b1; end
                                    8'd1: begin t_seed <= i1; t_load <= 1'b1; end
                                    8'd2: begin s_seed <= i1; s_load <= 1'b1; end
                                    8'd3: valid_p <= i1[7:0];
                                    8'd4: ready_p <= i1[7:0];
                                    8'd5: s_valid_p <= i1[7:0];
                                    8'd6: s_ready_p <= i1[7:0];
                                    8'd7: areg <= {i1[31:2], 2'b00};
                                    8'd8: sb_base <= i1;
                                    8'd9: wdog <= i1;
                                    default: ;
                                endcase
                                pc <= pc + 1'b1; st <= S_FETCH;
                            end
                            4'd7: begin
                                s_len <= i1[15:0]; if (!i0[6]) s_first <= i2; s_keep <= i0[KW-1:0]; s_no_last <= i0[4];
                                st <= S_SSEND;
                            end
                            4'd8: st <= S_SWAIT;
                            4'd9: st <= S_EV;
                            default: begin f_err <= 1'b1; st <= S_END; end
                        endcase
                    end
                end
                S_LITE: begin
                    wcnt <= wcnt + 1'b1;
                    if (m_done) begin
                        t_resp <= m_resp; t_lat <= m_lat;
                        if (m_is_read) t_data <= m_rdata; else t_data <= m_wdata;
                        if (f_check_resp && m_resp != i0[5:4]) t_respm <= 1'b1;
                        if (m_is_read && f_cexp && ((m_rdata ^ i2) & bmask(i0[3:0])) != 0) t_expm <= 1'b1;
                        sb_idx <= t_addr[11:2];
                        st <= S_SB;
                    end else if (wdog != 0 && wcnt >= wdog) begin
                        f_hang <= 1'b1; hang_ch <= {3'b0, p_r, p_ar, p_b, p_w, p_aw}; st <= S_END;
                    end
                end
                S_SB: st <= S_SB2;                          // reference memory row at t_addr
                S_SB2: begin
                    if (f_sb && in_win && t_resp == 2'b00) begin
                        if (!m_is_read) begin
                            sb_we <= 1'b1;
                            sb_wd <= {sb_q[35:32] | t_strb,
                                      (sb_q[31:0] & ~bmask(t_strb)) | (t_data & bmask(t_strb))};
                        end else if (sb_q[35:32] == 4'h0) begin
                            sb_unchk <= sb_unchk + 1'b1;
                        end else begin
                            sb_checked <= sb_checked + 1'b1;
                            if (((t_data ^ sb_q[31:0]) & bmask(sb_q[35:32])) != 0) t_sbm <= 1'b1;
                        end
                    end
                    lg_phase <= '0; st <= S_LOG;
                end
                S_LOG: begin                                // the digest takes the entry's three words, one a cycle
                    lg_phase <= lg_phase + 1'b1;
                    case (lg_phase)
                        2'd0: begin
                            lg_w0 <= {m_is_read ? 2'b10 : 2'b01, t_resp, t_sbm, t_expm, t_respm, 1'b0, t_lat[23:0]};
                            lg_w1 <= t_addr; lg_w2 <= t_data;
                            if (t_sbm) sb_mism <= sb_mism + 1'b1;
                            if (t_expm) exp_mism <= exp_mism + 1'b1;
                            if (t_respm) resp_mism <= resp_mism + 1'b1;
                            if ((t_sbm || t_expm || t_respm) && !fm_txn[31]) begin
                                fm_txn <= {1'b1, n_txn[30:0]}; fm_addr <= t_addr;
                                fm_exp <= t_sbm ? sb_q[31:0] : i2; fm_got <= t_data;
                            end
                        end
                        2'd1: begin digest_c <= crc32w(digest_c, lg_w0); lg_idx <= n_txn[7:0]; lg_we <= (n_txn < 256); end
                        2'd2: digest_c <= crc32w(digest_c, lg_w1);
                        default: begin
                            digest_c <= crc32w(digest_c, lg_w2); n_txn <= n_txn + 1'b1; pc <= pc + 1'b1; st <= S_FETCH;
                        end
                    endcase
                end
                S_WAIT: begin
                    wcnt <= wcnt + 1'b1;
                    if (wcnt + 1 >= i1) begin pc <= pc + 1'b1; st <= S_FETCH; end
                end
                S_SSEND: begin                              // the source is free and the expectation FIFO has room
                    wcnt <= wcnt + 1'b1;
                    if (!s_busy && !s_start && !(i0[5] && x_full)) begin
                        s_start <= 1'b1; s_push <= i0[5];
                        if (i0[7]) st <= S_SWAIT; else begin pc <= pc + 1'b1; st <= S_FETCH; end
                        wcnt <= '0;
                    end else if (wdog != 0 && wcnt >= wdog) begin
                        f_hang <= 1'b1; hang_ch <= {1'b0, x_full, s_busy, 5'b0}; st <= S_END;
                    end
                end
                S_SWAIT: begin
                    wcnt <= wcnt + 1'b1;
                    if (!s_busy && !s_start && x_empty && !s_push) begin pc <= pc + 1'b1; st <= S_FETCH; end
                    else if (wdog != 0 && wcnt >= wdog) begin f_hang <= 1'b1; hang_ch <= {1'b0, !x_empty, s_busy, 5'b0}; st <= S_END; end
                end
                S_EV: begin
                    wcnt <= wcnt + 1'b1;
                    if ((ev_in & i1[7:0]) != 0) begin pc <= pc + 1'b1; st <= S_FETCH; end
                    else if (i2 != 0 && wcnt >= i2) begin f_hang <= 1'b1; hang_ch <= 8'h80; st <= S_END; end
                end
                default: st <= S_IDLE;
            endcase
        end
    end

    // ------------------------------------------------------------------ host registers and the read mux (valid the cycle after win_rd)
    always_ff @(posedge clk) begin
        if (rst) begin
            prog_addr <= '0; lchk_en <= 10'h3FF; schk_en <= 5'h07; s_maxlen <= '0;
        end else if (win_wr) case (win_addr)
            7'h02: prog_addr <= win_wdata[9:0];
            7'h03: prog_addr <= prog_addr + 1'b1;
            7'h10: begin log_entry <= win_wdata[9:2]; log_word <= win_wdata[1:0]; end
            7'h12: lmon_sel <= win_wdata[6:0];
            7'h14: smon_sel <= win_wdata[5:0];
            7'h16: lchk_sel <= win_wdata[5:0];
            7'h18: schk_sel <= win_wdata[5:0];
            7'h1A: lchk_en <= win_wdata[9:0];
            7'h1B: schk_en <= win_wdata[4:0];
            7'h1C: s_maxlen <= win_wdata[15:0];
            7'h1D: sink_sel <= win_wdata[2:0];
            default: ;
        endcase
    end
    logic [31:0] pq;
    always_comb case (prog_addr[1:0])
        2'd0: pq = q0;  2'd1: pq = q1;  2'd2: pq = q2;  default: pq = q3;
    endcase
    logic [31:0] sinkq;
    always_comb case (sink_sel)
        3'd0: sinkq = k_beats; 3'd1: sinkq = k_pkts; 3'd2: sinkq = k_dm; 3'd3: sinkq = k_km; 3'd4: sinkq = k_lm;
        3'd5: sinkq = k_unx; 3'd6: sinkq = k_first; default: sinkq = '0;
    endcase
    wire sink_bad = (k_dm != 0) || (k_km != 0) || (k_lm != 0) || (k_unx != 0);
    always_ff @(posedge clk) begin
        case (win_addr)
            7'h00: win_rdata <= '0;
            7'h01: win_rdata <= {6'b0, pc, hang_ch, sink_bad, (sb_mism != 0 || exp_mism != 0 || resp_mism != 0), s_any, l_any,
                                 f_err, f_hang, f_done, busy};
            7'h02: win_rdata <= {22'b0, prog_addr};
            7'h03: win_rdata <= pq;
            7'h04: win_rdata <= run_cycles;
            7'h05: win_rdata <= n_txn;
            7'h06: win_rdata <= ~digest_c;
            7'h07: win_rdata <= sb_checked;
            7'h08: win_rdata <= sb_mism;
            7'h09: win_rdata <= sb_unchk;
            7'h0A: win_rdata <= exp_mism;
            7'h0B: win_rdata <= resp_mism;
            7'h0C: win_rdata <= fm_addr;
            7'h0D: win_rdata <= fm_exp;
            7'h0E: win_rdata <= fm_got;
            7'h0F: win_rdata <= fm_txn;
            7'h10: win_rdata <= {22'b0, log_entry, log_word};
            7'h11: win_rdata <= lg_q;
            7'h12: win_rdata <= {25'b0, lmon_sel};
            7'h13: win_rdata <= lmon_q;
            7'h14: win_rdata <= {26'b0, smon_sel};
            7'h15: win_rdata <= smon_q;
            7'h16: win_rdata <= {26'b0, lchk_sel};
            7'h17: win_rdata <= lchk_q;
            7'h18: win_rdata <= {26'b0, schk_sel};
            7'h19: win_rdata <= schk_q;
            7'h1A: win_rdata <= {22'b0, lchk_en};
            7'h1B: win_rdata <= {27'b0, schk_en};
            7'h1C: win_rdata <= {16'b0, s_maxlen};
            7'h1D: win_rdata <= {29'b0, sink_sel};
            7'h1E: win_rdata <= sinkq;
            7'h1F: win_rdata <= VERSION;
            default: win_rdata <= '0;
        endcase
    end
endmodule
/* verilator lint_on UNUSEDSIGNAL */
