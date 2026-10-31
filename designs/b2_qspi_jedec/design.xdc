## design.xdc: board self-check B2QF (b2_qspi_jedec_top) on the Nexys A7-100T.
## Pins and IOSTANDARDs are copied from Digilent's master XDC
## (boards/nexys_a7_100t/Nexys-A7-100T-Master.xdc, MIT); only the pins this design uses are here.
## The master XDC's bus QSPI_DQ[0..3] is split into QSPI_DQ0..QSPI_DQ3 (one direction each).
## SCK is the dedicated CCLK pin (E9), driven through STARTUPE2: it has no XDC line.

## Clock: 100 MHz oscillator
set_property -dict { PACKAGE_PIN E3    IOSTANDARD LVCMOS33 } [get_ports { CLK100MHZ }];
create_clock -add -name sys_clk_pin -period 10.00 -waveform {0 5} [get_ports { CLK100MHZ }];

## Reset button (active low)
set_property -dict { PACKAGE_PIN C12   IOSTANDARD LVCMOS33 } [get_ports { CPU_RESETN }];

## USB-UART (names from the host's side: the FPGA receives on UART_TXD_IN)
set_property -dict { PACKAGE_PIN C4    IOSTANDARD LVCMOS33 } [get_ports { UART_TXD_IN }];
set_property -dict { PACKAGE_PIN D4    IOSTANDARD LVCMOS33 } [get_ports { UART_RXD_OUT }];

## Quad-SPI configuration flash, used here as single-bit SPI, read-only (JEDEC ID)
set_property -dict { PACKAGE_PIN K17   IOSTANDARD LVCMOS33 } [get_ports { QSPI_DQ0 }];
set_property -dict { PACKAGE_PIN K18   IOSTANDARD LVCMOS33 } [get_ports { QSPI_DQ1 }];
set_property -dict { PACKAGE_PIN L14   IOSTANDARD LVCMOS33 } [get_ports { QSPI_DQ2 }];
set_property -dict { PACKAGE_PIN M14   IOSTANDARD LVCMOS33 } [get_ports { QSPI_DQ3 }];
set_property -dict { PACKAGE_PIN L13   IOSTANDARD LVCMOS33 } [get_ports { QSPI_CSN }];

## Configuration bank voltage (Nexys A7: CFGBVS tied to VCCO = 3.3 V)
set_property CFGBVS VCCO [current_design];
set_property CONFIG_VOLTAGE 3.3 [current_design];
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design];

## Asynchronous inputs: CPU_RESETN goes through reset_sync.sv, UART RX and the flash's
## SO (DQ1) through two ASYNC_REG flops; SO is sampled at the end of each 500 ns SCK
## high half. A zero input delay marks them constrained; the false path removes them.
set async_in [get_ports {CPU_RESETN UART_TXD_IN QSPI_DQ1}]
set_input_delay -clock sys_clk_pin 0.000 $async_in
set_false_path -from $async_in

## Slow outputs: UART TX every 868 clocks; the flash outputs change every 50 clocks
## (1 MHz SCK) from registers, or are constant (DQ2, DQ3).
set slow_out [get_ports {UART_RXD_OUT QSPI_DQ0 QSPI_DQ2 QSPI_DQ3 QSPI_CSN}]
set_output_delay -clock sys_clk_pin 0.000 $slow_out
set_false_path -to $slow_out
