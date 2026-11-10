## design.xdc: reference for drill d20_slow_fsm_ramp (Nexys A7-100T); pins from the board's master XDC.
set_property -dict { PACKAGE_PIN E3    IOSTANDARD LVCMOS33 } [get_ports { CLK100MHZ }];
set_property -dict { PACKAGE_PIN C12   IOSTANDARD LVCMOS33 } [get_ports { CPU_RESETN }];
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
set_property -dict { PACKAGE_PIN C4    IOSTANDARD LVCMOS33 } [get_ports { UART_TXD_IN }];
set_property -dict { PACKAGE_PIN D4    IOSTANDARD LVCMOS33 } [get_ports { UART_RXD_OUT }];
set_property CFGBVS VCCO [current_design];
set_property CONFIG_VOLTAGE 3.3 [current_design];
create_clock -add -name sys_clk_pin -period 10.00 -waveform {0 5} [get_ports { CLK100MHZ }];

## Asynchronous inputs: CPU_RESETN goes through reset_sync.sv and UART_TXD_IN through the shell's sync2 (ASYNC_REG);
## a zero input delay marks them constrained, the false path takes them out of timing analysis.
set async_in [get_ports {CPU_RESETN UART_TXD_IN}]
set_input_delay -clock sys_clk_pin 0.000 $async_in
set_false_path -from $async_in
## Slow outputs: LEDs change at most once per tick, UART TX every 868 clocks; nothing samples them against sys_clk_pin.
set slow_out [get_ports {LED[*] UART_RXD_OUT}]
set_output_delay -clock sys_clk_pin 0.000 $slow_out
set_false_path -to $slow_out

## The controller (st, level) and the fast unit's copy (level_q) load only when tick is 1, and tick (the clock enable)
## is 1 on one clock in 8: paths between two of these registers have 8 clocks. Setup 8, hold 7 (UG903 ch. 5).
## The RTL tags exactly these registers fda_slow_en; the copy is tick-qualified (it samples the level only on the tick).
set slow_regs [get_cells -hier -filter {fda_slow_en == true}]
set_multicycle_path 8 -setup -from [all_registers] -to [all_registers]
set_multicycle_path 7 -hold -from [all_registers] -to [all_registers]
