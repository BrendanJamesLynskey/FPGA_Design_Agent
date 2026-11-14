// tb_qspi (brief 69): black-box probes of AMD AXI Quad SPI 3.2, AXI4-Lite register mode, standard SPI, 16-deep FIFOs,
// Vivado 2026.1 xsim. Register level only: no SPI device is attached, no transfer is run.
`timescale 1ns/1ps
module tb_qspi;
`include "probe_common.svh"
    wire irq, io0_o, io0_t, io1_o, io1_t, ss_t, cfgclk, cfgmclk, eos, preq; wire [0:0] ss_o;
    dut_qspi u_dut (
        .ext_spi_clk(aclk), .s_axi_aclk(aclk), .s_axi_aresetn(aresetn),
        .s_axi_awaddr(awaddr[6:0]), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr[6:0]), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .io0_i(1'b0), .io0_o(io0_o), .io0_t(io0_t), .io1_i(1'b0), .io1_o(io1_o), .io1_t(io1_t),
        .ss_i(1'b1), .ss_o(ss_o), .ss_t(ss_t), .cfgclk(cfgclk), .cfgmclk(cfgmclk), .eos(eos), .preq(preq),
        .ip2intc_irpt(irq));
    initial begin
        discover(32, 32'hFFFF_FFFF);
        report_discover("window");
        bus_tail(7'h28, 7'h1C);
        $display("PROBE|done|ok=1");
        $finish;
    end
    initial begin #80ms; $display("PROBE|timeout|ok=0"); $finish; end
endmodule
