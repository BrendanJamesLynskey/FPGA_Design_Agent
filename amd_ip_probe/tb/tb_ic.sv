// tb_ic (brief 69): black-box probes of an AMD interconnect in AXI4-Lite use, Vivado 2026.1 xsim. One slave interface
// (S00, AXI4-Lite, 32-bit address), two slaves behind it: AXI GPIO at 0x1000 (4 KB) and AXI UART Lite at 0x2000 (4 KB).
// Everything else in the 32-bit address space is outside every slave. The slaves are AMD IP, so the probes see what
// the interconnect does to real slave behaviour (the UART Lite answers SLVERR to a read of an empty receive FIFO).
// The same bench runs against AXI SmartConnect 1.0 and AXI Interconnect 2.1; only the block design differs.
`timescale 1ns/1ps
module tb_ic;
`include "probe_common.svh"
    tri [7:0] gpio_pins;
    wire uart_tx;
    bd_wrapper u_dut (
        .GPIO_0_tri_io(gpio_pins),
        .S00_AXI_araddr(araddr), .S00_AXI_arprot(arprot), .S00_AXI_arready(arready), .S00_AXI_arvalid(arvalid),
        .S00_AXI_awaddr(awaddr), .S00_AXI_awprot(awprot), .S00_AXI_awready(awready), .S00_AXI_awvalid(awvalid),
        .S00_AXI_bready(bready), .S00_AXI_bresp(bresp), .S00_AXI_bvalid(bvalid),
        .S00_AXI_rdata(rdata), .S00_AXI_rready(rready), .S00_AXI_rresp(rresp), .S00_AXI_rvalid(rvalid),
        .S00_AXI_wdata(wdata), .S00_AXI_wready(wready), .S00_AXI_wstrb(wstrb), .S00_AXI_wvalid(wvalid),
        .UART_0_rxd(1'b1), .UART_0_txd(uart_tx), .aclk(aclk), .aresetn(aresetn));
    localparam [31:0] GP = 32'h0000_1000, UA = 32'h0000_2000;
    logic [31:0] a, b, c, v; string s; int i;
    logic [31:0] edges [10] = '{32'h0000_0000, 32'h0000_0FFC, 32'h0000_1000, 32'h0000_1FFC, 32'h0000_2008, 32'h0000_2FFC,
                                32'h0000_3000, 32'h0000_8000, 32'h8000_0000, 32'hFFFF_FFFC};
    initial begin
        do_reset(6);
        wr(GP + 32'h4, 32'h0); wr(GP, 32'hA5); rdv(GP, a);
        rep("sanity_gpio_through_ic", $sformatf("TRI=0 DATA=0xA5 read=%s resp=%s", hexs(a), rname(last_resp)));
        // ---- addresses at and around the two windows: reads
        s = "";
        for (i = 0; i < 10; i++) begin
            rdv(edges[i], v);
            s = {s, $sformatf("%s=%s/%s ", hexs(edges[i]), hung ? "HANG" : hexs(v), hung ? "HANG" : rname(last_resp))};
            if (hung) do_reset(6);
        end
        rep("map_edges_read", s);
        // ---- the same addresses: writes (GPIO DATA reads are checked afterwards for a stray write)
        s = "";
        for (i = 0; i < 10; i++) begin
            if (edges[i] == 32'h0000_1000 || edges[i] == 32'h0000_1FFC || edges[i] == 32'h0000_2008) continue;   // inside a slave: not a hole test
            wr(edges[i], 32'h0000_0077);
            s = {s, $sformatf("%s=%s ", hexs(edges[i]), hung ? "HANG" : rname(last_resp))};
            if (hung) do_reset(6);
        end
        rdv(GP, a); rdv(GP + 32'h4, b);
        rep("map_edges_write", {s, $sformatf("GPIO_DATA_after=%s GPIO_TRI_after=%s", hexs(a), hexs(b))});
        // ---- a slave's own error response passes through? UART Lite RX empty read answers SLVERR; its TX FIFO read answers OKAY
        rd(UA); a = last_resp; v = last_rdata; rd(UA + 32'h4); b = last_resp;
        rep("slave_error_passthrough", $sformatf("uart_rx_empty_read=%s data=%s uart_txf_read=%s", rname(a[1:0]), hexs(v), rname(b[1:0])));
        // ---- the 4 KB window is wider than the slaves' own 512-byte decode: what reaches the slave?
        rdv(GP + 32'h200, a); rdv(GP + 32'h400, b); rdv(GP + 32'h800, c); rdv(GP + 32'hC00, v);
        rep("inside_window_beyond_slave_decode", $sformatf("GPIO(512 B decode) DATA=0xA5: read_+0x200=%s +0x400=%s +0x800=%s +0xC00=%s", hexs(a), hexs(b), hexs(c), hexs(v)));
        rdv(GP + 32'h10, a); c = last_resp; rdv(GP + 32'h100, b); v = last_resp;
        rep("hole_inside_slave_through_ic", $sformatf("read_GPIO+0x10=%s/%s read_GPIO+0x100=%s/%s (standalone: holes read 0/OKAY)", hexs(a), rname(c[1:0]), hexs(b), rname(v[1:0])));
        wr(GP + 32'h11C, 32'h8000_0000); rdv(GP + 32'h11C, a); rdv(GP + 32'h15C, b);
        rep("alias_through_ic", $sformatf("wrote_GIER=0x80000000 at +0x11C: read_+0x11C=%s read_+0x15C=%s (standalone GPIO aliases +0x15C to GIER)", hexs(a), hexs(b)));
        // ---- ordering and outstanding across the two slaves
        outstanding_rd(GP, UA + 32'h8, 24);
        rep("outstanding_rd_two_slaves", $sformatf("ar_accepted_while_rready_low=%0d r_valid_while_low=%0d first=%s/%s second=%s/%s", ar_held, r_before_release, hexs(raw_r0), rname(raw_rr0), hexs(raw_r1), rname(raw_rr1)));
        outstanding_rd(GP, GP + 32'h4, 24);
        rep("outstanding_rd_same_slave", $sformatf("ar_accepted_while_rready_low=%0d r_valid_while_low=%0d first=%s/%s second=%s/%s", ar_held, r_before_release, hexs(raw_r0), rname(raw_rr0), hexs(raw_r1), rname(raw_rr1)));
        outstanding_rd(32'h0000_3000, GP, 24);
        rep("outstanding_rd_unmapped_then_mapped", $sformatf("ar_accepted_while_rready_low=%0d r_valid_while_low=%0d first=%s/%s second=%s/%s", ar_held, r_before_release, hexs(raw_r0), rname(raw_rr0), hexs(raw_r1), rname(raw_rr1)));
        outstanding_wr(32'h0000_3000, 32'h1, GP + 32'h4, 32'h2, 24); rdv(GP + 32'h4, a);
        rep("outstanding_wr_unmapped_then_mapped", $sformatf("aw_accepted_while_bready_low=%0d w_accepted_while_bready_low=%0d b_valid_while_low=%0d b_total=%0d b0=%s b1=%s GPIO_TRI=%s", aw_held, w_held, b_before_release, b_hs, rname(raw_b0), rname(raw_b1), hexs(a)));
        // ---- the same access-level probes as the slaves, through the interconnect, on GPIO TRI (a plain register)
        bus_tail(GP + 32'h4, GP + 32'h8, 1'b0, "not_observable=1 (both slaves ignore WSTRB, so a forwarded strobe cannot be told from a dropped one)");
        // ---- reset: a write accepted, then reset, then the slave's reset value
        wr(GP + 32'h4, 32'h0); do_reset(6); rdv(GP + 32'h4, a);
        rep("reset_through_ic", $sformatf("GPIO_TRI_after_reset=%s", hexs(a)));
        $display("PROBE|done|ok=1");
        $finish;
    end
    initial begin #40ms; $display("PROBE|timeout|ok=0"); $finish; end
endmodule
