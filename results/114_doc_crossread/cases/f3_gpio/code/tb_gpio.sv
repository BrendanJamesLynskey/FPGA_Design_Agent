// tb_gpio (brief 69): black-box probes of AMD AXI GPIO 2.0 (dual channel 8 + 4 bits, interrupt on), Vivado 2026.1 xsim.
`timescale 1ns/1ps
module tb_gpio;
`include "probe_common.svh"
    logic [7:0] pin1 = 8'h5A;
    logic [3:0] pin2 = 4'h6;
    wire  [7:0] out1, io_t1;
    wire  [3:0] out2, io_t2;
    wire        irq;
    dut_gpio u_dut (
        .s_axi_aclk(aclk), .s_axi_aresetn(aresetn),
        .s_axi_awaddr(awaddr[8:0]), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr[8:0]), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .ip2intc_irpt(irq),
        .gpio_io_i(pin1), .gpio_io_o(out1), .gpio_io_t(io_t1),
        .gpio2_io_i(pin2), .gpio2_io_o(out2), .gpio2_io_t(io_t2));

    localparam [8:0] DATA1 = 9'h000, TRI1 = 9'h004, DATA2 = 9'h008, TRI2 = 9'h00C,
                     GIER = 9'h11C, ISR = 9'h120, IER = 9'h128;
    localparam int NREG = 7;
    logic [8:0] regaddr [NREG] = '{DATA1, TRI1, DATA2, TRI2, GIER, ISR, IER};
    string regname [NREG] = '{"DATA1", "TRI1", "DATA2", "TRI2", "GIER", "ISR", "IER"};
    logic [31:0] v;

    task automatic baseline();   // known non-zero state: all inputs, interrupts enabled, ISR clear
        logic [31:0] x;
        wr(TRI1, 32'hFF); wr(TRI2, 32'hF); wr(GIER, 32'h8000_0000); wr(IER, 32'h3);
        rdv(ISR, x); if (x != 0) wr(ISR, x);
    endtask
    function automatic bit is_real(input logic [8:0] ad);
        for (int k = 0; k < NREG; k++) if (ad == regaddr[k]) return 1'b1;
        return 1'b0;
    endfunction
    int unsigned pc; int rel; int dP, dW; int pin_delay = 0; event go_pin;
    int unsigned irq_rise = 0; logic irq_d = 1'b0;
    always @(posedge aclk) begin irq_d <= irq; if (irq && !irq_d) irq_rise <= cyc; end
    always begin   // pin agent: toggles input 1 `pin_delay` negedges after go_pin
        @(go_pin);
        repeat (pin_delay) @(negedge aclk);
        pc = cyc; pin1 = ~pin1;
    end
    task automatic baseline_zero();   // every writable register 0 (all outputs, interrupts off), ISR clear
        logic [31:0] x;
        wr(TRI1, 32'h0); wr(TRI2, 32'h0); wr(DATA1, 32'h0); wr(DATA2, 32'h0); wr(GIER, 32'h0); wr(IER, 32'h0);
        rdv(ISR, x); if (x != 0) wr(ISR, x);
    endtask

    initial begin
        string s; int i, j, n;
        logic [31:0] a, b, c;
        logic [31:0] snap [NREG];
        logic [31:0] snap2 [NREG];
        do_reset(4);

        // ---- reset values, straight after reset (pins: ch1 0x5A, ch2 0x6)
        s = "";
        for (i = 0; i < NREG; i++) begin rdv(regaddr[i], v); s = {s, $sformatf("%s=%s ", regname[i], hexs(v))}; end
        rep("reset_values", s);

        // ---- reserved bits: write ones to every writable register, read back
        s = "";
        wr(TRI1, 32'hFFFF_FFFF); rdv(TRI1, v); s = {s, $sformatf("TRI1=%s ", hexs(v))};
        wr(TRI2, 32'hFFFF_FFFF); rdv(TRI2, v); s = {s, $sformatf("TRI2=%s ", hexs(v))};
        wr(GIER, 32'hFFFF_FFFF); rdv(GIER, v); s = {s, $sformatf("GIER=%s ", hexs(v))};
        wr(IER, 32'hFFFF_FFFF);  rdv(IER, v);  s = {s, $sformatf("IER=%s ", hexs(v))};
        rdv(ISR, v); s = {s, $sformatf("ISR=%s ", hexs(v))};
        rdv(DATA1, v); s = {s, $sformatf("DATA1=%s ", hexs(v))};
        rdv(DATA2, v); s = {s, $sformatf("DATA2=%s ", hexs(v))};
        rep("reserved_bits", s);
        do_reset(4);

        // ---- data register: input bits read the pin, output bits read ...?  (TRI default 0xF0: bits 7:4 input, 3:0 output)
        wr(DATA1, 32'hFFFF_FFFF); rdv(DATA1, v);
        rep("data_in_out", $sformatf("tri=0xF0 wrote=0xFFFFFFFF pins=0x5A read=%s out_pins=0x%02x", hexs(v), out1));
        wr(DATA1, 32'h0000_0000); rdv(DATA1, v);
        rep("data_in_out_zero", $sformatf("wrote=0x0 read=%s out_pins=0x%02x", hexs(v), out1));
        // TRI then DATA ordering: all outputs
        wr(TRI1, 32'h0); wr(DATA1, 32'h0000_00C3); rdv(DATA1, v);
        rep("data_all_out", $sformatf("tri=0 wrote=0xC3 read=%s out_pins=0x%02x tri_pins=0x%02x", hexs(v), out1, io_t1));
        do_reset(4);

        // ---- hole map: non-zero baseline, then read every word of the 512-byte window
        baseline(); wr(ISR, 32'h3);    // ISR = 3 (set by software) so an alias of ISR shows too
        s = ""; n = 0;
        for (i = 0; i < 128; i++) begin
            rdv({i[6:0], 2'b00}, v);
            if (last_resp != 2'b00 || v != 0 || hung) s = {s, $sformatf("o%03x=%s/%s ", i*4, hexs(v), hung ? "HANG" : rname(last_resp))};
            else n++;
        end
        rep("window_read_scan", {$sformatf("zero_okay_words=%0d ", n), s});
        // known-register values for comparison
        s = "";
        for (i = 0; i < NREG; i++) begin rdv(regaddr[i], v); snap[i] = v; s = {s, $sformatf("%s=%s ", regname[i], hexs(v))}; end
        rep("baseline_values", s);

        // ---- write map: from the all-zero state, write 0xFFFFFFFF to every word of the window and see which real register
        //      changed (a hole that really ignores writes changes nothing)
        s = ""; n = 0;
        baseline_zero();
        for (j = 0; j < NREG; j++) begin rdv(regaddr[j], v); snap[j] = v; end
        for (i = 0; i < 128; i++) begin
            logic [8:0] ad; ad = {i[6:0], 2'b00};
            wr(ad, 32'hFFFF_FFFF);
            if (hung) s = {s, $sformatf("o%03x=HANG ", ad)};
            else if (last_resp != 2'b00) s = {s, $sformatf("o%03x=%s ", ad, rname(last_resp))};
            for (j = 0; j < NREG; j++) begin rdv(regaddr[j], v); snap2[j] = v; end
            for (j = 0; j < NREG; j++) if (snap2[j] != snap[j] && !is_real(ad)) s = {s, $sformatf("o%03x->%s ", ad, regname[j])};
            baseline_zero();
            for (j = 0; j < NREG; j++) begin rdv(regaddr[j], v); snap[j] = v; end
        end
        rep("window_write_scan", {"baseline=all_zero pattern=0xFFFFFFFF changed_real_registers: ", s});

        // ---- partial writes (WSTRB): each case starts from the register cleared with a full strobe
        do_reset(4);
        wr(TRI1, 32'h0, 4'hF); wr(TRI1, 32'h0000_00FF, 4'b0000); rdv(TRI1, a);
        wr(TRI1, 32'h0, 4'hF); wr(TRI1, 32'h0000_00FF, 4'b0010); rdv(TRI1, b);
        wr(TRI1, 32'h0, 4'hF); wr(TRI1, 32'h0000_00FF, 4'b0001); rdv(TRI1, c);
        rep("wstrb_TRI1", $sformatf("write_0xFF_strb0000=%s strb0010=%s strb0001=%s (from 0)", hexs(a), hexs(b), hexs(c)));
        wr(TRI1, 32'h0, 4'hF); wr(TRI1, 32'h0000_00FF, 4'b1110); rdv(TRI1, a);
        wr(TRI1, 32'h00FF_FF00, 4'b0001); rdv(TRI1, b);
        rep("wstrb_TRI1_other", $sformatf("write_0xFF_strb1110=%s write_0x00FFFF00_strb0001=%s", hexs(a), hexs(b)));
        wr(GIER, 32'h0, 4'hF);
        wr(GIER, 32'h8000_0000, 4'b0001); rdv(GIER, a); wr(GIER, 32'h0, 4'hF);
        wr(GIER, 32'h8000_0000, 4'b1000); rdv(GIER, b);
        rep("wstrb_GIER", $sformatf("write_bit31_strb0001=%s strb1000=%s (from 0)", hexs(a), hexs(b)));
        wr(IER, 32'h0, 4'hF); wr(IER, 32'h3, 4'b1110); rdv(IER, a); wr(IER, 32'h0, 4'hF); wr(IER, 32'h3, 4'b0001); rdv(IER, b);
        rep("wstrb_IER", $sformatf("write_3_strb1110=%s strb0001=%s (from 0)", hexs(a), hexs(b)));
        // toggle-on-write ISR with a zero strobe
        baseline(); wr(ISR, 32'h1, 4'b0000); rdv(ISR, a);
        rep("wstrb_ISR", $sformatf("write_1_strb0000 from ISR=0: isr=%s", hexs(a)));
        wr(ISR, 32'h1, 4'hF);

        // ---- unaligned addresses
        do_reset(4);
        wr(TRI1 + 9'd1, 32'h0000_0055); rdv(TRI1, a); rdv(TRI1 + 9'd1, b); rdv(TRI1 + 9'd3, c);
        rep("unaligned", $sformatf("write_to_0x005_data_0x55: TRI1=%s read_0x005=%s read_0x007=%s resp=%s", hexs(a), hexs(b), hexs(c), rname(last_resp)));
        wr(TRI1 + 9'd2, 32'h0000_00AA); rdv(TRI1, a);
        rep("unaligned_write2", $sformatf("write_to_0x006: TRI1=%s", hexs(a)));

        // ---- read side effects: repeated reads of every register change nothing
        baseline(); pin1 = 8'hA5; repeat (4) @(posedge aclk); rdv(ISR, a);
        rdv(ISR, b); rdv(ISR, c); rdv(DATA1, v);
        rep("read_side_effect", $sformatf("isr_read1=%s read2=%s read3=%s data1=%s", hexs(a), hexs(b), hexs(c), hexs(v)));

        // ---- interrupt status: toggle-on-write
        baseline();
        pin1 = 8'h5A; repeat (4) @(posedge aclk);
        rdv(ISR, a); rep("isr_after_pin_change", $sformatf("isr=%s irq=%0d", hexs(a), irq));
        wr(ISR, 32'h1); rdv(ISR, a); rep("isr_write1_to_set_bit", $sformatf("isr=%s irq=%0d", hexs(a), irq));
        wr(ISR, 32'h1); rdv(ISR, a); rep("isr_write1_again", $sformatf("isr=%s irq=%0d", hexs(a), irq));
        wr(ISR, 32'h0); rdv(ISR, a); rep("isr_write0", $sformatf("isr=%s", hexs(a)));
        wr(ISR, 32'h2); wr(ISR, 32'hFFFF_FFFF); rdv(ISR, a); rep("isr_write_ones_after_bit1", $sformatf("isr=%s", hexs(a)));
        baseline();

        // ---- interrupt line: level, gated by GIER and IER, cleared only through ISR
        wr(GIER, 32'h0); pin1 = 8'h5B; repeat (4) @(posedge aclk); a = irq; rdv(ISR, b);
        rep("irq_gier_off", $sformatf("irq=%0d isr=%s", a, hexs(b)));
        wr(GIER, 32'h8000_0000); repeat (2) @(posedge aclk); a = irq;
        rep("irq_gier_on_after", $sformatf("irq=%0d", a));
        repeat (20) @(posedge aclk); a = irq; rdv(ISR, b); c = irq;
        rep("irq_level_hold", $sformatf("after_20_clocks=%0d after_isr_read=%0d", a, c));
        wr(ISR, 32'h1); repeat (2) @(posedge aclk); a = irq; rdv(ISR, b);
        rep("irq_after_clear", $sformatf("irq=%0d isr=%s", a, hexs(b)));
        wr(IER, 32'h0); pin1 = 8'h5A; repeat (4) @(posedge aclk); a = irq; rdv(ISR, b);
        rep("irq_ier_off", $sformatf("irq=%0d isr=%s", a, hexs(b)));
        // one-clock input pulse
        baseline();
        @(negedge aclk); pin1 = 8'h5B; @(negedge aclk); pin1 = 8'h5A; repeat (4) @(posedge aclk); rdv(ISR, a);
        rep("pulse_1clk", $sformatf("isr=%s", hexs(a)));
        wr(ISR, 32'h1);
        baseline();

        // ---- the two delays that place the coincident clock: dP = pin edge to irq rising edge (an event with the register
        //      enables on); dW = write-data handshake edge to irq rising edge (a GIER write that releases a pending ISR bit)
        baseline(); pin1 = 8'h5A; repeat (3) @(posedge aclk);
        irq_rise = 0; pin_delay = 0; @(negedge aclk); -> go_pin; repeat (20) @(posedge aclk);
        dP = int'(irq_rise) - int'(pc);
        wr(GIER, 32'h0); rdv(ISR, a);   // ISR bit 0 still pending from the pin edge, interrupt now masked
        repeat (4) @(posedge aclk);
        irq_rise = 0; wr(GIER, 32'h8000_0000); repeat (10) @(posedge aclk);
        dW = int'(irq_rise) - int'(wcyc);
        rep("irq_delays", $sformatf("pin_edge_to_irq=%0d write_handshake_to_irq=%0d coincident_rel=%0d aw_edge=%0d w_edge=%0d b_edge=%0d irq_edge=%0d", dP, dW, dW - dP, awcyc, wcyc, bcyc, irq_rise));
        // ---- same-clock races. rel = (clock edge on which the IP first samples the new pin value) minus (clock edge of the
        //      write-data handshake): rel 0 is the same edge. Scenario A: ISR bit 0 pending, software writes 1 (clear)
        //      against a new input change. Scenario B: ISR clear, software writes 1 (toggle to set) against an input change.
        for (n = 0; n < 2; n++) begin
            s = "";
            for (j = -6; j <= 8; j++) begin
                baseline();
                if (n == 0) begin
                    pin1 = 8'h5A; @(negedge aclk); pin1 = 8'h5B; repeat (4) @(posedge aclk);   // ISR = 1 pending
                end
                pc = 0;
                @(negedge aclk);
                if (j < 0) begin pin_delay = 0; -> go_pin; repeat (-j) @(negedge aclk); wr(ISR, 32'h1); end
                else begin pin_delay = j; -> go_pin; wr(ISR, 32'h1); end
                repeat (3) @(posedge aclk);
                rel = int'(pc) - int'(wcyc);
                rdv(ISR, a);
                s = {s, $sformatf("rel%0d=%s ", rel, hexs(a))};
            end
            if (n == 0) rep("race_scenarioA_clear_vs_event", s); else rep("race_scenarioB_toggle_vs_event", s);
        end

        // ---- latency
        baseline();
        wr(TRI1, 32'h0F); a = last_lat; rd(TRI1); b = last_lat;
        rep("latency", $sformatf("write=%0d read=%0d", a, b));

        // ---- back to back, orders
        wr(TRI1, 32'h11, 4'hF, 1); rdv(TRI1, a); wr(TRI1, 32'h22, 4'hF, 2); rdv(TRI1, b);
        rep("aw_w_order", $sformatf("aw_first=%s w_first=%s hung=%0d", hexs(a), hexs(b), hung));

        // ---- outstanding
        baseline(); pin1 = 8'h5A;
        outstanding_rd(TRI1, TRI2, 24);
        rep("outstanding_rd", $sformatf("ar_accepted_while_rready_low=%0d r_valid_while_low=%0d first=%s/%s second=%s/%s", ar_held, r_before_release, hexs(raw_r0), rname(raw_rr0), hexs(raw_r1), rname(raw_rr1)));
        outstanding_wr(TRI1, 32'h0000_0033, TRI2, 32'h0000_000C, 24);
        rdv(TRI1, a); rdv(TRI2, b);
        rep("outstanding_wr", $sformatf("aw_accepted_while_bready_low=%0d w_accepted_while_bready_low=%0d b_valid_while_low=%0d b_total=%0d b0=%s b1=%s TRI1=%s TRI2=%s", aw_held, w_held, b_before_release, b_hs, rname(raw_b0), rname(raw_b1), hexs(a), hexs(b)));
        channel_alone(1'b0, TRI1, 32'h0000_0044, 20);
        rdv(TRI1, a);
        rep("aw_alone", $sformatf("aw_accepted=%0d b_without_w=%0d tri1_after_completion=%s", alone_acc, alone_resp, hexs(a)));
        channel_alone(1'b1, TRI1, 32'h0000_0066, 20);
        rdv(TRI1, a);
        rep("w_alone", $sformatf("w_accepted=%0d b_without_aw=%0d tri1_after_completion=%s", alone_acc, alone_resp, hexs(a)));

        // ---- reset coverage: write every register, reset, read
        baseline(); wr(DATA1, 32'h3C); wr(TRI1, 32'h0F);
        do_reset(4);
        s = "";
        for (i = 0; i < NREG; i++) begin rdv(regaddr[i], v); s = {s, $sformatf("%s=%s ", regname[i], hexs(v))}; end
        rep("reset_after_writes", s);
        $display("PROBE|done|ok=1");
        $finish;
    end
    initial begin #20ms; $display("PROBE|timeout|ok=0"); $finish; end
endmodule
