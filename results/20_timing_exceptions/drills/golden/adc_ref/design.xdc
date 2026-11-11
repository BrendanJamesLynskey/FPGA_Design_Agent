## design.xdc: reference for drill d20_adc_capture (Nexys A7-100T); pins from the board's master XDC.
set_property -dict { PACKAGE_PIN E3    IOSTANDARD LVCMOS33 } [get_ports { CLK100MHZ }];
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
set_property -dict { PACKAGE_PIN C12   IOSTANDARD LVCMOS33 } [get_ports { CPU_RESETN }];
set_property -dict { PACKAGE_PIN C17   IOSTANDARD LVCMOS33 } [get_ports { JA1 }];
set_property -dict { PACKAGE_PIN D18   IOSTANDARD LVCMOS33 } [get_ports { JA2 }];
set_property -dict { PACKAGE_PIN E18   IOSTANDARD LVCMOS33 } [get_ports { JA3 }];
set_property -dict { PACKAGE_PIN G17   IOSTANDARD LVCMOS33 } [get_ports { JA4 }];
set_property -dict { PACKAGE_PIN D17   IOSTANDARD LVCMOS33 } [get_ports { JA7 }];
set_property -dict { PACKAGE_PIN E17   IOSTANDARD LVCMOS33 } [get_ports { JA8 }];
set_property -dict { PACKAGE_PIN F18   IOSTANDARD LVCMOS33 } [get_ports { JA9 }];
set_property -dict { PACKAGE_PIN G18   IOSTANDARD LVCMOS33 } [get_ports { JA10 }];
set_property -dict { PACKAGE_PIN C4    IOSTANDARD LVCMOS33 } [get_ports { UART_TXD_IN }];
set_property -dict { PACKAGE_PIN D4    IOSTANDARD LVCMOS33 } [get_ports { UART_RXD_OUT }];
set_property CFGBVS VCCO [current_design];
set_property CONFIG_VOLTAGE 3.3 [current_design];
create_clock -add -name sys_clk_pin -period 10.00 -waveform {0 5} [get_ports { CLK100MHZ }];
## The oscillator's data sheet: 50 ps period jitter (peak-to-peak), as set_input_jitter expects (UG903 ch. 3)
set_input_jitter [get_clocks sys_clk_pin] 0.050

## ADC on JA (system-synchronous: the board oscillator clocks the ADC and CLK100MHZ, clock traces matched).
## Data sheet: tCO 1.0 ns min, 5.0 ns max; board: data trace 0.5 ns.
## -max = tCO_max + trace = 5.0 + 0.5 = 5.5 ns; -min = tCO_min + trace = 1.0 + 0.5 = 1.5 ns
set adc_in [get_ports {JA1 JA2 JA3 JA4 JA7 JA8 JA9 JA10}]
set_input_delay -clock sys_clk_pin -max 5.500 $adc_in
set_input_delay -clock sys_clk_pin -min 1.500 $adc_in

## Asynchronous inputs: CPU_RESETN goes through reset_sync.sv and UART_TXD_IN through the shell's sync2 (ASYNC_REG);
## a zero input delay marks them constrained, the false path takes them out of timing analysis.
set async_in [get_ports {CPU_RESETN UART_TXD_IN}]
set_input_delay -clock sys_clk_pin 0.000 $async_in
set_false_path -from $async_in
## Slow outputs: LEDs (a person) and UART TX (868 clocks a bit); nothing samples them against sys_clk_pin.
set slow_out [get_ports {LED[*] UART_RXD_OUT}]
set_output_delay -clock sys_clk_pin 0.000 $slow_out
set_false_path -to $slow_out
