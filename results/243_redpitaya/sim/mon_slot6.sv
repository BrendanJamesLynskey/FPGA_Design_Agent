module mon2;
  always @(posedge tb_bus243.adc_clk) if (tb_bus243.sys[6].ren || tb_bus243.sys[6].ack || tb_bus243.ps_sys.ack || tb_bus243.sys[6].rdata != 0)
    $display("%0t slot6(adc clk) ren=%b ack=%b rdata=%h | PS side ack=%b rdata=%h", $time, tb_bus243.sys[6].ren, tb_bus243.sys[6].ack, tb_bus243.sys[6].rdata, tb_bus243.ps_sys.ack, tb_bus243.ps_sys.rdata);
endmodule
