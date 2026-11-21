// tb_uartlite (brief 69): black-box probes of AMD AXI UART Lite 2.0 (230400 baud, 8N1, no parity), Vivado 2026.1 xsim.
`timescale 1ns/1ps
module tb_uartlite;
`include "probe_common.svh"
    logic loop = 1'b1, rx_force = 1'b1;
    wire tx, irq, rx_in;
    assign rx_in = loop ? tx : rx_force;
    dut_uart u_dut (
        .s_axi_aclk(aclk), .s_axi_aresetn(aresetn), .interrupt(irq),
        .s_axi_awaddr(awaddr[3:0]), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr[3:0]), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .rx(rx_in), .tx(tx));
    localparam [3:0] RXF = 4'h0, TXF = 4'h4, STAT = 4'h8, CTRL = 4'hC;
    localparam int CHR = 4600;   // clocks for one 8N1 character at 230400 baud and 100 MHz, with margin
    task automatic wait_clks(input int n); repeat (n) @(posedge aclk); endtask
    task automatic send(input logic [7:0] c); wr(TXF, {24'h0, c}); endtask
    logic [31:0] a, b, c, v; string s; int i, n;
    int irq_hi;
    int irq_rises = 0, irq_high = 0; int unsigned irq_t0 = 0, irq_first = 0; logic irq_q = 1'b0;
    always @(posedge aclk) begin
        irq_q <= irq;
        if (irq) irq_high <= irq_high + 1;
        if (irq && !irq_q) begin irq_rises <= irq_rises + 1; if (irq_rises == 0) irq_first <= cyc; end
    end
    task automatic irq_log_reset(); irq_rises = 0; irq_high = 0; irq_t0 = cyc; endtask
    function automatic string irq_log(); return $sformatf("rises=%0d high_clocks=%0d first_rise_after=%0d", irq_rises, irq_high, irq_rises ? int'(irq_first) - int'(irq_t0) : -1); endfunction

    initial begin
        do_reset(4);
        // ---- reset values and the access types of each register
        rdv(STAT, a); rdv(TXF, b); rdv(CTRL, c); n = int'(last_resp);
        rep("reset_values", $sformatf("STAT=%s TXF_read=%s CTRL_read=%s ctrl_resp=%s", hexs(a), hexs(b), hexs(c), rname(last_resp)));
        rd(RXF); rep("rx_empty_read", $sformatf("resp=%s data=%s hung=%0d", rname(last_resp), hexs(last_rdata), hung));
        rd(TXF); rep("txf_read", $sformatf("resp=%s data=%s", rname(last_resp), hexs(last_rdata)));
        wr(STAT, 32'hFFFF_FFFF); rep("write_stat_ro", $sformatf("resp=%s", rname(last_resp)));
        wr(RXF, 32'h55); rdv(STAT, a); rep("write_rxf_ro", $sformatf("resp=%s stat_after=%s", rname(last_resp), hexs(a)));
        // ---- loopback of one character, pop on read
        send(8'h41); wait_clks(CHR); rdv(STAT, a);
        rdv(RXF, b); rdv(STAT, c); rdv(RXF, v);
        rep("rx_pop_on_read", $sformatf("stat_with_char=%s first_read=%s stat_after_read=%s second_read=%s/%s", hexs(a), hexs(b), hexs(c), hexs(v), rname(last_resp)));
        // two characters, FIFO order, and a read of the data register twice
        send(8'h42); send(8'h43); wait_clks(2 * CHR); rdv(STAT, a); rdv(RXF, b); rdv(RXF, c); rdv(STAT, v);
        rep("rx_fifo_order", $sformatf("stat=%s reads=%s,%s stat_after=%s", hexs(a), hexs(b), hexs(c), hexs(v)));
        // ---- TX FIFO full: write 24 characters back to back
        s = ""; n = 0; v = 0;
        for (i = 0; i < 24; i++) begin
            send(8'h30 + i[7:0]);
            if (last_resp != 2'b00) begin if (n == 0) v = i; n++; end
        end
        rdv(STAT, a);
        rep("tx_full", $sformatf("writes=24 first_non_okay_write_index=%0d non_okay_writes=%0d stat_after=%s", n ? v : 32'hFFFF, n, hexs(a)));
        wait_clks(25 * CHR);
        // ---- RX overrun: the RX FIFO is 16 deep; 16 chars have arrived (some lost); read STAT twice
        rdv(STAT, a); rdv(STAT, b);
        rep("rx_full_no_overrun_yet", $sformatf("16 chars received, none read: stat=%s stat_again=%s", hexs(a), hexs(b)));
        for (i = 0; i < 3; i++) send(8'h90 + i[7:0]);
        wait_clks(4 * CHR); rdv(STAT, a); rdv(STAT, b);
        rep("rx_overrun", $sformatf("3 more chars into a full RX FIFO: stat=%s stat_again=%s", hexs(a), hexs(b)));
        s = ""; n = 0;
        repeat (20) begin rdv(RXF, v); if (last_resp == 2'b00) n++; end
        rdv(STAT, a);
        rep("rx_drain", $sformatf("okay_reads=%0d stat_after=%s", n, hexs(a)));
        // ---- control register: reset RX FIFO, reset TX FIFO
        send(8'h61); wait_clks(CHR); rdv(STAT, a); wr(CTRL, 32'h2); rdv(STAT, b);
        rep("ctrl_reset_rx", $sformatf("stat_before=%s stat_after_rst_rx=%s", hexs(a), hexs(b)));
        for (i = 0; i < 6; i++) send(8'h70 + i[7:0]);
        rdv(STAT, a); wr(CTRL, 32'h1); rdv(STAT, b);
        rep("ctrl_reset_tx", $sformatf("stat_before=%s stat_after_rst_tx=%s", hexs(a), hexs(b)));
        wait_clks(7 * CHR); wr(CTRL, 32'h2);
        // ---- reserved bits of CTRL, and strobes
        wr(CTRL, 32'hFFFF_FFFF); rdv(STAT, a); wr(CTRL, 32'h0); rdv(STAT, b);
        rep("ctrl_ones_then_zero", $sformatf("stat_after_ones=%s stat_after_zero=%s", hexs(a), hexs(b)));
        wr(CTRL, 32'h2); wait_clks(10);
        wr(TXF, 32'h0000_0055, 4'b0000); wait_clks(CHR); rdv(STAT, a);
        rep("wstrb_zero_tx", $sformatf("wrote_0x55_strb0000: stat=%s", hexs(a)));
        rdv(RXF, b); rep("wstrb_zero_tx_data", $sformatf("rx=%s resp=%s", hexs(b), rname(last_resp)));
        wr(TXF, 32'h0000_0066, 4'b0010); wait_clks(CHR); rdv(RXF, b);
        rep("wstrb_byte1_tx", $sformatf("wrote_0x66_strb0010 rx=%s resp=%s", hexs(b), rname(last_resp)));
        wr(TXF, 32'hAB00_0077, 4'b0001); wait_clks(CHR); rdv(RXF, b);
        rep("wide_wdata_tx", $sformatf("wrote_0xAB000077 rx=%s", hexs(b)));
        // ---- unaligned addresses
        send(8'h5A); wait_clks(CHR); rdv(STAT, a); rdv(4'h1, b); rdv(STAT, c);
        rep("unaligned_rx_read", $sformatf("stat=%s read_0x1=%s stat_after=%s", hexs(a), hexs(b), hexs(c)));
        wr(4'h5, 32'h0000_0044); wait_clks(CHR); rdv(RXF, b);
        rep("unaligned_tx_write", $sformatf("write_0x5 then rx=%s", hexs(b)));
        wr(4'hA, 32'hFFFF_FFFF); rdv(STAT, a);
        rep("unaligned_stat_write", $sformatf("write_0xA stat=%s", hexs(a)));
        // ---- frame error: hold RX low for 12 bit times with the loopback open
        wr(CTRL, 32'h3); wait_clks(5);
        loop = 1'b0; rx_force = 1'b1; wait_clks(100); rx_force = 1'b0; wait_clks(434 * 12); rx_force = 1'b1; wait_clks(200);
        rdv(STAT, a); rdv(STAT, b); rdv(RXF, c);
        rep("frame_error", $sformatf("stat=%s stat_again=%s rxf_read=%s/%s", hexs(a), hexs(b), hexs(c), rname(last_resp)));
        loop = 1'b1; wait_clks(100);
        // ---- interrupt: pulses or level? enabled with an empty TX FIFO, after RX data, after a read
        wr(CTRL, 32'h3); wait_clks(5); rdv(STAT, a);
        rep("irq_idle", $sformatf("irq_before_enable=%0d", irq));
        irq_log_reset(); wr(CTRL, 32'h10); wait_clks(40); rdv(STAT, a);
        rep("irq_enabled_tx_empty", $sformatf("%s irq_now=%0d stat=%s", irq_log(), irq, hexs(a)));
        irq_log_reset(); send(8'h31); wait_clks(CHR); rdv(STAT, a);
        rep("irq_after_char", $sformatf("%s irq_now=%0d stat=%s (char sent and received by loopback)", irq_log(), irq, hexs(a)));
        irq_log_reset(); wait_clks(200); rep("irq_with_rx_data_waiting", $sformatf("%s irq_now=%0d stat=%s", irq_log(), irq, hexs(a)));
        irq_log_reset(); rdv(RXF, b); wait_clks(20); rep("irq_after_pop", $sformatf("%s", irq_log()));
        irq_log_reset(); wr(CTRL, 32'h00); wait_clks(20); rdv(STAT, a); rep("irq_disable_write0", $sformatf("%s stat=%s", irq_log(), hexs(a)));
        wr(CTRL, 32'h10); irq_log_reset(); wr(CTRL, 32'h2); wait_clks(20);
        rdv(STAT, a); rep("irq_enable_bit_after_rx_reset_write", $sformatf("stat=%s", hexs(a)));
        wr(CTRL, 32'h00);
        // ---- latency, back to back, order
        wr(CTRL, 32'h3); wait_clks(50);
        rd(STAT); a = last_lat; wr(CTRL, 32'h0); b = last_lat;
        rep("latency", $sformatf("read=%0d write=%0d", a, b));
        wr(TXF, 32'h21, 4'hF, 1); wr(TXF, 32'h22, 4'hF, 2); wait_clks(2 * CHR); rdv(RXF, a); rdv(RXF, b);
        rep("aw_w_order", $sformatf("aw_first_then_w_first rx=%s,%s", hexs(a), hexs(b)));
        // ---- outstanding
        wr(CTRL, 32'h3);
        outstanding_rd(STAT, STAT, 24);
        rep("outstanding_rd", $sformatf("ar_accepted_while_rready_low=%0d r_valid_while_low=%0d first=%s/%s second=%s/%s", ar_held, r_before_release, hexs(raw_r0), rname(raw_rr0), hexs(raw_r1), rname(raw_rr1)));
        outstanding_wr(CTRL, 32'h2, CTRL, 32'h1, 24);
        rep("outstanding_wr", $sformatf("aw_accepted_while_bready_low=%0d w_accepted_while_bready_low=%0d b_valid_while_low=%0d b_total=%0d", aw_held, w_held, b_before_release, b_hs));
        channel_alone(1'b0, CTRL, 32'h2, 20);
        rep("aw_alone", $sformatf("aw_accepted=%0d b_without_w=%0d", alone_acc, alone_resp));
        channel_alone(1'b1, CTRL, 32'h2, 20);
        rep("w_alone", $sformatf("w_accepted=%0d b_without_aw=%0d", alone_acc, alone_resp));
        // ---- reset with characters in both FIFOs and the interrupt enabled
        wr(CTRL, 32'h10); send(8'h11); send(8'h12); wait_clks(2 * CHR); send(8'h13);
        do_reset(4); wait_clks(2); rdv(STAT, a);
        rep("reset_after_activity", $sformatf("stat=%s irq=%0d", hexs(a), irq));
        $display("PROBE|done|ok=1");
        $finish;
    end
    initial begin #60ms; $display("PROBE|timeout|ok=0"); $finish; end
endmodule
