## design.xdc: brief 63D network design (b63d_nexys_net_top) on the Nexys A7-100T.
## Pins and IOSTANDARDs are copied from Digilent's master XDC (boards/nexys_a7_100t/Nexys-A7-100T-Master.xdc, MIT).

## Clock: 100 MHz oscillator (the MMCM makes the 50 MHz logic clock and the PHY's reference clock from it)
set_property -dict { PACKAGE_PIN E3    IOSTANDARD LVCMOS33 } [get_ports { CLK100MHZ }];
create_clock -add -name sys_clk_pin -period 10.00 -waveform {0 5} [get_ports { CLK100MHZ }];

## Reset button (active low), USB-UART (the FPGA receives on UART_TXD_IN)
set_property -dict { PACKAGE_PIN C12   IOSTANDARD LVCMOS33 } [get_ports { CPU_RESETN }];
set_property -dict { PACKAGE_PIN C4    IOSTANDARD LVCMOS33 } [get_ports { UART_TXD_IN }];
set_property -dict { PACKAGE_PIN D4    IOSTANDARD LVCMOS33 } [get_ports { UART_RXD_OUT }];

## LEDs 0-3
set_property -dict { PACKAGE_PIN H17   IOSTANDARD LVCMOS33 } [get_ports { LED[0] }];
set_property -dict { PACKAGE_PIN K15   IOSTANDARD LVCMOS33 } [get_ports { LED[1] }];
set_property -dict { PACKAGE_PIN J13   IOSTANDARD LVCMOS33 } [get_ports { LED[2] }];
set_property -dict { PACKAGE_PIN N14   IOSTANDARD LVCMOS33 } [get_ports { LED[3] }];

## Ethernet PHY (LAN8720A, RMII, REF_CLK-in mode: the FPGA drives ETH_REFCLK)
set_property -dict { PACKAGE_PIN C9    IOSTANDARD LVCMOS33 } [get_ports { ETH_MDC }];
set_property -dict { PACKAGE_PIN A9    IOSTANDARD LVCMOS33 } [get_ports { ETH_MDIO }];
set_property -dict { PACKAGE_PIN B3    IOSTANDARD LVCMOS33 } [get_ports { ETH_RSTN }];
set_property -dict { PACKAGE_PIN D9    IOSTANDARD LVCMOS33 } [get_ports { ETH_CRSDV }];
set_property -dict { PACKAGE_PIN C10   IOSTANDARD LVCMOS33 } [get_ports { ETH_RXERR }];
set_property -dict { PACKAGE_PIN C11   IOSTANDARD LVCMOS33 } [get_ports { ETH_RXD[0] }];
set_property -dict { PACKAGE_PIN D10   IOSTANDARD LVCMOS33 } [get_ports { ETH_RXD[1] }];
set_property -dict { PACKAGE_PIN B9    IOSTANDARD LVCMOS33 } [get_ports { ETH_TXEN }];
set_property -dict { PACKAGE_PIN A10   IOSTANDARD LVCMOS33 } [get_ports { ETH_TXD[0] }];
set_property -dict { PACKAGE_PIN A8    IOSTANDARD LVCMOS33 } [get_ports { ETH_TXD[1] }];
set_property -dict { PACKAGE_PIN D5    IOSTANDARD LVCMOS33 } [get_ports { ETH_REFCLK }];

## Configuration bank voltage (Nexys A7: CFGBVS tied to VCCO = 3.3 V)
set_property CFGBVS VCCO [current_design];
set_property CONFIG_VOLTAGE 3.3 [current_design];
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design];

## RMII timing (RMII specification rev 1.2: the PHY's outputs change 2 to 14 ns after REF_CLK rises; its inputs need
## 4 ns setup and 2 ns hold). REF_CLK leaves the FPGA 45 degrees (2.5 ns) after the logic clock, so relative to the
## logic clock the receive data arrive 4.5 to 16.5 ns after its edge, and the PHY samples the transmit data 2.5 ns after
## it. Board traces are short and left out. The receive and transmit registers sit in the IOBs.
set clk50 [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]]
set_input_delay -clock $clk50 -max 16.5 [get_ports {ETH_CRSDV ETH_RXERR ETH_RXD[*]}]
set_input_delay -clock $clk50 -min 4.5  [get_ports {ETH_CRSDV ETH_RXERR ETH_RXD[*]}]
set_output_delay -clock $clk50 -max 1.5  [get_ports {ETH_TXEN ETH_TXD[*]}]
set_output_delay -clock $clk50 -min -4.5 [get_ports {ETH_TXEN ETH_TXD[*]}]
set_property IOB TRUE [get_ports {ETH_CRSDV ETH_RXERR ETH_RXD[*] ETH_TXEN ETH_TXD[*]}]

## Asynchronous or slow: reset button, UART, MDIO (2 MHz, synchronised in the design), PHY reset, LEDs, REF_CLK out
set async_in [get_ports {CPU_RESETN UART_TXD_IN ETH_MDIO}]
set_input_delay -clock sys_clk_pin 0.000 $async_in
set_false_path -from $async_in
set slow_out [get_ports {LED[*] UART_RXD_OUT ETH_MDC ETH_MDIO ETH_RSTN}]
set_output_delay -clock sys_clk_pin 0.000 $slow_out
set_false_path -to $slow_out
