// tb_timer (brief 69): black-box probes of AMD AXI Timer 2.0 (two 32-bit timers), Vivado 2026.1 xsim.
`timescale 1ns/1ps
module tb_timer;
`include "probe_common.svh"
    wire irq, gen0, gen1, pwm0;
    logic cap0 = 1'b0, cap1 = 1'b0;
    dut_timer u_dut (
        .capturetrig0(cap0), .capturetrig1(cap1), .generateout0(gen0), .generateout1(gen1), .pwm0(pwm0),
        .interrupt(irq), .freeze(1'b0),
        .s_axi_aclk(aclk), .s_axi_aresetn(aresetn),
        .s_axi_awaddr(awaddr[4:0]), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr[4:0]), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready));
    localparam [4:0] TCSR0 = 5'h00, TLR0 = 5'h04, TCR0 = 5'h08, TCSR1 = 5'h10, TLR1 = 5'h14, TCR1 = 5'h18;
    localparam logic [31:0] ENT = 32'h80, LOAD = 32'h20, ARHT = 32'h10, ENIT = 32'h40, T0INT = 32'h100, UDT = 32'h2, CASC = 32'h800;
    task automatic wait_clks(input int n); repeat (n) @(posedge aclk); endtask
    logic [31:0] a, b, c, v; string s; int i, j, n, k;
    // interrupt-output edge log
    int unsigned irq_rise = 0, irq_fall = 0; logic irq_q = 1'b0;
    always @(posedge aclk) begin irq_q <= irq; if (irq && !irq_q) irq_rise <= cyc; if (!irq && irq_q) irq_fall <= cyc; end
    int Er, dstar, fall_lag; int unsigned u_e, u_c;

    initial begin
        do_reset(4);
        // ---- reset values, every word of the 32-byte window
        s = "";
        for (i = 0; i < 8; i++) begin rdv(4 * i, v); s = {s, $sformatf("o%02x=%s/%s ", 4 * i, hexs(v), rname(last_resp))}; end
        rep("reset_values_window_scan", s);
        // ---- reserved words 0x0C, 0x1C: read, write, then check nothing else moved
        wr(5'h0C, 32'hFFFF_FFFF); a = last_resp; wr(5'h1C, 32'hFFFF_FFFF); b = last_resp;
        s = ""; for (i = 0; i < 8; i++) begin rdv(4 * i, v); s = {s, $sformatf("o%02x=%s ", 4 * i, hexs(v))}; end
        rep("reserved_words_write", $sformatf("write_0x0C=%s write_0x1C=%s after: %s", rname(a[1:0]), rname(b[1:0]), s));
        // ---- TCSR0 bits: write each single bit from reset and read back
        s = ""; n = 0;
        for (i = 0; i < 32; i++) begin
            do_reset(3); wr(TCSR0, 32'h1 << i); rdv(TCSR0, v);
            if (i < 12) s = {s, $sformatf("b%0d->%s ", i, hexs(v))};
            else if (v != 0) n++;
        end
        do_reset(3);
        rep("tcsr0_single_bit_writes", {$sformatf("bits31_12_that_read_back_nonzero=%0d ", n), s});
        // write ones to TLR0
        wr(TLR0, 32'hFFFF_FFFF); rdv(TLR0, a); wr(TCR0, 32'hFFFF_FFFF); rdv(TCR0, b);
        rep("tlr_tcr_write", $sformatf("TLR0=%s TCR0_after_write=%s", hexs(a), hexs(b)));
        do_reset(3);
        // ---- generate mode, auto reload, up counter: load and run; T0INT sets at rollover; measure the period
        wr(TLR0, 32'hFFFF_FFC0); wr(TCSR0, LOAD | ARHT); rdv(TCR0, a);
        rep("load_visible", $sformatf("TLR0=0xFFFFFFC0 after LOAD TCR0=%s", hexs(a)));
        wr(TCSR0, ARHT | ENT | ENIT); wait_clks(200);
        rdv(TCSR0, a); rep("rollover_flag", $sformatf("TCSR0=%s irq=%0d", hexs(a), irq));
        wr(TCSR0, ARHT | ENT | ENIT | T0INT); rdv(TCSR0, b);
        rep("t0int_write1_clears", $sformatf("wrote_%s TCSR0=%s", hexs(ARHT | ENT | ENIT | T0INT), hexs(b)));
        wait_clks(200); rdv(TCSR0, a); rep("t0int_sets_again_autoreload", $sformatf("TCSR0=%s", hexs(a)));
        wr(TCSR0, ARHT | ENT | ENIT);  rdv(TCSR0, b);
        rep("t0int_write0_no_change", $sformatf("wrote_0_to_bit8 TCSR0=%s", hexs(b)));
        wr(TCSR0, ARHT | ENT | ENIT | T0INT);
        // ---- irq is a level while T0INT && ENIT0
        wait_clks(100); a = irq; rdv(TCSR0, b); c = irq; wr(TCSR0, ARHT | ENT | T0INT); wait_clks(4); v = irq;
        rep("irq_level", $sformatf("irq_with_T0INT=%0d after_read=%0d ENIT0_cleared_T0INT_cleared=%0d", a, c, v));
        // ---- same-clock race: software clear of T0INT against the hardware rollover that sets it. One-shot generate mode
        //      (ARHT = 0), counter loaded with 0xFFFFFFFF - K and started by a TCSR0 write whose write-data handshake edge
        //      is wcyc_e; the rollover is then a fixed number of clocks after wcyc_e. A clear (write 1 to T0INT) is timed so
        //      that its handshake edge is D clocks after wcyc_e. Flag after = 1: the event survived; 0: it was cleared.
        do_reset(3);
        wr(TLR0, 32'hFFFF_FFFF - 50); wr(TCSR0, LOAD); wr(TCSR0, ENT | ENIT); u_e = wcyc;
        wait_clks(120); rdv(TCSR0, a);
        Er = int'(irq_rise) - int'(u_e);
        rep("rollover_timing", $sformatf("K=50 irq_rise_minus_start_W_edge=%0d flag=%s", Er, hexs(a)));
        s = ""; dstar = 0;
        for (j = Er - 7; j <= Er + 7; j++) begin
            do_reset(3);
            wr(TLR0, 32'hFFFF_FFFF - 50); wr(TCSR0, LOAD); wr(TCSR0, ENT | ENIT); u_e = wcyc;
            wait_clks(j - 6);
            wr(TCSR0, ENT | ENIT | T0INT); u_c = wcyc;
            wait_clks(30); rdv(TCSR0, a);
            n = int'(u_c) - int'(u_e);
            s = {s, $sformatf("D%0d=%s ", n, a[8] ? "set" : "clear")};
            if (j == Er + 7) fall_lag = int'(irq_fall) - int'(u_c);
        end
        rep("race_clear_vs_rollover", {"D = clear W edge minus start W edge: ", s});
        rep("race_clear_irq_fall_lag", $sformatf("clear_W_edge_to_irq_fall=%0d coincident_D=%0d (irq rise D=%0d; assumes the flag reaches the interrupt through the same path rising and falling)", fall_lag, Er - fall_lag, Er));
        // ---- stop, then one-shot hold mode (ARHT = 0)
        do_reset(3);
        wr(TLR0, 32'hFFFF_FFF0); wr(TCSR0, LOAD); wr(TCSR0, ENT); wait_clks(60); rdv(TCSR0, a); rdv(TCR0, b); rdv(TCR0, c);
        rep("hold_mode", $sformatf("after rollover TCSR0=%s TCR0=%s,%s (equal means held)", hexs(a), hexs(b), hexs(c)));
        wr(TLR0, 32'h0000_0100); wr(TCSR0, LOAD); wr(TCSR0, ENT); wait_clks(20); wr(TCSR0, 32'h0); rdv(TCR0, a); wait_clks(40); rdv(TCR0, b);
        rep("disable_halts", $sformatf("TCR0 %s then %s (equal means halted)", hexs(a), hexs(b)));
        // down counter
        do_reset(3);
        wr(TLR0, 32'd100); wr(TCSR0, LOAD | UDT); wr(TCSR0, ENT | UDT); wait_clks(20); rdv(TCR0, a); wait_clks(20); rdv(TCR0, b);
        rep("down_counter", $sformatf("TCR0 %s then %s", hexs(a), hexs(b)));
        // ---- ENALL
        do_reset(3);
        wr(TCSR0, 32'h400); rdv(TCSR0, a); rdv(TCSR1, b);
        rep("enall", $sformatf("wrote_ENALL: TCSR0=%s TCSR1=%s", hexs(a), hexs(b)));
        wr(TCSR0, 32'h0); rdv(TCSR0, a); rdv(TCSR1, b);
        rep("enall_clear", $sformatf("wrote_0: TCSR0=%s TCSR1=%s", hexs(a), hexs(b)));
        // ---- partial writes (WSTRB): TLR0 and TCSR0
        do_reset(3);
        wr(TLR0, 32'hFFFF_FFFF, 4'b0000); rdv(TLR0, a);
        wr(TLR0, 32'h0, 4'hF); wr(TLR0, 32'hFFFF_FFFF, 4'b0100); rdv(TLR0, b);
        rep("wstrb_TLR0", $sformatf("strb0000=%s strb0100=%s", hexs(a), hexs(b)));
        wr(TCSR0, ENT | ENIT, 4'b0000); rdv(TCSR0, a); do_reset(3); wr(TCSR0, ENT | ENIT, 4'b0010); rdv(TCSR0, b);
        rep("wstrb_TCSR0", $sformatf("write_0xC0_strb0000=%s strb0010=%s", hexs(a), hexs(b)));
        // ---- unaligned
        do_reset(3);
        wr(TLR0 + 5'd1, 32'h1234_5678); rdv(TLR0, a); rdv(TLR0 + 5'd3, b);
        rep("unaligned", $sformatf("write_0x05 TLR0=%s read_0x07=%s", hexs(a), hexs(b)));
        // ---- 64-bit cascade: does a read tear? (read TCR0 then TCR1 across a carry, series of consecutive samples)
        n = 0;
        for (j = 0; j < 12; j++) begin
            logic [63:0] prev, cur; int bad; bad = 0; prev = 0;
            do_reset(3);
            wr(TLR1, 32'h0000_0001); wr(TLR0, 32'hFFFF_FF00 + j * 3); wr(TCSR0, CASC | LOAD); wr(TCSR0, CASC | ENT);
            for (i = 0; i < 40; i++) begin
                rdv(TCR0, a); rdv(TCR1, b); cur = {b, a};
                if (i > 0 && cur < prev) bad++;
                prev = cur;
            end
            n += bad;
        end
        rep("cascade_read_tear", $sformatf("12_trials_x_40_pairs_low_then_high non_monotonic_samples=%0d", n));
        n = 0;
        for (j = 0; j < 12; j++) begin
            logic [63:0] prev, cur; int bad; bad = 0; prev = 0;
            do_reset(3);
            wr(TLR1, 32'h0000_0001); wr(TLR0, 32'hFFFF_FF00 + j * 3); wr(TCSR0, CASC | LOAD); wr(TCSR0, CASC | ENT);
            for (i = 0; i < 40; i++) begin
                rdv(TCR1, b); rdv(TCR0, a); cur = {b, a};
                if (i > 0 && cur < prev) bad++;
                prev = cur;
            end
            n += bad;
        end
        rep("cascade_read_tear_hi_first", $sformatf("12_trials_x_40_pairs_high_then_low non_monotonic_samples=%0d", n));
        do_reset(3);
        // ---- latency, outstanding, ordering
        wr(TLR0, 32'h5); a = last_lat; rd(TLR0); b = last_lat;
        rep("latency", $sformatf("write=%0d read=%0d", a, b));
        wr(TLR0, 32'h11, 4'hF, 1); rdv(TLR0, a); wr(TLR0, 32'h22, 4'hF, 2); rdv(TLR0, b);
        rep("aw_w_order", $sformatf("aw_first=%s w_first=%s", hexs(a), hexs(b)));
        outstanding_rd(TLR0, TLR1, 24);
        rep("outstanding_rd", $sformatf("ar_accepted_while_rready_low=%0d r_valid_while_low=%0d first=%s/%s second=%s/%s", ar_held, r_before_release, hexs(raw_r0), rname(raw_rr0), hexs(raw_r1), rname(raw_rr1)));
        outstanding_wr(TLR0, 32'h33, TLR1, 32'h44, 24); rdv(TLR0, a); rdv(TLR1, b);
        rep("outstanding_wr", $sformatf("aw_accepted_while_bready_low=%0d w_accepted_while_bready_low=%0d b_valid_while_low=%0d b_total=%0d TLR0=%s TLR1=%s", aw_held, w_held, b_before_release, b_hs, hexs(a), hexs(b)));
        channel_alone(1'b0, TLR0, 32'h55, 20); rdv(TLR0, a);
        rep("aw_alone", $sformatf("aw_accepted=%0d b_without_w=%0d TLR0_after_completion=%s", alone_acc, alone_resp, hexs(a)));
        channel_alone(1'b1, TLR0, 32'h66, 20); rdv(TLR0, a);
        rep("w_alone", $sformatf("w_accepted=%0d b_without_aw=%0d TLR0_after_completion=%s", alone_acc, alone_resp, hexs(a)));
        // ---- reset coverage
        wr(TLR0, 32'h99); wr(TLR1, 32'h98); wr(TCSR0, ENIT | ARHT); wr(TCSR1, ENIT | ARHT);
        do_reset(3);
        s = ""; for (i = 0; i < 8; i++) begin rdv(4 * i, v); s = {s, $sformatf("o%02x=%s ", 4 * i, hexs(v))}; end
        rep("reset_after_writes", s);
        $display("PROBE|done|ok=1");
        $finish;
    end
    initial begin #40ms; $display("PROBE|timeout|ok=0"); $finish; end
endmodule
