## design.xdc: board self-check B2MC (b2_mic_pdm_top) on the Nexys A7-100T.
## Pins and IOSTANDARDs are copied from Digilent's master XDC
## (boards/nexys_a7_100t/Nexys-A7-100T-Master.xdc, MIT); only the pins this design uses are here.

## Clock: 100 MHz oscillator
set_property -dict { PACKAGE_PIN E3    IOSTANDARD LVCMOS33 } [get_ports { CLK100MHZ }];
create_clock -add -name sys_clk_pin -period 10.00 -waveform {0 5} [get_ports { CLK100MHZ }];

## Reset button (active low)
set_property -dict { PACKAGE_PIN C12   IOSTANDARD LVCMOS33 } [get_ports { CPU_RESETN }];

## USB-UART (names from the host's side: the FPGA receives on UART_TXD_IN)
set_property -dict { PACKAGE_PIN C4    IOSTANDARD LVCMOS33 } [get_ports { UART_TXD_IN }];
set_property -dict { PACKAGE_PIN D4    IOSTANDARD LVCMOS33 } [get_ports { UART_RXD_OUT }];

## PDM microphone
set_property -dict { PACKAGE_PIN J5    IOSTANDARD LVCMOS33 } [get_ports { M_CLK }];
set_property -dict { PACKAGE_PIN H5    IOSTANDARD LVCMOS33 } [get_ports { M_DATA }];
set_property -dict { PACKAGE_PIN F5    IOSTANDARD LVCMOS33 } [get_ports { M_LRSEL }];

## Configuration bank voltage (Nexys A7: CFGBVS tied to VCCO = 3.3 V)
set_property CFGBVS VCCO [current_design];
set_property CONFIG_VOLTAGE 3.3 [current_design];
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design];

## Asynchronous inputs: CPU_RESETN goes through reset_sync.sv, UART RX and M_DATA through
## two ASYNC_REG flops; M_DATA is sampled mid-way through each 210 ns M_CLK high half.
set async_in [get_ports {CPU_RESETN UART_TXD_IN M_DATA}]
set_input_delay -clock sys_clk_pin 0.000 $async_in
set_false_path -from $async_in

## Slow outputs: UART TX every 868 clocks; M_CLK toggles every 21 clocks from a register;
## M_LRSEL is constant.
set slow_out [get_ports {UART_RXD_OUT M_CLK M_LRSEL}]
set_output_delay -clock sys_clk_pin 0.000 $slow_out
set_false_path -to $slow_out
