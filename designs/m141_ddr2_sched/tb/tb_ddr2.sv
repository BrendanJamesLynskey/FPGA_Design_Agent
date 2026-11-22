// tb_ddr2.sv (brief 141): bench for ddr2_sched against a behavioural DDR2 timing model written from the Micron MT47H64M16 data sheet (Rev. AB 09/18), not from the RTL.
//
// The model keeps absolute-time stamps (the clock number of the last ACTIVATE, PRECHARGE, READ, WRITE and REFRESH of each bank) and checks every command on the bus against the rules in nanoseconds,
// converted to clocks here by its own ceiling function (tCK = 2.5 ns): the RTL's timers (down-counters in clocks) and the formal monitor (saturating ages) are different formulations of the same rules, so a
// wrong constant in one of them does not pass the others. It also checks the state rules (a column command needs the bank open on the request's row; ACTIVATE needs a closed bank; REFRESH needs every bank
// closed), the data-bus rules (no overlap of data bursts, one idle clock between a read burst and a write burst, tWTR after a write burst), the refresh obligation (the gap between REFRESH commands is at most
// 9 x tREFI, JEDEC's limit with 8 postponed) and request integrity (each request gets exactly one column command with its own bank, row, column and direction, in an order that keeps read-after-write,
// write-after-write and write-after-read order to the same burst address).
//
// Traffic (+PAT): 0 random reads, 1 random reads with a stream of writes (30 %), 2 sequential read stream, 3 read stream plus write stream (a copy), 4 bursts of reads at a random address followed by a
// quiet gap (trading-style bursts of related reads), 5 random read-modify-write on a small set of addresses (hazard stress).  +GAP = mean clocks between requests (0 = as fast as accepted).  +N = requests.
// +DEFER=1 holds ref_defer; +DEFERP=p +DEFERW=w makes it a window (high for the first w clocks of every p clocks after en).
// Output: one RESULT line, LAT lines (read latency in clocks, request accepted to first data beat, and 1 if ref_defer was high when the request was accepted), and VIOL lines for any violation.
`timescale 1ns/1ps
module tb_ddr2;
    parameter int POLICY   = 0;
    parameter int MAP      = 0;
    parameter int QD       = 8;
    parameter int REF_POST = 4;
    parameter int AGE_LIM  = 1024;
    parameter int WR_HI    = 6;
    parameter int WR_LO    = 1;
    parameter int RUN_MAX  = 16;
    parameter int TCK_PS   = 2500;    // the model's clock period; the DUT's timing parameters below must be those of this period (tests/m141_timing.py derives them)
    parameter int T_RCD = 6, T_RP = 6, T_RPA = 7, T_RAS = 16, T_RC = 22, T_RRD = 4, T_FAW = 20, T_WR = 6, T_WTR = 3, T_RTP = 3, T_RFC = 51, T_REFI = 3120, RL = 6, WL = 5, BL2 = 4;

    localparam int BW = 3, RW = 13, CB = 7, TW = 6;
    localparam int AWD = RW + BW + CB;

    // the model's own constants: picoseconds from the data sheet (-25 speed grade, x16), clocks by ceiling (the refresh interval by floor: refreshing early is safe)
    function automatic int cyc(input int ps);
        return (ps + TCK_PS - 1) / TCK_PS;
    endfunction
    localparam int M_RCD = cyc(15000), M_RP = cyc(15000), M_RPA = cyc(17500), M_RAS = cyc(40000), M_RC = cyc(55000), M_RRD = cyc(10000), M_FAW = cyc(50000);
    localparam int M_WR = cyc(15000), M_WTR = cyc(7500), M_RTP = cyc(7500), M_RFC = cyc(127500), M_REFI = 7800000 / TCK_PS;
    localparam int M_CL = RL, M_WL = RL - 1, M_BL2 = 4;

    logic clk = 1'b0, rst = 1'b1, en = 1'b0;
    always #(TCK_PS / 2000.0) clk = ~clk;

    logic                req_v = 1'b0, req_rdy, req_wr = 1'b0, ref_defer = 1'b0;
    logic [AWD-1:0]      req_addr = '0;
    logic [TW-1:0]       req_tag = '0;
    logic                cmd_v;
    logic [2:0]          cmd_op;
    logic [BW-1:0]       cmd_bank;
    logic [RW-1:0]       cmd_row;
    logic [CB-1:0]       cmd_col;
    logic [TW-1:0]       cmd_tag;

    ddr2_sched #(.POLICY(POLICY), .QD(QD), .MAP(MAP), .AGE_LIM(AGE_LIM), .WR_HI(WR_HI), .WR_LO(WR_LO), .RUN_MAX(RUN_MAX), .REF_POST(REF_POST),
                   .T_RCD(T_RCD), .T_RP(T_RP), .T_RPA(T_RPA), .T_RAS(T_RAS), .T_RC(T_RC), .T_RRD(T_RRD), .T_FAW(T_FAW), .T_WR(T_WR), .T_WTR(T_WTR), .T_RTP(T_RTP), .T_RFC(T_RFC), .T_REFI(T_REFI), .RL(RL), .WL(WL), .BL2(BL2)) dut (.*);

    localparam logic [2:0] OP_ACT = 3'd1, OP_RD = 3'd2, OP_WR = 3'd3, OP_PRE = 3'd4, OP_PREA = 3'd5, OP_REF = 3'd6;

    // ------------------------------------------------------------------ the DDR2 model
    longint now = 0;
    longint t_act [8], t_pre [8], t_rd [8], t_wr [8];
    int     pre_len [8];                                  // tRP, or tRPA after a PRECHARGE ALL
    logic   open_m [8];
    logic [RW-1:0] row_m [8];
    longint act_hist [4];
    longint last_act = -100000, last_ref = -100000, last_rd = -100000, last_wr = -100000, first_ref = -1;
    longint rd_data_end = -1, wr_data_end = -1;           // last clock of the last read / write data burst
    int     viol = 0;
    int     n_act = 0, n_rd = 0, n_wr = 0, n_ref = 0, n_pre = 0, n_prea = 0, n_turn = 0;
    logic   last_dir_wr = 1'b0, have_dir = 1'b0;                  // direction of the previous column command, for counting bus turnarounds
    longint max_ref_gap = 0;
    longint en_at = 0;

    task automatic fail(input string s);
        viol = viol + 1;
        if (viol <= 20) $display("VIOL @%0d: %s", now, s);
    endtask

    // request table by tag (the tags in flight are unique: at most QD < 64 outstanding)
    logic          t_live [64];
    logic          t_wrt  [64];
    logic [AWD-1:0] t_addr [64];
    longint        t_seq  [64];
    longint        t_acc  [64];
    logic          t_win  [64];                          // ref_defer was high when the request was accepted
    longint        seq_next = 0;
    int            n_acc = 0, n_done = 0, n_hazard = 0, n_badreq = 0;

    // read latency log
    int lat_n = 0;
    longint lat_sum = 0;
    int lat_max = 0;
    int wait_max = 0;                                     // the longest wait of any request, accepted to column command, in clocks

    // the address map, written again here from its description (ddr2_addrmap.sv header), so the map itself is checked too
    function automatic logic [BW+RW+CB-1:0] decode(input logic [AWD-1:0] a);
        logic [BW-1:0] bk; logic [RW-1:0] rw; logic [CB-1:0] cl;
        rw = a[AWD-1:CB+BW];
        if (MAP == 0) begin cl = a[CB-1:0]; bk = a[CB+BW-1:CB]; end
        else if (MAP == 1) begin cl = {a[CB+BW-1:3+BW], a[2:0]}; bk = a[3+BW-1:3]; end
        else begin bk = a[BW-1:0]; cl = a[CB+BW-1:BW]; end
        return {bk, rw, cl};
    endfunction

    task automatic check_pre_ok(input int b, input string who);
        if (now - t_act[b] < M_RAS)                      fail($sformatf("%s bank %0d: tRAS (%0d < %0d)", who, b, now - t_act[b], M_RAS));
        if (now - t_rd[b]  < (M_BL2 - 2 + (M_RTP > 2 ? M_RTP : 2))) fail($sformatf("%s bank %0d: tRTP", who, b));
        if (now - t_wr[b]  < (M_WL + M_BL2 + M_WR))      fail($sformatf("%s bank %0d: tWR", who, b));
    endtask

    always @(posedge clk) begin
        now <= now + 1;
        if (cmd_v) begin : chk
            int b;
            logic [BW+RW+CB-1:0] dec_v;
            b = int'(cmd_bank);
            if (now - last_ref < M_RFC && last_ref >= 0 && cmd_op != OP_REF) fail("command inside tRFC after REFRESH");
            case (cmd_op)
                OP_ACT: begin
                    n_act = n_act + 1;
                    if (open_m[b])                          fail($sformatf("ACT bank %0d already open", b));
                    if (now - t_pre[b] < pre_len[b])        fail($sformatf("ACT bank %0d: tRP/tRPA", b));
                    if (now - t_act[b] < M_RC)              fail($sformatf("ACT bank %0d: tRC", b));
                    if (now - last_act < M_RRD)             fail("ACT: tRRD");
                    if (now - act_hist[3] < M_FAW)          fail("ACT: tFAW (fifth ACTIVATE inside the window)");
                    if (now - last_ref < M_RFC)             fail("ACT: tRFC");
                    open_m[b] = 1'b1; row_m[b] = cmd_row; t_act[b] = now; last_act = now;
                    act_hist[3] = act_hist[2]; act_hist[2] = act_hist[1]; act_hist[1] = act_hist[0]; act_hist[0] = now;
                end
                OP_RD, OP_WR: begin
                    if (!t_live[cmd_tag]) begin fail("column command with a tag that is not in flight"); n_badreq = n_badreq + 1; end
                    else begin
                        dec_v = decode(t_addr[cmd_tag]);
                        if (t_wrt[cmd_tag] != (cmd_op == OP_WR) || dec_v[CB+RW+BW-1:CB+RW] != cmd_bank || dec_v[CB-1:0] != cmd_col) begin
                            fail($sformatf("column command does not match its request (tag %0d)", cmd_tag)); n_badreq = n_badreq + 1;
                        end
                        if (open_m[b] && row_m[b] != dec_v[CB+RW-1:CB]) begin
                            fail($sformatf("column command to bank %0d: the open row is not the request's row", b)); n_badreq = n_badreq + 1;
                        end
                        for (int t = 0; t < 64; t++)
                            if (t_live[t] && t != int'(cmd_tag) && t_addr[t] == t_addr[cmd_tag] && t_seq[t] < t_seq[cmd_tag] && (t_wrt[t] || t_wrt[cmd_tag])) begin
                                fail($sformatf("order: tag %0d overtook older tag %0d to the same address", cmd_tag, t)); n_hazard = n_hazard + 1;
                            end
                        if (int'(now - t_acc[cmd_tag]) > wait_max) wait_max = int'(now - t_acc[cmd_tag]);
                        t_live[cmd_tag] = 1'b0;
                        n_done = n_done + 1;
                    end
                    if (have_dir && last_dir_wr != (cmd_op == OP_WR)) n_turn = n_turn + 1;
                    last_dir_wr = (cmd_op == OP_WR); have_dir = 1'b1;
                    if (!open_m[b])                         fail($sformatf("column command to closed bank %0d", b));
                    if (now - t_act[b] < M_RCD)             fail($sformatf("column command bank %0d: tRCD", b));
                    if (cmd_op == OP_RD) begin
                        n_rd = n_rd + 1;
                        if (now - last_wr < M_WL + M_BL2 + M_WTR && last_wr >= 0) fail("READ: tWTR after the write burst");
                        if (now + M_CL <= rd_data_end)      fail("READ: data burst overlaps the previous read burst");
                        if (now + M_CL <= wr_data_end)      fail("READ: data burst overlaps the previous write burst");
                        rd_data_end = now + M_CL + M_BL2 - 1; t_rd[b] = now; last_rd = now;
                        begin
                            int l;
                            l = int'(now + M_CL - t_acc[cmd_tag]);
                            $display("LAT %0d %0d", l, t_win[cmd_tag]);
                            lat_n = lat_n + 1; lat_sum = lat_sum + l; if (l > lat_max) lat_max = l;
                        end
                    end else begin
                        n_wr = n_wr + 1;
                        if (now + M_WL <= wr_data_end)      fail("WRITE: data burst overlaps the previous write burst");
                        if (now + M_WL <= rd_data_end + 1)  fail("WRITE: data burst overlaps or touches the previous read burst (one idle clock needed)");
                        wr_data_end = now + M_WL + M_BL2 - 1; t_wr[b] = now; last_wr = now;
                    end
                end
                OP_PRE: begin
                    n_pre = n_pre + 1;
                    if (!open_m[b]) fail($sformatf("PRE bank %0d not open", b));
                    check_pre_ok(b, "PRE");
                    open_m[b] = 1'b0; t_pre[b] = now; pre_len[b] = M_RP;
                end
                OP_PREA: begin
                    n_prea = n_prea + 1;
                    for (int k = 0; k < 8; k++) begin
                        if (open_m[k]) check_pre_ok(k, "PREA");
                        open_m[k] = 1'b0; t_pre[k] = now; pre_len[k] = M_RPA;
                    end
                end
                OP_REF: begin
                    n_ref = n_ref + 1;
                    for (int k = 0; k < 8; k++) begin
                        if (open_m[k])                      fail($sformatf("REF with bank %0d open", k));
                        if (now - t_pre[k] < pre_len[k])    fail($sformatf("REF: tRP/tRPA bank %0d", k));
                    end
                    if (now - last_ref < M_RFC)             fail("REF: tRFC after the previous REFRESH");
                    if (first_ref >= 0 && now - last_ref > max_ref_gap) max_ref_gap = now - last_ref;
                    if (first_ref < 0) first_ref = now;
                    last_ref = now;
                end
                default: fail("unknown command");
            endcase
        end
        if (!rst && en && now - (last_ref >= 0 ? last_ref : en_at) > 9 * M_REFI) fail("refresh obligation: more than 9 x tREFI since the last REFRESH");
    end

    // ------------------------------------------------------------------ traffic
    int  pat = 0, gap = 40, nreq = 5000;
    int  defer_const = 0, defer_p = 0, defer_w = 0;       // ref_defer held (+DEFER=1) or a window: high for the first +DEFERW clocks of every +DEFERP clocks, counted from en
    always @(posedge clk) ref_defer <= (defer_p > 0) ? ((en && ((now - en_at) % defer_p) < defer_w) ? 1'b1 : 1'b0) : (defer_const != 0);
    logic [31:0] rs = 32'h2545F491;
    function automatic logic [31:0] xs(input logic [31:0] s);
        logic [31:0] x;
        x = s; x ^= x << 13; x ^= x >> 17; x ^= x << 5;
        return x;
    endfunction
    task automatic rnd(output logic [31:0] r);
        rs = xs(rs); r = rs;
    endtask

    int  sent = 0, wait_gap = 0, burst_left = 0;
    logic [AWD-1:0] seq_r = '0, seq_w = '0 | 23'h200000, burst_base = '0;
    logic next_is_wr = 1'b0;
    logic [AWD-1:0] hot [16];
    longint done_at = 0;
    longint start_at = 0;

    // build the next request into (nx_*)
    logic nx_wr; logic [AWD-1:0] nx_addr;
    task automatic make_request;
        logic [31:0] r1, r2;
        rnd(r1); rnd(r2);
        case (pat)
            0: begin nx_wr = 1'b0; nx_addr = r1[AWD-1:0]; end
            1: begin nx_wr = (r2 % 10) < 3; nx_addr = r1[AWD-1:0]; end
            2: begin nx_wr = 1'b0; nx_addr = seq_r; seq_r = seq_r + 1; end
            3: begin
                next_is_wr = ~next_is_wr;
                nx_wr = next_is_wr;
                if (next_is_wr) begin nx_addr = seq_w; seq_w = seq_w + 1; end else begin nx_addr = seq_r; seq_r = seq_r + 1; end
            end
            4: begin
                nx_wr = 1'b0;
                if (burst_left == 0) begin burst_base = r1[AWD-1:0]; burst_left = 4 + int'(r2 % 5); end
                nx_addr = burst_base + AWD'(burst_left & 3);   // reads near each other: same row, nearby columns
                burst_left = burst_left - 1;
            end
            default: begin nx_wr = (r2 % 2) == 0; nx_addr = hot[r1 % 16]; end
        endcase
    endtask

    // a tag no request in the queue holds (the scheduler returns the tag with the column command; tags must be unique among outstanding requests, which is the user's duty)
    function automatic logic [TW-1:0] pick_tag();
        for (int t = 0; t < 64; t++) if (!t_live[t]) return TW'(t);
        return '0;
    endfunction

    always @(posedge clk) if (!rst) begin
        // a request handshake
        if (req_v && req_rdy) begin
            t_live[req_tag] = 1'b1; t_wrt[req_tag] = req_wr; t_addr[req_tag] = req_addr; t_seq[req_tag] = seq_next; t_acc[req_tag] = now; t_win[req_tag] = ref_defer;
            seq_next = seq_next + 1; n_acc = n_acc + 1;
            req_v <= 1'b0;
            sent = sent + 1;
            if (gap > 0) begin
                logic [31:0] g; rnd(g);
                wait_gap = int'(g % (2 * gap)) ;
                if (pat == 4 && burst_left == 0) wait_gap = 4 * gap + int'(g % (4 * gap));
            end else wait_gap = 0;
        end else if (!req_v && sent < nreq) begin
            if (wait_gap > 0) wait_gap = wait_gap - 1;
            else begin
                make_request;
                req_v <= 1'b1; req_wr <= nx_wr; req_addr <= nx_addr; req_tag <= pick_tag();
            end
        end
    end

    // ------------------------------------------------------------------ run
    initial begin : main
        string p;
        for (int k = 0; k < 8; k++) begin t_act[k] = -100000; t_pre[k] = -100000; t_rd[k] = -100000; t_wr[k] = -100000; open_m[k] = 1'b0; pre_len[k] = M_RP; row_m[k] = '0; end
        for (int k = 0; k < 4; k++) act_hist[k] = -100000;
        for (int k = 0; k < 64; k++) begin t_live[k] = 1'b0; t_wrt[k] = 1'b0; t_addr[k] = '0; t_seq[k] = 0; t_acc[k] = 0; end
        for (int k = 0; k < 16; k++) hot[k] = AWD'(k * 32'h1357 + 5);
        if ($value$plusargs("PAT=%d", pat)) ;
        if ($value$plusargs("GAP=%d", gap)) ;
        if ($value$plusargs("N=%d", nreq)) ;
        if ($value$plusargs("SEED=%d", rs)) ;
        if ($value$plusargs("DEFER=%d", defer_const)) ;
        if ($value$plusargs("DEFERP=%d", defer_p)) ;
        if ($value$plusargs("DEFERW=%d", defer_w)) ;
        repeat (4) @(posedge clk);
        rst <= 1'b0;
        repeat (4) @(posedge clk);
        en <= 1'b1;
        en_at = now;
        start_at = now;
        wait (sent == nreq && n_done == nreq);
        repeat (2) @(posedge clk);
        done_at = now;
        $display("RESULT policy=%0d map=%0d pat=%0d gap=%0d n=%0d clocks=%0d reads=%0d writes=%0d act=%0d pre=%0d prea=%0d ref=%0d lat_mean_x100=%0d lat_max=%0d violations=%0d hazards=%0d badreq=%0d max_ref_gap=%0d wait_max=%0d refpost=%0d turn=%0d",
                 POLICY, MAP, pat, gap, nreq, done_at - start_at, n_rd, n_wr, n_act, n_pre, n_prea, n_ref, (lat_n > 0 ? (lat_sum * 100) / lat_n : 0), lat_max, viol, n_hazard, n_badreq, max_ref_gap, wait_max, REF_POST, n_turn);
        if (viol == 0 && n_badreq == 0) $display("PASS"); else $display("FAIL");
        $finish;
    end

    // watchdog in clocks: a run that does not finish (a deadlocked scheduler, or a mutant that never serves a request) fails instead of running on
    always @(posedge clk) if (!rst && now > longint'(nreq) * (2 * gap + 400) + 60000) begin
        $display("TIMEOUT sent=%0d done=%0d", sent, n_done);
        $display("FAIL");
        $finish;
    end
endmodule
