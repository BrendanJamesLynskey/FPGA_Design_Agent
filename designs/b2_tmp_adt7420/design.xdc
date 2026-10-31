## design.xdc: board self-check B2TS (b2_tmp_adt7420_top) on the Nexys A7-100T.
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

## ADT7420 temperature sensor, I2C (open drain; 1 kohm pull-ups to 3.3 V on the board)
set_property -dict { PACKAGE_PIN C14   IOSTANDARD LVCMOS33 } [get_ports { TMP_SCL }];
set_property -dict { PACKAGE_PIN C15   IOSTANDARD LVCMOS33 } [get_ports { TMP_SDA }];

## Configuration bank voltage (Nexys A7: CFGBVS tied to VCCO = 3.3 V)
set_property CFGBVS VCCO [current_design];
set_property CONFIG_VOLTAGE 3.3 [current_design];
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design];

## Asynchronous inputs: CPU_RESETN goes through reset_sync.sv, UART RX and both I2C
## lines through two ASYNC_REG flops. A zero input delay marks them constrained for
## check_timing; the false path removes them from timing analysis.
set async_in [get_ports {CPU_RESETN UART_TXD_IN TMP_SCL TMP_SDA}]
set_input_delay -clock sys_clk_pin 0.000 $async_in
set_false_path -from $async_in

## Slow outputs: UART TX changes every 868 clocks; the I2C lines are registered
## open-drain enables that change every 250 clocks (100 kHz SCL). Nothing samples
## them against sys_clk_pin, so they carry no output timing requirement.
set slow_out [get_ports {UART_RXD_OUT TMP_SCL TMP_SDA}]
set_output_delay -clock sys_clk_pin 0.000 $slow_out
set_false_path -to $slow_out
