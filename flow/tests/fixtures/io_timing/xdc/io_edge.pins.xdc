# io_edge pins (bank 15: rx_clk on JB[10], the P side of an MRCC pair (a BUFIO needs the P side); rx_d on JB[1], JB[4])
set_property -dict { PACKAGE_PIN H16 IOSTANDARD LVCMOS33 } [get_ports { rx_clk }]
set_property -dict { PACKAGE_PIN D14 IOSTANDARD LVCMOS33 } [get_ports { rx_d[0] }]
set_property -dict { PACKAGE_PIN H14 IOSTANDARD LVCMOS33 } [get_ports { rx_d[1] }]
set_property -dict { PACKAGE_PIN H17 IOSTANDARD LVCMOS33 } [get_ports { LED[0] }]
set_property -dict { PACKAGE_PIN E3 IOSTANDARD LVCMOS33 } [get_ports { CLK100MHZ }]
