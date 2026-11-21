`timescale 1ps/1ps
// tb_bp_ctl.sv (brief 96F1b): the reset drive and the alignment timeout/retry of gt_bp_ctl with AMD's own buffer-bypass controllers (the Wizard's generated sources, compiled by run.sh, NOT committed)
// against a STAND-IN transceiver (as tb_bp_seq.sv of 96F1: after TXDLYSRESET / RXDLYSRESET it drops SYNCDONE and PHALIGNDONE and raises them again SYNC_CLKS clocks later; the real alignment time is not a
// measured figure). The stand-in can ignore a given number of start pulses (withhold), which is how a hung alignment is made.
// By default the timeouts are scaled (TTO = 6000, RTO = 26000 clocks, the 30 : 130 ratio of the real values) so that every case runs in seconds; with -d FULL the instances take the module defaults
// (30 ms = 4,833,984 TXUSRCLK2 clocks) and one case runs: a TX alignment (30 ms) and an RX alignment (130 ms) that each hang once and are recovered by the retry.
//  A. reset drive: asynchronous assert (the reset rises within 100 ps of the clock-active level falling, with no clock edge), synchronous release (it falls only right after a clock edge, at least 3 clocks after the level rises).
//  B. normal start: done, no error, run, no retry, no gave-up, and the timer never fires over 2 timeouts.
//  C. one hung attempt: the timeout fires TTO clocks (+- 3) after the reset helper's done, the controller is reset for RST_CLKS clocks, restarts by itself, done, retries = 1, run only afterwards.
//  D. retries 2 (TX) and 3 (RX = MAX_RETRIES): done after the last permitted retry, no gave-up.
//  E. never aligns: retries = 3, gave_up = 1, run stays low, no more resets after the give-up; a new reset sequence (reset helper's done low then high) clears both and the next attempt works.
//  F. error (PHALIGNDONE never high): not retried, run low, error held, retries 0, gave_up 0.
//  G. the user clock going inactive in the middle of a hung attempt restarts the timer and the retry count; the first timeout after it comes a full TTO later.
//  E also covers a controller that hung and is NOT given up on: the next reset sequence must un-hang it (the controller only starts from idle).
//  H. run is never high without a finished alignment of the current sequence in every case.
module tb_bp_ctl;
`ifdef FULL
    localparam int TTO = 4_833_984, RTO = 20_947_266;
`else
    localparam int TTO = 6000, RTO = 26000;
`endif
    localparam int MAXR = 3, RSTC = 8;
    int SYNC_CLKS = 60;
    logic txclk = 0, rxclk = 0;
    always #3103 txclk = ~txclk;          // 161.13 MHz
    always #3100 rxclk = ~rxclk;
    // ---------------- TX side
    logic t_act = 0, t_rstdone = 0, t_phdone = 1, t_syncdone = 1, t_done, t_err, t_run, t_brst, t_gu;
    logic [3:0] t_rty;
    logic [0:0] t_dlysreset;
    gt_bp_ctl #(.TIMEOUT_CLKS(TTO), .MAX_RETRIES(MAXR), .RST_CLKS(RSTC)) u_ct (.clk(txclk), .clk_active(t_act), .rst_done(t_rstdone), .bp_done(t_done), .bp_err(t_err),
        .bp_reset(t_brst), .run(t_run), .retries(t_rty), .gave_up(t_gu));
    gtwizard_ultrascale_v1_7_23_gtwiz_buffbypass_tx #(.P_BUFFER_BYPASS_MODE(0), .P_TOTAL_NUMBER_OF_CHANNELS(1), .P_MASTER_CHANNEL_POINTER(0)) u_tx (
        .gtwiz_buffbypass_tx_clk_in(txclk), .gtwiz_buffbypass_tx_reset_in(t_brst), .gtwiz_buffbypass_tx_start_user_in(1'b0), .gtwiz_buffbypass_tx_resetdone_in(t_rstdone),
        .gtwiz_buffbypass_tx_done_out(t_done), .gtwiz_buffbypass_tx_error_out(t_err),
        .txphaligndone_in(t_phdone), .txphinitdone_in(1'b0), .txdlysresetdone_in(1'b0), .txsyncout_in(1'b0), .txsyncdone_in(t_syncdone),
        .txphdlyreset_out(), .txphalign_out(), .txphalignen_out(), .txphdlypd_out(), .txphinit_out(), .txphovrden_out(), .txdlysreset_out(t_dlysreset), .txdlybypass_out(),
        .txdlyen_out(), .txdlyovrden_out(), .txphdlytstclk_out(), .txdlyhold_out(), .txdlyupdown_out(), .txsyncmode_out(), .txsyncallin_out(), .txsyncin_out());
    // ---------------- RX side
    logic r_act = 0, r_rstdone = 0, r_phdone = 1, r_syncdone = 1, r_done, r_err, r_run, r_brst, r_gu;
    logic [3:0] r_rty;
    logic [0:0] r_dlysreset;
    gt_bp_ctl #(.TIMEOUT_CLKS(RTO), .MAX_RETRIES(MAXR), .RST_CLKS(RSTC)) u_cr (.clk(rxclk), .clk_active(r_act), .rst_done(r_rstdone), .bp_done(r_done), .bp_err(r_err),
        .bp_reset(r_brst), .run(r_run), .retries(r_rty), .gave_up(r_gu));
    gtwizard_ultrascale_v1_7_23_gtwiz_buffbypass_rx #(.P_BUFFER_BYPASS_MODE(0), .P_TOTAL_NUMBER_OF_CHANNELS(1), .P_MASTER_CHANNEL_POINTER(0)) u_rx (
        .gtwiz_buffbypass_rx_clk_in(rxclk), .gtwiz_buffbypass_rx_reset_in(r_brst), .gtwiz_buffbypass_rx_start_user_in(1'b0), .gtwiz_buffbypass_rx_resetdone_in(r_rstdone),
        .gtwiz_buffbypass_rx_done_out(r_done), .gtwiz_buffbypass_rx_error_out(r_err),
        .rxphaligndone_in(r_phdone), .rxdlysresetdone_in(1'b0), .rxsyncout_in(1'b0), .rxsyncdone_in(r_syncdone),
        .rxphdlyreset_out(), .rxphalign_out(), .rxphalignen_out(), .rxphdlypd_out(), .rxphovrden_out(), .rxdlysreset_out(r_dlysreset), .rxdlybypass_out(),
        .rxdlyen_out(), .rxdlyovrden_out(), .rxsyncmode_out(), .rxsyncallin_out(), .rxsyncin_out());
    // ---------------- transceiver stand-in: ignores the next t_withhold / r_withhold start pulses (alignment never completes), PHALIGNDONE never rises in the error mode
    int t_withhold = 0, r_withhold = 0;
    logic t_err_mode = 0, r_err_mode = 0;
    always @(posedge t_dlysreset) begin
        t_syncdone <= 1'b0; t_phdone <= 1'b0;
        if (t_withhold > 0) t_withhold--;
        else begin repeat (SYNC_CLKS) @(posedge txclk); t_syncdone <= 1'b1; t_phdone <= !t_err_mode; end
    end
    always @(posedge r_dlysreset) begin
        r_syncdone <= 1'b0; r_phdone <= 1'b0;
        if (r_withhold > 0) r_withhold--;
        else begin repeat (SYNC_CLKS) @(posedge rxclk); r_syncdone <= 1'b1; r_phdone <= !r_err_mode; end
    end
    // the reset's release must coincide with a rising clock edge (posedge of txclk: 3103 + 6206 k ps; rxclk: 3100 + 6200 k ps)
    logic t_rel_sync = 1'b0, r_rel_sync = 1'b0;
    always @(negedge t_brst) if (t_act) t_rel_sync = (($time - 3103) % 6206) == 0;
    always @(negedge r_brst) if (r_act) r_rel_sync = (($time - 3100) % 6200) == 0;
    // ---------------- monitors (clock counts per direction; the reset-pulse edges that are not the clock-inactive reset)
    int errors = 0, checks = 0;
    int tn = 0, rn = 0;                                         // clock counts
    int t_c0 = 0, r_c0 = 0;                                     // count at the last rising edge of the reset helper's done
    int t_rise[$], t_fall[$], r_rise[$], r_fall[$];             // counts of bp_reset edges since the last reset-done rise
    int t_early = 0, r_early = 0;
    logic t_restarted = 0, r_restarted = 0, t_q = 0, r_q = 0, t_bq = 0, r_bq = 0;
    always @(posedge txclk) begin
        tn <= tn + 1;
        t_q <= t_rstdone; t_bq <= t_brst;
        if (t_rstdone && !t_q) begin t_c0 = tn; t_rise.delete(); t_fall.delete(); end
        if (t_rstdone && t_act) begin if (t_brst && !t_bq) t_rise.push_back(tn); if (!t_brst && t_bq && t_rise.size() > 0) t_fall.push_back(tn); end
        if (!t_rstdone) t_restarted <= 0; else if (!t_done) t_restarted <= 1;
        if (t_run && !(t_rstdone && t_done && t_restarted && !t_err)) t_early++;
    end
    always @(posedge rxclk) begin
        rn <= rn + 1;
        r_q <= r_rstdone; r_bq <= r_brst;
        if (r_rstdone && !r_q) begin r_c0 = rn; r_rise.delete(); r_fall.delete(); end
        if (r_rstdone && r_act) begin if (r_brst && !r_bq) r_rise.push_back(rn); if (!r_brst && r_bq && r_rise.size() > 0) r_fall.push_back(rn); end
        if (!r_rstdone) r_restarted <= 0; else if (!r_done) r_restarted <= 1;
        if (r_run && !(r_rstdone && r_done && r_restarted && !r_err)) r_early++;
    end
    task automatic check(input string what, input bit ok);
        checks++;
        if (!ok) begin errors++; $display("FAIL: %s (t=%0t)", what, $time); end else $display("ok:   %s", what);
    endtask
    task automatic idle(input int n);
        repeat (n) @(posedge txclk);
    endtask
    // the reset helpers finish (the controllers must start by themselves), then wait `n` TX clocks
    task automatic helpers_done(input int n);
        @(posedge txclk); t_rstdone <= 1'b1; @(posedge rxclk); r_rstdone <= 1'b1;
        idle(n);
    endtask
    task automatic new_sequence();         // a GT reset: the reset helpers' done drops (clears retries and gave-up), the clocks stay active
        @(posedge txclk); t_rstdone <= 1'b0; @(posedge rxclk); r_rstdone <= 1'b0;
        idle(30);
    endtask
    function automatic bit near(input int a, input int b, input int tol);
        return (a > b ? a - b : b - a) <= tol;
    endfunction
    initial begin
        int d, sp;
        time tfall, trise;
        repeat (200) #1000;                         // glbl.GSR (100 ns) holds the XPM models until it ends
        // ---------------- A: reset drive
        check("A reset is asserted while the clock-active level is low", t_brst && r_brst);
        t_rstdone = 1'b1; r_rstdone = 1'b1;               // (the controller is also held in reset while the reset helper's done is low: keep it high here so that only the clock-active level is under test)
        // release: the level rises at an arbitrary time (1.37 ns after a clock edge), the reset must fall only just after a clock edge and several clocks later
        @(posedge txclk); #1370; trise = $time; t_act = 1'b1;
        sp = 0; while (t_brst && sp < 20) begin @(posedge txclk); sp++; end
        check($sformatf("A synchronous release: TX reset fell %0d clocks after the level rose (4 flops)", sp), sp >= 3 && sp <= 6);
        check("A the TX reset fell exactly on a TXUSRCLK2 rising edge (not between edges)", t_rel_sync);
        @(posedge rxclk); #1370; r_act = 1'b1;
        sp = 0; while (r_brst && sp < 20) begin @(posedge rxclk); sp++; end
        check($sformatf("A synchronous release: RX reset fell %0d clocks after the level rose", sp), sp >= 3 && sp <= 6);
        check("A the RX reset fell exactly on a RXUSRCLK2 rising edge", r_rel_sync);
        // asynchronous assert: drop the level 0.9 ns after an edge; the reset must be high within 100 ps, with no clock edge in between
        @(posedge txclk); #900; tfall = $time; t_act = 1'b0; #100;
        check("A asynchronous assert: TX reset high within 100 ps of the level falling (no clock edge)", t_brst && ($time - tfall) <= 100);
        @(posedge rxclk); #900; tfall = $time; r_act = 1'b0; #100;
        check("A asynchronous assert: RX reset high within 100 ps", r_brst && ($time - tfall) <= 100);
        // ---------------- B: normal start
        t_act = 1'b1; r_act = 1'b1; idle(20);
        new_sequence();
        t_early = 0; r_early = 0; t_withhold = 0; r_withhold = 0; SYNC_CLKS = 60;
        helpers_done(60 + 40);
        check("B normal start: done, no error, run, no retry, no gave-up", t_done && !t_err && t_run && t_rty == 0 && !t_gu && r_done && !r_err && r_run && r_rty == 0 && !r_gu);
`ifdef FULL
        goto_full();
`else
        idle(2 * RTO + 100);
        check("B the timer never fires once aligned (no retry, no further reset, still running)", t_run && r_run && t_rty == 0 && r_rty == 0 && t_rise.size() == 0 && r_rise.size() == 0);
        check("B run never early", t_early == 0 && r_early == 0);
        new_sequence();
        // ---------------- C: one hung attempt on each side
        t_early = 0; r_early = 0; t_withhold = 1; r_withhold = 1;
        helpers_done(TTO + 20 * RSTC + 200);
        check($sformatf("C TX: reset pulse rose %0d clocks after the reset helper's done (timeout %0d)", t_rise.size() ? t_rise[0] - t_c0 : -1, TTO), t_rise.size() >= 1 && near(t_rise[0] - t_c0, TTO, 3));
        check($sformatf("C TX: controller held in reset %0d clocks (RST_CLKS %0d)", t_fall.size() ? t_fall[0] - t_rise[0] : -1, RSTC), t_fall.size() >= 1 && near(t_fall[0] - t_rise[0], RSTC, 1));
        check("C TX: one reset only, retries = 1, done, run, no gave-up", t_rise.size() == 1 && t_rty == 1 && t_done && !t_err && t_run && !t_gu);
        check("C TX: the run was never released before the retry's alignment finished", t_early == 0);
        idle(RTO);
        check($sformatf("C RX: reset pulse %0d clocks after the reset helper's done (timeout %0d)", r_rise.size() ? r_rise[0] - r_c0 : -1, RTO), r_rise.size() >= 1 && near(r_rise[0] - r_c0, RTO, 3));
        check("C RX: one reset only, retries = 1, done, run, no gave-up", r_rise.size() == 1 && r_rty == 1 && r_done && !r_err && r_run && !r_gu && r_early == 0);
        // ---------------- D: two retries on TX, MAX_RETRIES on RX: still succeeds
        new_sequence();
        check("D a new reset sequence clears the retry counts and the gave-up flags", t_rty == 0 && r_rty == 0 && !t_gu && !r_gu && !t_run && !r_run);
        t_early = 0; r_early = 0; t_withhold = 2; r_withhold = MAXR;
        helpers_done(RTO * (MAXR + 1) + 20 * RSTC * (MAXR + 1) + 200);
        check("D TX: two retries, then done and run, no gave-up", t_rty == 2 && t_done && t_run && !t_gu && t_rise.size() == 2);
        check($sformatf("D RX: %0d retries (the maximum), then done and run, no gave-up", MAXR), r_rty == MAXR && r_done && r_run && !r_gu && r_rise.size() == MAXR && r_early == 0 && t_early == 0);
        check("D RX: successive resets are RTO + RST_CLKS clocks apart", r_rise.size() == MAXR && near(r_rise[1] - r_rise[0], RTO + RSTC, 3) && near(r_rise[2] - r_rise[1], RTO + RSTC, 3));
        // ---------------- E: never aligns
        new_sequence();
        t_early = 0; r_early = 0; t_withhold = 999; r_withhold = 999;
        helpers_done(RTO * (MAXR + 1) + 20 * RSTC * (MAXR + 1) + 400);
        check($sformatf("E TX: retries = %0d, gave_up, no run, done low", MAXR), t_rty == MAXR && t_gu && !t_run && !t_done && t_rise.size() == MAXR);
        check($sformatf("E RX: retries = %0d, gave_up, no run, done low", MAXR), r_rty == MAXR && r_gu && !r_run && !r_done && r_rise.size() == MAXR);
        d = t_rise.size() + r_rise.size();
        idle(3 * RTO);
        check("E after the give-up: no further resets, the flags stay, run stays low", t_rise.size() + r_rise.size() == d && t_gu && r_gu && !t_run && !r_run && t_early == 0 && r_early == 0);
        new_sequence();
        check("E the next reset sequence clears retries and gave-up", t_rty == 0 && r_rty == 0 && !t_gu && !r_gu);
        t_withhold = 0; r_withhold = 0;
        helpers_done(60 + 60);
        check("E and the next attempt works (done, run, no retry)", t_done && r_done && t_run && r_run && t_rty == 0 && r_rty == 0);
        // ---------------- F: error is not retried
        new_sequence();
        t_early = 0; r_early = 0; t_err_mode = 1; r_err_mode = 1;
        helpers_done(RTO + 300);
        check("F error (PHALIGNDONE never high): done and error, no run, not retried, no gave-up",
              t_done && t_err && !t_run && t_rty == 0 && !t_gu && t_rise.size() == 0 && r_done && r_err && !r_run && r_rty == 0 && !r_gu && r_rise.size() == 0 && t_early == 0 && r_early == 0);
        new_sequence(); t_err_mode = 0; r_err_mode = 0;
        // ---------------- G: the user clock going inactive in the middle of a hung attempt
        t_withhold = 999; r_withhold = 999;
        helpers_done(TTO / 2);
        @(posedge txclk); t_act <= 1'b0; t_rstdone <= 1'b0; @(posedge rxclk); r_act <= 1'b0; r_rstdone <= 1'b0; idle(20);
        check("G the clock-inactive reset clears retries and gave-up and holds the controller in reset", t_rty == 0 && r_rty == 0 && !t_gu && !r_gu && t_brst && r_brst);
        t_withhold = 1; r_withhold = 1;
        @(posedge txclk); t_act <= 1'b1; @(posedge rxclk); r_act <= 1'b1; idle(20);
        helpers_done(TTO + 20 * RSTC + 200);
        check($sformatf("G the first timeout after the restart came %0d clocks after the reset helper's done (a full TTO %0d, not the half already waited)", t_rise.size() ? t_rise[0] - t_c0 : -1, TTO), t_rise.size() == 1 && near(t_rise[0] - t_c0, TTO, 3) && t_run && t_rty == 1);
        // ---------------- start of a retry racing the reset helper: the reset helper's done drops while a retry reset is being held
        new_sequence();
        t_withhold = 1; r_withhold = 0;
        helpers_done(TTO + 3);                      // inside the retry pulse
        new_sequence();
        t_withhold = 0;
        helpers_done(60 + 60);
        check("G a GT reset during a retry pulse: the next sequence is clean (done, run, no retry)", t_done && t_run && t_rty == 0 && !t_gu);
`endif
        $display("%s: %0d checks, %0d failed", errors == 0 ? "PASS" : "FAIL", checks, errors);
        $finish;
    end
`ifdef FULL
    // one case at the real values: the TX alignment (30 ms) and the RX alignment (130 ms) each hang once, the retry recovers them
    task automatic goto_full();
        new_sequence();
        t_early = 0; r_early = 0; t_withhold = 1; r_withhold = 1;
        helpers_done(RTO + 300);
        check($sformatf("FULL TX: the timeout fired %0d clocks after the reset helper's done (30 ms = %0d clocks at 161.1328125 MHz)", t_rise.size() ? t_rise[0] - t_c0 : -1, TTO), t_rise.size() == 1 && near(t_rise[0] - t_c0, TTO, 3));
        check("FULL TX: retry recovered: retries = 1, done, run, no gave-up", t_rty == 1 && t_done && t_run && !t_gu && t_early == 0);
        check($sformatf("FULL RX: the timeout fired %0d clocks after the reset helper's done (130 ms = %0d clocks at 161.1328125 MHz)", r_rise.size() ? r_rise[0] - r_c0 : -1, RTO), r_rise.size() == 1 && near(r_rise[0] - r_c0, RTO, 3));
        check("FULL RX: retry recovered: retries = 1, done, run, no gave-up", r_rty == 1 && r_done && r_run && !r_gu && r_early == 0);
        $display("INFO: FULL RX timeout = %0d clocks = %0.3f ms at the nominal 6.2061 ns clock (the bench RX clock is 6.2000 ns)", r_rise[0] - r_c0, (r_rise[0] - r_c0) * 6.2061e-6);
        $display("INFO: FULL TX timeout = %0d clocks = %0.3f ms at the 6.2061 ns clock", t_rise[0] - t_c0, (t_rise[0] - t_c0) * 6.2061e-6);
    endtask
`endif
endmodule
