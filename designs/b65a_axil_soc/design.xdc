## design.xdc: B65A (b65a_axil_soc_top, generated from blockdesign.yaml) on the Nexys A7-100T.
## Pins and IOSTANDARDs are copied from Digilent's master XDC
## (boards/nexys_a7_100t/Nexys-A7-100T-Master.xdc, MIT, pinned commit in boards/nexys_a7_100t/README.md);
## only the pins this design uses are here.

## Clock: 100 MHz oscillator
set_property -dict { PACKAGE_PIN E3    IOSTANDARD LVCMOS33 } [get_ports { CLK100MHZ }];
create_clock -add -name sys_clk_pin -period 10.00 -waveform {0 5} [get_ports { CLK100MHZ }];

## Reset button (active low)
set_property -dict { PACKAGE_PIN C12   IOSTANDARD LVCMOS33 } [get_ports { CPU_RESETN }];

## LEDs
set_property -dict { PACKAGE_PIN H17   IOSTANDARD LVCMOS33 } [get_ports { LED[0] }];
set_property -dict { PACKAGE_PIN K15   IOSTANDARD LVCMOS33 } [get_ports { LED[1] }];
set_property -dict { PACKAGE_PIN J13   IOSTANDARD LVCMOS33 } [get_ports { LED[2] }];
set_property -dict { PACKAGE_PIN N14   IOSTANDARD LVCMOS33 } [get_ports { LED[3] }];
set_property -dict { PACKAGE_PIN R18   IOSTANDARD LVCMOS33 } [get_ports { LED[4] }];
set_property -dict { PACKAGE_PIN V17   IOSTANDARD LVCMOS33 } [get_ports { LED[5] }];
set_property -dict { PACKAGE_PIN U17   IOSTANDARD LVCMOS33 } [get_ports { LED[6] }];
set_property -dict { PACKAGE_PIN U16   IOSTANDARD LVCMOS33 } [get_ports { LED[7] }];
set_property -dict { PACKAGE_PIN V16   IOSTANDARD LVCMOS33 } [get_ports { LED[8] }];
set_property -dict { PACKAGE_PIN T15   IOSTANDARD LVCMOS33 } [get_ports { LED[9] }];
set_property -dict { PACKAGE_PIN U14   IOSTANDARD LVCMOS33 } [get_ports { LED[10] }];
set_property -dict { PACKAGE_PIN T16   IOSTANDARD LVCMOS33 } [get_ports { LED[11] }];
set_property -dict { PACKAGE_PIN V15   IOSTANDARD LVCMOS33 } [get_ports { LED[12] }];
set_property -dict { PACKAGE_PIN V14   IOSTANDARD LVCMOS33 } [get_ports { LED[13] }];
set_property -dict { PACKAGE_PIN V12   IOSTANDARD LVCMOS33 } [get_ports { LED[14] }];
set_property -dict { PACKAGE_PIN V11   IOSTANDARD LVCMOS33 } [get_ports { LED[15] }];


## USB-UART (names from the host's side: the FPGA receives on UART_TXD_IN)
set_property -dict { PACKAGE_PIN C4    IOSTANDARD LVCMOS33 } [get_ports { UART_TXD_IN }];
set_property -dict { PACKAGE_PIN D4    IOSTANDARD LVCMOS33 } [get_ports { UART_RXD_OUT }];

## Configuration bank voltage (Nexys A7: CFGBVS tied to VCCO = 3.3 V)
set_property CFGBVS VCCO [current_design];
set_property CONFIG_VOLTAGE 3.3 [current_design];
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design];

## Asynchronous inputs. UART RX has no timing relationship to sys_clk_pin: it is synchronised by two ASYNC_REG flops
## inside the shell (sync2.sv), and CPU_RESETN goes through the reset synchroniser that block automation added
## (reset_sync.sv: asynchronous assert, synchronous release). A zero input delay marks them as constrained for
## check_timing; the false path then removes them from timing analysis.
set async_in [get_ports {CPU_RESETN UART_TXD_IN}]
set_input_delay -clock sys_clk_pin 0.000 $async_in
set_false_path -from $async_in

## Slow outputs. The LEDs show the tone's top byte (changing at most once a sample tick) and UART TX changes every
## 868 clocks; nothing outside samples them against sys_clk_pin, so they carry no output timing requirement.
set slow_out [get_ports {LED[*] UART_RXD_OUT}]
set_output_delay -clock sys_clk_pin 0.000 $slow_out
set_false_path -to $slow_out
