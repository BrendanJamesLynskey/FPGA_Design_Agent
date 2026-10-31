## design.xdc: board self-check B2AC (b2_acl_adxl362_top) on the Nexys A7-100T.
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

## ADXL362 accelerometer, SPI mode 0 (INT1/INT2 not used)
set_property -dict { PACKAGE_PIN E15   IOSTANDARD LVCMOS33 } [get_ports { ACL_MISO }];
set_property -dict { PACKAGE_PIN F14   IOSTANDARD LVCMOS33 } [get_ports { ACL_MOSI }];
set_property -dict { PACKAGE_PIN F15   IOSTANDARD LVCMOS33 } [get_ports { ACL_SCLK }];
set_property -dict { PACKAGE_PIN D15   IOSTANDARD LVCMOS33 } [get_ports { ACL_CSN }];

## Configuration bank voltage (Nexys A7: CFGBVS tied to VCCO = 3.3 V)
set_property CFGBVS VCCO [current_design];
set_property CONFIG_VOLTAGE 3.3 [current_design];
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design];

## Asynchronous inputs: CPU_RESETN goes through reset_sync.sv, UART RX and MISO through
## two ASYNC_REG flops. MISO is sampled at the end of each 500 ns SCLK high half, so its
## timing needs no constraint at 1 MHz. A zero input delay marks them constrained for
## check_timing; the false path removes them from timing analysis.
set async_in [get_ports {CPU_RESETN UART_TXD_IN ACL_MISO}]
set_input_delay -clock sys_clk_pin 0.000 $async_in
set_false_path -from $async_in

## Slow outputs: UART TX changes every 868 clocks, the SPI outputs every 50 clocks
## (1 MHz SCLK), all from registers.
set slow_out [get_ports {UART_RXD_OUT ACL_SCLK ACL_MOSI ACL_CSN}]
set_output_delay -clock sys_clk_pin 0.000 $slow_out
set_false_path -to $slow_out
