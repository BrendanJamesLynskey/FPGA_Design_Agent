// tb_iic (brief 69): black-box probes of AMD AXI IIC 2.1, Vivado 2026.1 xsim. Register level only: no I2C device is
// attached (SDA and SCL are held high), so no transfer is run.
`timescale 1ns/1ps
module tb_iic;
`include "probe_common.svh"
    wire irq, sda_o, sda_t, scl_o, scl_t; wire [0:0] gpo;
    dut_iic u_dut (
        .s_axi_aclk(aclk), .s_axi_aresetn(aresetn), .iic2intc_irpt(irq),
        .s_axi_awaddr(awaddr[8:0]), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr[8:0]), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .sda_i(1'b1), .sda_o(sda_o), .sda_t(sda_t), .scl_i(1'b1), .scl_o(scl_o), .scl_t(scl_t), .gpo(gpo));
    initial begin
        discover(128, 32'hFFFF_FFFF);
        report_discover("window");
        bus_tail(9'h028, 9'h01C);
        $display("PROBE|done|ok=1");
        $finish;
    end
    initial begin #80ms; $display("PROBE|timeout|ok=0"); $finish; end
endmodule
