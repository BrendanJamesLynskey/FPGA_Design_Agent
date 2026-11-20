## design.xdc: pins from the board master XDC via board_constraints; timing lines appended.

set_property -dict { PACKAGE_PIN E3   IOSTANDARD LVCMOS33 } [get_ports { CLK100MHZ }];  # CLK100MHZ
create_clock -add -name sys_clk_pin -period 10.00 -waveform {0 5} [get_ports { CLK100MHZ }];
set_property -dict { PACKAGE_PIN C12  IOSTANDARD LVCMOS33 } [get_ports { CPU_RESETN }];  # CPU_RESETN
set_property -dict { PACKAGE_PIN H17  IOSTANDARD LVCMOS33 } [get_ports { LED[0] }];  # LED[0]
set_property -dict { PACKAGE_PIN K15  IOSTANDARD LVCMOS33 } [get_ports { LED[1] }];  # LED[1]
set_property -dict { PACKAGE_PIN J13  IOSTANDARD LVCMOS33 } [get_ports { LED[2] }];  # LED[2]
set_property -dict { PACKAGE_PIN N14  IOSTANDARD LVCMOS33 } [get_ports { LED[3] }];  # LED[3]
set_property -dict { PACKAGE_PIN R18  IOSTANDARD LVCMOS33 } [get_ports { LED[4] }];  # LED[4]
set_property -dict { PACKAGE_PIN V17  IOSTANDARD LVCMOS33 } [get_ports { LED[5] }];  # LED[5]
set_property -dict { PACKAGE_PIN U17  IOSTANDARD LVCMOS33 } [get_ports { LED[6] }];  # LED[6]
set_property -dict { PACKAGE_PIN U16  IOSTANDARD LVCMOS33 } [get_ports { LED[7] }];  # LED[7]
set_property -dict { PACKAGE_PIN V16  IOSTANDARD LVCMOS33 } [get_ports { LED[8] }];  # LED[8]
set_property -dict { PACKAGE_PIN T15  IOSTANDARD LVCMOS33 } [get_ports { LED[9] }];  # LED[9]
set_property -dict { PACKAGE_PIN U14  IOSTANDARD LVCMOS33 } [get_ports { LED[10] }];  # LED[10]
set_property -dict { PACKAGE_PIN T16  IOSTANDARD LVCMOS33 } [get_ports { LED[11] }];  # LED[11]
set_property -dict { PACKAGE_PIN V15  IOSTANDARD LVCMOS33 } [get_ports { LED[12] }];  # LED[12]
set_property -dict { PACKAGE_PIN V14  IOSTANDARD LVCMOS33 } [get_ports { LED[13] }];  # LED[13]
set_property -dict { PACKAGE_PIN V12  IOSTANDARD LVCMOS33 } [get_ports { LED[14] }];  # LED[14]
set_property -dict { PACKAGE_PIN V11  IOSTANDARD LVCMOS33 } [get_ports { LED[15] }];  # LED[15]
set_property -dict { PACKAGE_PIN D4   IOSTANDARD LVCMOS33 } [get_ports { UART_RXD_OUT }];  # UART_RXD_OUT
set_property -dict { PACKAGE_PIN C4   IOSTANDARD LVCMOS33 } [get_ports { UART_TXD_IN }];  # UART_TXD_IN

# Asynchronous inputs (reset button, UART from host) are synchronised inside the design: zero delay plus false path, no invented relationship.
set async_in [get_ports {CPU_RESETN UART_TXD_IN}]
set_input_delay -clock sys_clk_pin 0.0 $async_in
set_false_path -from $async_in

# Outputs (LEDs and UART to host) are slow human/serial signals with no timing relationship: zero delay plus false path.
set slow_out [get_ports {LED[*] UART_RXD_OUT}]
set_output_delay -clock sys_clk_pin 0.0 $slow_out
set_false_path -to $slow_out
