// ddr2_sched.sv (brief 141, phase 0): an application-optimised DDR2 command scheduler with two policies, on an abstract command interface.
//
// What it is. A request queue in front of a DDR2 command bus. Requests (read or write of one BL8 burst, by burst address) go in; one DDR2 command per clock comes out (ACTIVATE, READ, WRITE, PRECHARGE,
// PRECHARGE ALL, REFRESH) with the JEDEC timing rules enforced by per-bank and global down-counters. It owns no data path: the data bursts follow a READ by RL clocks and a WRITE by WL clocks, as in the
// DDR2 part, and the user's logic or a PHY moves them. It does not initialise the part: `en` goes high when the PHY (for example the AMD MIG's calibration) says the part is ready.
// The timing parameters are in clocks of the command bus (one command a clock). docs/memory_controller_plan.md maps this to AMD's MIG (what the native interface hides, what a controller replacing
// MIG's would drive) and to a coarser controller clock.
//
// Policies (parameter POLICY).
//   0 latency-first:   reads before writes, writes drained in batches (watermarks WR_HI, WR_LO); the oldest ready entry first; a bank with no pending request for its open row is precharged at once
//                      (eager precharge), so a random read finds its bank closed and pays tRCD + RL, never tRP + tRCD + RL; refresh postponed while reads are pending, up to REF_POST (and while
//                      `ref_defer` is high) and done in idle time.
//   1 bandwidth-first: open page; first-ready first-come-first-served (a request that hits an open row, then an ACTIVATE for the oldest, then a PRECHARGE for the oldest miss); stays in one direction
//                      (read or write) for up to RUN_MAX column commands to avoid the turnaround; refresh as soon as it is due unless REF_POST > 0.
//   Both: a request whose wait reaches AGE_LIM clocks and is the oldest in the queue is served alone (the other entries are held) so every request has a bounded wait (the formula is
//   verif/formal/run_formal.py:bound, section 9 of docs/memory_controller_plan.md explains it; the formal run checks it at small parameters, the simulations at real ones). AGE_LIM must exceed the wait of a
//   request in a full queue: below that the queue is served first-come first-served all the time (measured, results/b141).
//
// Ordering. A request never overtakes an older request to the same burst address when either of the two is a write (read-after-write, write-after-write and write-after-read keep program order).
// Otherwise requests complete out of order; `cmd_tag` returns the tag with the READ or WRITE.
//
// Reset: synchronous, active high, clears the queue and every timer; the bank state is "all precharged" (the part is precharged and the refresh timer starts when en rises: the user is told to hold
// `en` low until calibration is done and every bank is closed, which is how MIG hands the part over).
//
// Registered command output: the decision made in clock t appears on cmd_* in clock t+1; every timer is aligned to the decision, so spacings on the output are the spacings the rules require.
module ddr2_sched #(
    parameter int POLICY  = 0,      // 0 latency-first, 1 bandwidth-first
    parameter int QD      = 8,      // request queue depth (entries)
    parameter int BW      = 3,      // bank address bits (8 banks on the MT47H64M16)
    parameter int RW      = 13,     // row address bits
    parameter int CB      = 7,      // burst-column bits (128 bursts = a 2 KiB page of a x16 part)
    parameter int TW      = 6,      // tag width
    parameter int MAP     = 0,      // address map (ddr2_addrmap.sv)
    // timing, in command clocks. Defaults: MT47H64M16-25, DDR2-800 (tCK 2.5 ns), CL 6, BL8, from the Micron data sheet Rev. AB 09/18 (docs/memory_controller_plan.md section 2)
    parameter int T_RCD   = 6,      // ACTIVATE to READ/WRITE
    parameter int T_RP    = 6,      // PRECHARGE to ACTIVATE (one bank)
    parameter int T_RPA   = 7,      // PRECHARGE ALL to ACTIVATE or REFRESH
    parameter int T_RAS   = 16,     // ACTIVATE to PRECHARGE
    parameter int T_RC    = 22,     // ACTIVATE to ACTIVATE (same bank)
    parameter int T_RRD   = 4,      // ACTIVATE to ACTIVATE (different banks)
    parameter int T_FAW   = 20,     // four-ACTIVATE window
    parameter int T_WR    = 6,      // write recovery
    parameter int T_WTR   = 3,      // write to read (after the data burst)
    parameter int T_RTP   = 3,      // read to precharge
    parameter int T_RFC   = 51,     // REFRESH to the next command
    parameter int T_REFI  = 3120,   // average refresh interval
    parameter int RL      = 6,      // read latency (CL, AL = 0)
    parameter int WL      = 5,      // write latency (RL - 1)
    parameter int BL2     = 4,      // clocks a data burst occupies (BL / 2)
    // policy knobs
    parameter int AGE_LIM = 1024,   // an oldest entry this old is served alone (must exceed the wait of a request in a full queue, or the queue degrades to first-come first-served)
    parameter int WR_HI   = 6,      // POLICY 0: start draining writes at this many queued writes
    parameter int WR_LO   = 1,      // POLICY 0: stop draining at this many
    parameter int RUN_MAX = 16,     // POLICY 1: column commands in one direction before the other direction gets its turn
    parameter int REF_POST = 4      // refreshes that may be postponed (JEDEC allows up to 8; keep it below)
) (
    input  logic                    clk,
    input  logic                    rst,
    input  logic                    en,         // the part is initialised and precharged (calibration done)
    // requests
    input  logic                    req_v,
    output logic                    req_rdy,
    input  logic                    req_wr,
    input  logic [RW+BW+CB-1:0]     req_addr,   // burst address, see ddr2_addrmap.sv
    input  logic [TW-1:0]           req_tag,
    input  logic                    ref_defer,  // 1: a latency-critical window; refresh is postponed (within REF_POST), forced when the allowance is used
    // commands (registered)
    output logic                    cmd_v,
    output logic [2:0]              cmd_op,
    output logic [BW-1:0]           cmd_bank,
    output logic [RW-1:0]           cmd_row,    // ACTIVATE
    output logic [CB-1:0]           cmd_col,    // READ, WRITE (burst column)
    output logic [TW-1:0]           cmd_tag     // READ, WRITE
);
    localparam int NB   = 1 << BW;
    localparam int IW   = (QD > 1) ? $clog2(QD) : 1;
    localparam int QW   = $clog2(QD + 1);
    localparam int RTW  = RL + BL2 + 1 - WL;                         // READ to WRITE: the bus idles one clock between the read burst and the write burst (Micron Table 40, Figure 50)
    localparam int R2P  = BL2 - 2 + ((T_RTP > 2) ? T_RTP : 2);       // READ to PRECHARGE (AL = 0): BL/2 - 2 + max(tRTP, 2)
    localparam int W2P  = WL + BL2 + T_WR;                           // WRITE to PRECHARGE
    localparam int W2R  = WL + BL2 + T_WTR;                          // WRITE to READ
    localparam int WWID = $clog2(AGE_LIM + 2);
    localparam int RFW  = $clog2(T_REFI + 1);

    localparam logic [2:0] OP_NOP = 3'd0, OP_ACT = 3'd1, OP_RD = 3'd2, OP_WR = 3'd3, OP_PRE = 3'd4, OP_PREA = 3'd5, OP_REF = 3'd6;

    if (T_REFI < 4 * (T_RAS + T_RPA + T_RFC) || T_RFC > 255 || T_RC > 255 || T_FAW > 255 || W2P > 255 || W2R > 255) begin : g_chk_t
        $error("ddr2_sched: timing parameters out of range (counters are 8 bits; tREFI must exceed four times the longest refresh sequence)");
    end
    if (REF_POST < 0 || REF_POST > 6) begin : g_chk_p
        $error("ddr2_sched: REF_POST must be 0 to 6 (the postponement allowance keeps the debt below JEDEC's 8)");
    end
    if (RL != WL + 1) begin : g_chk_l
        $error("ddr2_sched: write latency must be read latency minus one (DDR2)");
    end

    // ------------------------------------------------------------------------------------------------ queue
    logic [QD-1:0]  v, w;
    logic [QD-1:0][BW-1:0] q_bank;
    logic [QD-1:0][RW-1:0] q_row;
    logic [QD-1:0][CB-1:0] q_col;
    logic [QD-1:0][TW-1:0] q_tag;
    logic [QD-1:0][QD-1:0] older;            // older[i][j]: entry j was in the queue before entry i and has not left
    logic [QD-1:0][QD-1:0] dep;            // dep[i][j]: entry j is older, to the same burst address, and one of the two is a write: i must wait for j
    logic [QD-1:0][WWID-1:0] waitc;

    logic [BW-1:0]  a_bank;
    logic [RW-1:0]  a_row;
    logic [CB-1:0]  a_col;
    ddr2_addrmap #(.MAP(MAP), .RW(RW), .BW(BW), .CB(CB)) u_map (.addr(req_addr), .bank(a_bank), .row(a_row), .col(a_col));

    // ------------------------------------------------------------------------------------------------ bank, bus and refresh timers: each counts the clocks still to wait; 0 = allowed
    localparam int CNW = 8;
    logic [NB-1:0]  open_q;
    logic [NB-1:0][RW-1:0] orow;
    logic [NB-1:0][CNW-1:0] c_col;             // ACTIVATE to column command (tRCD)
    logic [NB-1:0][CNW-1:0] c_pre;             // to PRECHARGE: tRAS from ACTIVATE, read-to-precharge, write recovery
    logic [NB-1:0][CNW-1:0] c_rc;             // ACTIVATE to ACTIVATE, same bank (tRC)
    logic [NB-1:0][CNW-1:0] c_rp;             // PRECHARGE to ACTIVATE or REFRESH (tRP, tRPA)
    logic [CNW-1:0] c_rrd;             // ACTIVATE to ACTIVATE, any bank
    logic [3:0][CNW-1:0] c_faw;              // one timer per recent ACTIVATE: at most four live
    logic [CNW-1:0] c_rd;              // next READ allowed (data bus and write-to-read turnaround)
    logic [CNW-1:0] c_wr;              // next WRITE allowed
    logic [CNW-1:0] c_rfc;             // after REFRESH
    logic [RFW-1:0] tick;
    logic [3:0]     debt;              // refreshes due and not yet issued
    logic           ref_latched;
    logic           wmode;           // direction being served: 1 write
    logic [4:0]     run_q;

    function automatic logic [CNW-1:0] dec(input logic [CNW-1:0] c);
        return (c == '0) ? '0 : c - CNW'(1);
    endfunction
    function automatic logic [CNW-1:0] ld(input logic [CNW-1:0] c, input int n);          // c after this clock, with a rule of n clocks starting now
        logic [CNW-1:0] d, m;
        d = dec(c);
        m = CNW'(n - 1);
        return (d > m) ? d : m;
    endfunction

    // ------------------------------------------------------------------------------------------------ decision (combinational)
    logic [QD-1:0]  avail, s_col, s_act, s_pre, s_sel, s_any;
    logic [QD-1:0]  retire_m;
    logic           forced, force_w, ref_want, ref_active, idle_ok;
    logic [IW-1:0]  force_i, sel_i, free_i;
    logic           sel_found, free_found;
    logic           faw_ok;
    logic [1:0]     faw_z;
    logic           cls;
    logic           av_r, av_w;
    logic [QW-1:0]   rd_cnt, wr_cnt;
    logic           pre_all_ok, any_open, all_rp_ok;
    logic [NB-1:0]  hitp, idle_pre_b;
    logic           idle_pre_f;
    logic [BW-1:0]  idle_pre_i;

    logic [QD-1:0]  conf;
    logic           d_v;
    logic [2:0]     d_op;
    logic [BW-1:0]  d_bank;
    logic [RW-1:0]  d_row;
    logic [CB-1:0]  d_col;
    logic [TW-1:0]  d_tag;
    logic [IW-1:0]  d_slot;

    always_comb begin
        // counts and availability
        rd_cnt = '0; wr_cnt = '0;
        for (int i = 0; i < QD; i++) begin
            if (v[i] && !w[i]) rd_cnt = rd_cnt + QW'(1);
            if (v[i] &&  w[i]) wr_cnt = wr_cnt + QW'(1);
        end
        for (int i = 0; i < QD; i++) avail[i] = v[i] && (dep[i] == '0);
        av_r = |(avail & ~w);
        av_w = |(avail &  w);

        // the oldest entry, forced when it has waited AGE_LIM clocks
        forced = 1'b0; force_i = '0; force_w = 1'b0;
        for (int i = 0; i < QD; i++)
            if (v[i] && (older[i] == '0) && (waitc[i] >= WWID'(AGE_LIM))) begin forced = 1'b1; force_i = IW'(i); force_w = w[i]; end

        // direction
        if (POLICY == 0) begin
            if (av_r && !av_w)       cls = 1'b0;
            else if (!av_r && av_w)  cls = 1'b1;
            else if (!av_r && !av_w) cls = wmode;
            else                     cls = wmode ? (wr_cnt > QW'(WR_LO)) : (wr_cnt >= QW'(WR_HI));
        end else begin
            if (av_r && !av_w)       cls = 1'b0;
            else if (!av_r && av_w)  cls = 1'b1;
            else if (!av_r && !av_w) cls = wmode;
            else                     cls = (run_q >= 5'(RUN_MAX)) ? !wmode : wmode;
        end
        if (forced) cls = force_w;

        // per-bank: is an available entry of the served direction waiting for the open row; any direction
        for (int b = 0; b < NB; b++) begin
            hitp[b] = 1'b0;
            idle_pre_b[b] = 1'b0;
        end
        for (int i = 0; i < QD; i++)
            if (avail[i] && open_q[q_bank[i]] && (orow[q_bank[i]] == q_row[i]) && (w[i] == cls)) hitp[q_bank[i]] = 1'b1;
        idle_pre_f = 1'b0; idle_pre_i = '0;
        for (int b = 0; b < NB; b++) begin
            logic any_hit;
            any_hit = 1'b0;
            for (int i = 0; i < QD; i++)
                if (avail[i] && (q_bank[i] == BW'(b)) && (orow[b] == q_row[i])) any_hit = 1'b1;
            idle_pre_b[b] = open_q[b] && (c_pre[b] == '0) && !any_hit;
            if (idle_pre_b[b] && !idle_pre_f) begin idle_pre_f = 1'b1; idle_pre_i = BW'(b); end
        end

        faw_ok = 1'b0; faw_z = 2'd0;
        for (int k = 3; k >= 0; k--) if (c_faw[k] == '0) begin faw_ok = 1'b1; faw_z = 2'(k); end

        // candidate commands of each entry
        for (int i = 0; i < QD; i++) begin
            logic [BW-1:0] b;
            logic hit, cand, is_f;
            b = q_bank[i];
            hit = open_q[b] && (orow[b] == q_row[i]);
            is_f = forced && (force_i == IW'(i));
            cand = avail[i] && (forced ? is_f : (w[i] == cls));
            s_col[i] = cand && hit && (c_col[b] == '0) && (w[i] ? (c_wr == '0) : (c_rd == '0));
            s_act[i] = cand && !open_q[b] && (c_rc[b] == '0) && (c_rp[b] == '0) && (c_rrd == '0) && faw_ok && (c_rfc == '0);
            s_pre[i] = cand && open_q[b] && !hit && (c_pre[b] == '0) && (is_f || !hitp[b]);
        end

        // refresh sequence
        any_open = |open_q;
        pre_all_ok = 1'b1; all_rp_ok = 1'b1;
        for (int b = 0; b < NB; b++) begin
            if (open_q[b] && (c_pre[b] != '0)) pre_all_ok = 1'b0;
            if (c_rp[b] != '0) all_rp_ok = 1'b0;
        end
        idle_ok = (POLICY == 0) ? (rd_cnt == '0) : (v == '0);
        ref_want = (debt != '0) && ((debt > 4'(REF_POST)) || (!ref_defer && idle_ok));
        ref_active = ref_latched || ref_want;

        // choose
        s_any = s_col | s_act | s_pre;
        if (POLICY == 1) s_sel = (|s_col) ? s_col : ((|s_act) ? s_act : s_pre);
        else             s_sel = s_any;
        sel_found = 1'b0; sel_i = '0;
        for (int i = 0; i < QD; i++)
            if (s_sel[i] && ((older[i] & s_sel) == '0)) begin sel_found = 1'b1; sel_i = IW'(i); end

        d_v = 1'b0; d_op = OP_NOP; d_bank = '0; d_row = '0; d_col = '0; d_tag = '0; d_slot = '0;
        if (en) begin
            if (ref_active) begin
                if (any_open && pre_all_ok) begin
                    d_v = 1'b1; d_op = OP_PREA;
                end else if (!any_open && all_rp_ok && (c_rfc == '0)) begin
                    d_v = 1'b1; d_op = OP_REF;
                end
            end else if (sel_found) begin
                d_v = 1'b1; d_slot = sel_i;
                d_bank = q_bank[sel_i]; d_row = q_row[sel_i]; d_col = q_col[sel_i]; d_tag = q_tag[sel_i];
                if (s_col[sel_i])      d_op = w[sel_i] ? OP_WR : OP_RD;
                else if (s_act[sel_i]) d_op = OP_ACT;
                else                   d_op = OP_PRE;
            end else if (POLICY == 0 && !forced && idle_pre_f) begin
                d_v = 1'b1; d_op = OP_PRE; d_bank = idle_pre_i;
            end
        end
        retire_m = '0;
        if (d_v && (d_op == OP_RD || d_op == OP_WR)) retire_m[d_slot] = 1'b1;

        // the older entries a new request must wait for
        conf = '0;
        for (int j = 0; j < QD; j++)
            conf[j] = v[j] && !retire_m[j] && (q_bank[j] == a_bank) && (q_row[j] == a_row) && (q_col[j] == a_col) && (w[j] || req_wr);

        // free slot
        free_found = 1'b0; free_i = '0;
        for (int i = QD - 1; i >= 0; i--) if (!v[i]) begin free_found = 1'b1; free_i = IW'(i); end
    end

    assign req_rdy = en && free_found;

    // ------------------------------------------------------------------------------------------------ state update
    always_ff @(posedge clk) begin
        // timers
        for (int b = 0; b < NB; b++) begin
            c_col[b] <= dec(c_col[b]); c_pre[b] <= dec(c_pre[b]); c_rc[b] <= dec(c_rc[b]); c_rp[b] <= dec(c_rp[b]);
        end
        c_rrd <= dec(c_rrd); c_rd <= dec(c_rd); c_wr <= dec(c_wr); c_rfc <= dec(c_rfc);
        for (int k = 0; k < 4; k++) c_faw[k] <= dec(c_faw[k]);

        // refresh timer: one refresh falls due every T_REFI clocks once en is high
        if (!en) begin
            tick <= RFW'(T_REFI - 1);
        end else if (tick == '0) begin
            tick <= RFW'(T_REFI - 1);
            if (debt != 4'd15) debt <= debt + 4'd1;
        end else begin
            tick <= tick - RFW'(1);
        end
        ref_latched <= ref_active && !(d_v && d_op == OP_REF);

        // issued command
        cmd_v <= d_v; cmd_op <= d_op; cmd_bank <= d_bank; cmd_row <= d_row; cmd_col <= d_col; cmd_tag <= d_tag;
        if (d_v) begin
            case (d_op)
                OP_ACT: begin
                    open_q[d_bank] <= 1'b1; orow[d_bank] <= d_row;
                    c_rc[d_bank] <= ld(c_rc[d_bank], T_RC);
                    c_col[d_bank] <= ld(c_col[d_bank], T_RCD);
                    c_pre[d_bank] <= ld(c_pre[d_bank], T_RAS);
                    c_rrd <= ld(c_rrd, T_RRD);
                    c_faw[faw_z] <= CNW'(T_FAW - 1);
                end
                OP_RD: begin
                    c_rd <= ld(c_rd, BL2);
                    c_wr <= ld(c_wr, RTW);
                    c_pre[d_bank] <= ld(c_pre[d_bank], R2P);
                end
                OP_WR: begin
                    c_wr <= ld(c_wr, BL2);
                    c_rd <= ld(c_rd, W2R);
                    c_pre[d_bank] <= ld(c_pre[d_bank], W2P);
                end
                OP_PRE: begin
                    open_q[d_bank] <= 1'b0;
                    c_rp[d_bank] <= ld(c_rp[d_bank], T_RP);
                end
                OP_PREA: begin
                    open_q <= '0;
                    for (int b = 0; b < NB; b++) c_rp[b] <= ld(c_rp[b], T_RPA);
                end
                OP_REF: begin
                    c_rfc <= CNW'(T_RFC - 1);
                    debt <= debt - 4'd1 + ((en && tick == '0 && debt != 4'd15) ? 4'd1 : 4'd0);
                end
                default: ;
            endcase
        end

        // direction and run length
        wmode <= cls;
        if (d_v && (d_op == OP_RD || d_op == OP_WR)) run_q <= (cls != wmode) ? 5'd1 : ((run_q == 5'd31) ? run_q : run_q + 5'd1);
        else if (cls != wmode) run_q <= 5'd0;

        // queue: waits, retire, enqueue
        for (int i = 0; i < QD; i++) begin
            if (v[i] && (waitc[i] < WWID'(AGE_LIM))) waitc[i] <= waitc[i] + WWID'(1);
            if (retire_m[i]) v[i] <= 1'b0;
            older[i] <= older[i] & ~retire_m;
            dep[i]   <= dep[i] & ~retire_m;
        end
        if (req_v && req_rdy) begin
            v[free_i] <= 1'b1; w[free_i] <= req_wr;
            q_bank[free_i] <= a_bank; q_row[free_i] <= a_row; q_col[free_i] <= a_col; q_tag[free_i] <= req_tag;
            older[free_i] <= v & ~retire_m;
            dep[free_i] <= conf;
            waitc[free_i] <= '0;
        end

        if (rst) begin
            v <= '0; w <= '0; open_q <= '0; debt <= '0; ref_latched <= 1'b0; wmode <= 1'b0; run_q <= '0;
            cmd_v <= 1'b0; cmd_op <= OP_NOP;
            c_rrd <= '0; c_rd <= '0; c_wr <= '0; c_rfc <= '0;
            for (int b = 0; b < NB; b++) begin c_col[b] <= '0; c_pre[b] <= '0; c_rc[b] <= '0; c_rp[b] <= '0; end
            for (int k = 0; k < 4; k++) c_faw[k] <= '0;
            for (int i = 0; i < QD; i++) begin older[i] <= '0; dep[i] <= '0; waitc[i] <= '0; end
        end
    end
endmodule
