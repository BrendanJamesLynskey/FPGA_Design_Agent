## design.xdc: the SEEDED FAULT variant of b30_hil_audio: identical RTL, but AUD_PWM is constrained to the LED0 pin (H17), so the tone never reaches the audio jack. Passes simulation and every in-FPGA self-check; only a measurement at the pins sees it.
## Pins and IOSTANDARDs are copied from Digilent's master XDC (boards/nexys_a7_100t/Nexys-A7-100T-Master.xdc, MIT).

## Clock: 100 MHz oscillator
set_property -dict { PACKAGE_PIN E3    IOSTANDARD LVCMOS33 } [get_ports { CLK100MHZ }];
create_clock -add -name sys_clk_pin -period 10.00 -waveform {0 5} [get_ports { CLK100MHZ }];

## Reset button (active low)
set_property -dict { PACKAGE_PIN C12   IOSTANDARD LVCMOS33 } [get_ports { CPU_RESETN }];

## USB-UART (names from the host's side: the FPGA receives on UART_TXD_IN)
set_property -dict { PACKAGE_PIN C4    IOSTANDARD LVCMOS33 } [get_ports { UART_TXD_IN }];
set_property -dict { PACKAGE_PIN D4    IOSTANDARD LVCMOS33 } [get_ports { UART_RXD_OUT }];

## PWM audio amplifier (through the board's low-pass filter to the 3.5 mm jack)
set_property -dict { PACKAGE_PIN H17   IOSTANDARD LVCMOS33 } [get_ports { AUD_PWM }];
set_property -dict { PACKAGE_PIN D12   IOSTANDARD LVCMOS33 } [get_ports { AUD_SD }];

## LEDs 0 and 1
set_property -dict { PACKAGE_PIN J13   IOSTANDARD LVCMOS33 } [get_ports { LED[0] }];
set_property -dict { PACKAGE_PIN K15   IOSTANDARD LVCMOS33 } [get_ports { LED[1] }];

## Configuration bank voltage (Nexys A7: CFGBVS tied to VCCO = 3.3 V)
set_property CFGBVS VCCO [current_design];
set_property CONFIG_VOLTAGE 3.3 [current_design];
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design];

## Asynchronous inputs: CPU_RESETN goes through reset_sync.sv, UART RX through two ASYNC_REG flops.
set async_in [get_ports {CPU_RESETN UART_TXD_IN}]
set_input_delay -clock sys_clk_pin 0.000 $async_in
set_false_path -from $async_in

## Slow outputs: LEDs, the audio stage (analogue filter, 97 kHz carrier) and UART TX are sampled by nothing synchronous.
set slow_out [get_ports {LED[*] AUD_PWM AUD_SD UART_RXD_OUT}]
set_output_delay -clock sys_clk_pin 0.000 $slow_out
set_false_path -to $slow_out
