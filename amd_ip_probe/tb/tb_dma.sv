// tb_dma (brief 69): black-box probes of the register port of AMD AXI DMA 7.1 (simple mode, scatter-gather off, MM2S and
// S2MM), Vivado 2026.1 xsim. The lite port has no WSTRB input. The memory-mapped and stream sides are tied off, so no
// transfer is run.
`timescale 1ns/1ps
module tb_dma;
`include "probe_common.svh"
    wire mm2s_irq, s2mm_irq;
    dut_dma u_dut (
        .s_axi_lite_aclk(aclk), .m_axi_mm2s_aclk(aclk), .m_axi_s2mm_aclk(aclk), .axi_resetn(aresetn),
        .s_axi_lite_awvalid(awvalid), .s_axi_lite_awready(awready), .s_axi_lite_awaddr(awaddr[9:0]),
        .s_axi_lite_wvalid(wvalid), .s_axi_lite_wready(wready), .s_axi_lite_wdata(wdata),
        .s_axi_lite_bresp(bresp), .s_axi_lite_bvalid(bvalid), .s_axi_lite_bready(bready),
        .s_axi_lite_arvalid(arvalid), .s_axi_lite_arready(arready), .s_axi_lite_araddr(araddr[9:0]),
        .s_axi_lite_rvalid(rvalid), .s_axi_lite_rready(rready), .s_axi_lite_rdata(rdata), .s_axi_lite_rresp(rresp),
        .m_axi_mm2s_araddr(), .m_axi_mm2s_arlen(), .m_axi_mm2s_arsize(), .m_axi_mm2s_arburst(), .m_axi_mm2s_arprot(),
        .m_axi_mm2s_arcache(), .m_axi_mm2s_arvalid(), .m_axi_mm2s_arready(1'b0), .m_axi_mm2s_rdata(32'h0),
        .m_axi_mm2s_rresp(2'b00), .m_axi_mm2s_rlast(1'b0), .m_axi_mm2s_rvalid(1'b0), .m_axi_mm2s_rready(),
        .mm2s_prmry_reset_out_n(), .m_axis_mm2s_tdata(), .m_axis_mm2s_tkeep(), .m_axis_mm2s_tvalid(),
        .m_axis_mm2s_tready(1'b0), .m_axis_mm2s_tlast(),
        .m_axi_s2mm_awaddr(), .m_axi_s2mm_awlen(), .m_axi_s2mm_awsize(), .m_axi_s2mm_awburst(), .m_axi_s2mm_awprot(),
        .m_axi_s2mm_awcache(), .m_axi_s2mm_awvalid(), .m_axi_s2mm_awready(1'b0), .m_axi_s2mm_wdata(), .m_axi_s2mm_wstrb(),
        .m_axi_s2mm_wlast(), .m_axi_s2mm_wvalid(), .m_axi_s2mm_wready(1'b0), .m_axi_s2mm_bresp(2'b00),
        .m_axi_s2mm_bvalid(1'b0), .m_axi_s2mm_bready(), .s2mm_prmry_reset_out_n(),
        .s_axis_s2mm_tdata(32'h0), .s_axis_s2mm_tkeep(4'h0), .s_axis_s2mm_tvalid(1'b0), .s_axis_s2mm_tready(),
        .s_axis_s2mm_tlast(1'b0), .mm2s_introut(mm2s_irq), .s2mm_introut(s2mm_irq), .axi_dma_tstvec());
    logic [31:0] a, b, c; int i;
    initial begin
        discover(256, 32'hFFFF_FFFF);
        report_discover("window");
        // soft reset bit of MM2S_DMACR (bit 2): self-clearing?
        do_reset(4);
        rdv(10'h04, a); wr(10'h00, 32'h4); rdv(10'h00, b);
        for (i = 0; i < 400; i++) begin rdv(10'h00, c); if (!c[2]) break; end
        rep("mm2s_soft_reset", $sformatf("DMASR_at_reset=%s DMACR_just_after_write=%s reads_until_reset_bit_clear=%0d DMACR_then=%s", hexs(a), hexs(b), i, hexs(c)));
        wr(10'h00, 32'h1); rdv(10'h04, a); rdv(10'h00, b);
        rep("mm2s_run_stop", $sformatf("DMACR_RS=1: DMASR=%s DMACR=%s", hexs(a), hexs(b)));
        wr(10'h28, 32'h0); rdv(10'h04, a);
        rep("mm2s_length_zero", $sformatf("length_0_with_RS: DMASR=%s irq=%0d", hexs(a), mm2s_irq));
        bus_tail(10'h18, 10'h48, 1'b0, "no_wstrb_port=1 (the lite port has no WSTRB input)");
        // two writes back to back with BREADY held low until both have been accepted: one B each?
        do_reset(4);
        outstanding_wr(10'h18, 32'h1, 10'h1C, 32'h2, 24);
        rep("outstanding_wr_pair_MM2S_SA_LENGTH_hi", $sformatf("MM2S_SA then MM2S_SA+4: aw_accepted_while_bready_low=%0d w_accepted_while_bready_low=%0d b_total=%0d", aw_held, w_held, b_hs));
        do_reset(4);
        outstanding_wr(10'h48, 32'h1, 10'h4C, 32'h2, 24);
        rep("outstanding_wr_pair_S2MM_DA", $sformatf("S2MM_DA then S2MM_DA+4: aw_accepted_while_bready_low=%0d w_accepted_while_bready_low=%0d b_total=%0d", aw_held, w_held, b_hs));
        do_reset(4);
        outstanding_wr(10'h18, 32'h1, 10'h18, 32'h2, 24); rdv(10'h18, a);
        rep("outstanding_wr_pair_same_register", $sformatf("MM2S_SA twice: aw_accepted_while_bready_low=%0d w_accepted_while_bready_low=%0d b_total=%0d final=%s", aw_held, w_held, b_hs, hexs(a)));
        // does the port recover after a write whose B did not come? an ordinary write and read afterwards
        wr(10'h18, 32'h5); b = last_resp; c = hung; rdv(10'h18, a);
        rep("after_missing_b", $sformatf("ordinary_write: resp=%s hung=%0d then_read=%s read_hung=%0d", rname(b[1:0]), c[0], hexs(a), hung));
        $display("PROBE|done|ok=1");
        $finish;
    end
    initial begin #200ms; $display("PROBE|timeout|ok=0"); $finish; end
endmodule
