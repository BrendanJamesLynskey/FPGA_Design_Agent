// tb_intc (brief 69): black-box probes of AMD AXI Interrupt Controller 4.1 (4 inputs: 0 and 1 rising-edge, 2 and 3
// high-level; basic mode), Vivado 2026.1 xsim.
`timescale 1ns/1ps
module tb_intc;
`include "probe_common.svh"
    logic [3:0] intr = 4'b0000;
    wire irq;
    dut_intc u_dut (
        .s_axi_aclk(aclk), .s_axi_aresetn(aresetn),
        .s_axi_awaddr(awaddr[8:0]), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr[8:0]), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .intr(intr), .irq(irq));
    localparam [8:0] ISR = 9'h00, IPR = 9'h04, IER = 9'h08, IAR = 9'h0C, SIE = 9'h10, CIE = 9'h14, IVR = 9'h18, MER = 9'h1C,
                     IMR = 9'h20, ILR = 9'h24, IVAR0 = 9'h100;
    localparam int NREG = 8;
    logic [8:0] regaddr [NREG] = '{ISR, IPR, IER, IVR, MER, IMR, ILR, IVAR0};
    string regname [NREG] = '{"ISR", "IPR", "IER", "IVR", "MER", "IMR", "ILR", "IVAR0"};
    task automatic wait_clks(input int n); repeat (n) @(posedge aclk); endtask
    logic [31:0] a, b, c, v; string s; int i, j, n;
    logic [31:0] snap [NREG], snap2 [NREG];
    int unsigned irq_rise = 0, irq_fall = 0; logic irq_q = 1'b0;
    always @(posedge aclk) begin irq_q <= irq; if (irq && !irq_q) irq_rise <= cyc; if (!irq && irq_q) irq_fall <= cyc; end
    int unsigned pc; int pin_delay = 0; event go_pin; int rel, dP, dC;
    always begin @(go_pin); repeat (pin_delay) @(negedge aclk); pc = cyc; intr[0] = ~intr[0]; end
    function automatic bit is_real(input logic [8:0] ad);
        if (ad <= 9'h24) return 1'b1;
        return 1'b0;
    endfunction
    task automatic snapshot(output logic [31:0] sn [NREG]);
        logic [31:0] x; for (int k = 0; k < NREG; k++) begin rdv(regaddr[k], x); sn[k] = x; end
    endtask

    initial begin
        do_reset(4);
        // ---- reset values and the full 9-bit window
        s = "";
        for (i = 0; i < NREG; i++) begin rdv(regaddr[i], v); s = {s, $sformatf("%s=%s/%s ", regname[i], hexs(v), rname(last_resp))}; end
        rdv(SIE, a); rdv(CIE, b); rdv(IAR, c);
        rep("reset_values", {s, $sformatf("SIE_read=%s CIE_read=%s IAR_read=%s", hexs(a), hexs(b), hexs(c))});
        for (i = 0; i < 128; i++) scan_skip[i] = 0;
        scan_rd(0, 128);
        rep("window_read_scan_reset", {$sformatf("zero_okay_words=%0d ", scan_zero), scan_str});
        // ---- non-zero state, then scan reads again (ISR from software, IER, MER)
        wr(IER, 32'hF); wr(ISR, 32'h3); wr(IVAR0, 32'h1234_5678); wr(MER, 32'h1);
        scan_rd(0, 128);
        rep("window_read_scan_nonzero", {$sformatf("zero_okay_words=%0d ", scan_zero), scan_str});
        // ---- write scan over the holes only
        do_reset(4); snapshot(snap);
        s = "";
        for (i = 0; i < 128; i++) begin
            logic [8:0] ad; ad = {i[6:0], 2'b00};
            if (is_real(ad) || (ad >= 9'h100 && ad < 9'h104)) continue;
            wr(ad, 32'hFFFF_FFFF);
            if (hung) begin s = {s, $sformatf("o%03x=HANG ", ad)}; do_reset(4); end
            else if (last_resp != 2'b00) s = {s, $sformatf("o%03x=%s ", ad, rname(last_resp))};
            snapshot(snap2);
            for (j = 0; j < NREG; j++) if (snap2[j] != snap[j]) s = {s, $sformatf("o%03x->%s ", ad, regname[j])};
            do_reset(4); snapshot(snap);
        end
        rep("window_write_scan", {"from_reset pattern=0xFFFFFFFF holes_only changed_or_non_okay: ", s});
        // ---- reserved bits
        do_reset(4);
        wr(IER, 32'hFFFF_FFFF); rdv(IER, a); wr(MER, 32'hFFFF_FFFF); rdv(MER, b); wr(IMR, 32'hFFFF_FFFF); rdv(IMR, c); wr(ILR, 32'hFFFF_FFFF); rdv(ILR, v);
        rep("reserved_bits", $sformatf("IER=%s MER=%s IMR=%s ILR=%s", hexs(a), hexs(b), hexs(c), hexs(v)));
        do_reset(4);
        // ---- SIE / CIE / IAR access types
        wr(SIE, 32'h5); rdv(IER, a); wr(SIE, 32'h2); rdv(IER, b); wr(CIE, 32'h1); rdv(IER, c); wr(CIE, 32'h0); rdv(IER, v);
        rep("sie_cie", $sformatf("SIE_5=%s SIE_2_adds=%s CIE_1_clears=%s CIE_0_nochange=%s", hexs(a), hexs(b), hexs(c), hexs(v)));
        wr(IER, 32'h0); wr(IER, 32'hF); wr(SIE, 32'h0); rdv(IER, a);
        rep("sie_zero_no_change", $sformatf("IER=%s", hexs(a)));
        // ---- software interrupt through ISR before and after HIE
        do_reset(4);
        wr(ISR, 32'h3); rdv(ISR, a); rdv(IPR, b);
        rep("isr_write_before_hie", $sformatf("ISR=%s IPR=%s", hexs(a), hexs(b)));
        wr(IAR, 32'h1); rdv(ISR, a); wr(IAR, 32'h0); rdv(ISR, b); wr(IAR, 32'h2); rdv(ISR, c);
        rep("iar_clears", $sformatf("after_IAR_1=%s IAR_0_nochange=%s after_IAR_2=%s", hexs(a), hexs(b), hexs(c)));
        wr(MER, 32'h2); rdv(MER, a); wr(ISR, 32'h3); rdv(ISR, b);
        rep("isr_write_after_hie", $sformatf("MER=%s ISR_after_write_3=%s", hexs(a), hexs(b)));
        // ---- hardware inputs: edge and level
        do_reset(4); wr(MER, 32'h3); wr(IER, 32'hF); intr = 4'b0000; wait_clks(4);
        @(negedge aclk); intr[0] = 1'b1; @(negedge aclk); intr[0] = 1'b0; wait_clks(8); rdv(ISR, a);
        rep("edge_input_1clk_pulse", $sformatf("ISR=%s irq=%0d", hexs(a), irq));
        wr(IAR, 32'h1); wait_clks(4); rdv(ISR, a); rep("edge_ack", $sformatf("ISR=%s irq=%0d", hexs(a), irq));
        @(negedge aclk); intr[2] = 1'b1; wait_clks(8); rdv(ISR, a); wr(IAR, 32'h4); wait_clks(4); rdv(ISR, b);
        rep("level_input_high_ack", $sformatf("ISR=%s ack_while_high=%s irq=%0d", hexs(a), hexs(b), irq));
        @(negedge aclk); intr[2] = 1'b0; wait_clks(8); rdv(ISR, a); rdv(IPR, b);
        rep("level_input_released", $sformatf("ISR=%s IPR=%s (input low, no IAR write since)", hexs(a), hexs(b)));
        wr(IAR, 32'hF); wait_clks(4); rdv(ISR, c);
        rep("level_input_released_then_ack", $sformatf("ISR=%s", hexs(c)));
        // IVR: highest priority (lowest number) pending
        @(negedge aclk); intr[3] = 1'b1; intr[1] = 1'b0; wait_clks(8); rdv(IVR, a); wr(ISR, 32'h0); 
        @(negedge aclk); intr[0] = 1'b1; wait_clks(8); rdv(IVR, b); rdv(IVR, c); wr(IAR, 32'h1); wait_clks(4); rdv(IVR, v);
        rep("ivr", $sformatf("only_input3=%s inputs_0_and_3=%s again=%s after_ack_0=%s", hexs(a), hexs(b), hexs(c), hexs(v)));
        @(negedge aclk); intr = 4'b0; wait_clks(4); wr(IAR, 32'hF); wait_clks(4); rdv(IVR, a);
        rep("ivr_none_pending", $sformatf("IVR=%s", hexs(a)));
        // ---- irq output: needs ME, IER and a pending bit; level
        do_reset(4); intr = 4'b0; wr(IER, 32'h1); wr(MER, 32'h0);
        @(negedge aclk); intr[0] = 1'b1; @(negedge aclk); intr[0] = 1'b0; wait_clks(8); a = irq; rdv(ISR, b);
        rep("irq_mer_off", $sformatf("irq=%0d ISR=%s", a, hexs(b)));
        wr(MER, 32'h3); wait_clks(4); a = irq; rdv(ISR, b); c = irq; wait_clks(20); v = irq;
        rep("irq_mer_on", $sformatf("irq=%0d after_read=%0d 20_later=%0d", a, c, v));
        wr(IAR, 32'h1); wait_clks(4); rep("irq_after_ack", $sformatf("irq=%0d", irq));
        // ---- the two lags that place the coincident clock, then the race: ISR bit 0 pending, IAR write 1 against a new edge
        // dP: input edge to irq rise;  dC: IAR write handshake edge to irq fall
        intr[0] = 1'b0; wait_clks(4); wr(IAR, 32'h1);
        pin_delay = 0; @(negedge aclk); -> go_pin; wait_clks(30); dP = int'(irq_rise) - int'(pc);   // rising input
        wr(IAR, 32'h1); wait_clks(10); dC = int'(irq_fall) - int'(wcyc);
        rep("irq_lags", $sformatf("input_edge_to_irq_rise=%0d IAR_write_edge_to_irq_fall=%0d coincident_rel=%0d (assumes the same path to irq both ways)", dP, dC, dC - dP));
        s = "";
        for (j = -8; j <= 8; j++) begin
            intr[0] = 1'b0; wr(IAR, 32'h1); wait_clks(6);
            @(negedge aclk); intr[0] = 1'b1; wait_clks(20);    // ISR bit 0 pending
            pc = 0;
            @(negedge aclk);
            // second edge: drop the input first, then create a new rising edge j clocks around the write
            intr[0] = 1'b0; wait_clks(3);
            @(negedge aclk);
            if (j < 0) begin pin_delay = 0; -> go_pin; repeat (-j) @(negedge aclk); wr(IAR, 32'h1); end
            else begin pin_delay = j; -> go_pin; wr(IAR, 32'h1); end
            wait_clks(30); rdv(ISR, a);
            rel = int'(pc) - int'(wcyc);
            s = {s, $sformatf("rel%0d=%s ", rel, a[0] ? "kept" : "lost")};
        end
        rep("race_iar_clear_vs_edge", {"new rising edge on input 0 against an IAR clear; rel = edge sampled minus IAR W edge: ", s});
        // ---- latency, outstanding, order
        do_reset(4); intr = 4'b0;
        wr(IER, 32'h5); a = last_lat; rd(IER); b = last_lat; rep("latency", $sformatf("write=%0d read=%0d", a, b));
        wr(IER, 32'h1, 4'hF, 1); rdv(IER, a); wr(IER, 32'h2, 4'hF, 2); rdv(IER, b); rep("aw_w_order", $sformatf("aw_first=%s w_first=%s", hexs(a), hexs(b)));
        wr(IER, 32'hF, 4'b0000); rdv(IER, a); wr(IER, 32'h0); wr(IER, 32'hF, 4'b0001); rdv(IER, b);
        rep("wstrb_IER", $sformatf("write_0xF_strb0000=%s then_strb0001_from_0=%s", hexs(a), hexs(b)));
        wr(IER + 9'd1, 32'h0000_0003); rdv(IER, a); rdv(IER + 9'd3, b); rep("unaligned", $sformatf("write_0x09 IER=%s read_0x0B=%s", hexs(a), hexs(b)));
        wr(IER, 32'h0);
        outstanding_rd(IER, MER, 24);
        rep("outstanding_rd", $sformatf("ar_accepted_while_rready_low=%0d r_valid_while_low=%0d first=%s/%s second=%s/%s", ar_held, r_before_release, hexs(raw_r0), rname(raw_rr0), hexs(raw_r1), rname(raw_rr1)));
        outstanding_wr(IER, 32'h5, IER, 32'h6, 24); rdv(IER, a);
        rep("outstanding_wr", $sformatf("aw_accepted_while_bready_low=%0d w_accepted_while_bready_low=%0d b_valid_while_low=%0d b_total=%0d IER=%s", aw_held, w_held, b_before_release, b_hs, hexs(a)));
        channel_alone(1'b0, IER, 32'h9, 20); rdv(IER, a); rep("aw_alone", $sformatf("aw_accepted=%0d b_without_w=%0d IER_after=%s", alone_acc, alone_resp, hexs(a)));
        channel_alone(1'b1, IER, 32'hA, 20); rdv(IER, a); rep("w_alone", $sformatf("w_accepted=%0d b_without_aw=%0d IER_after=%s", alone_acc, alone_resp, hexs(a)));
        // ---- reset coverage
        wr(IER, 32'hF); wr(MER, 32'h3); wr(IVAR0, 32'h1234_5678); wr(ISR, 32'h0);
        do_reset(4);
        s = ""; for (i = 0; i < NREG; i++) begin rdv(regaddr[i], v); s = {s, $sformatf("%s=%s ", regname[i], hexs(v))}; end
        rep("reset_after_writes", s);
        $display("PROBE|done|ok=1");
        $finish;
    end
    initial begin #40ms; $display("PROBE|timeout|ok=0"); $finish; end
endmodule
