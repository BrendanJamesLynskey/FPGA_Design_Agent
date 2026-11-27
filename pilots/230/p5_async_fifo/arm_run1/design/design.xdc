## design.xdc: pins and I/O standards from the board's master XDC (kr260-pins.xdc), timing lines appended.

set_property -dict { PACKAGE_PIN C3   IOSTANDARD LVCMOS18 } [get_ports { clk_c3 }];  # clk_25
create_clock -add -name sys_clk_pin -period 40.00 -waveform {0 20} [get_ports { clk_c3 }];
set_property -dict { PACKAGE_PIN F8   IOSTANDARD LVCMOS18 } [get_ports { led[0] }];  # led[0]
set_property -dict { PACKAGE_PIN E8   IOSTANDARD LVCMOS18 } [get_ports { led[1] }];  # led[1]
set_property -dict { PACKAGE_PIN Y10  IOSTANDARD LVCMOS33 } [get_ports { sfp_tx_disable }];  # sfp_tx_disable

# The 156.25 MHz gt_refclk (SFP cage MGTREFCLK0) is created by the flow in known_pre.xdc on gt_refclk_p; not redefined here

# The JTAG TCK and the USR_ACCESSE2 CCLK (flow-created clocks) are unrelated to the 25 MHz write clock
set_clock_groups -asynchronous -group [get_clocks usr_cclk] -group [get_clocks sys_clk_pin]
set_clock_groups -asynchronous -group [get_clocks jtag_tck] -group [get_clocks sys_clk_pin]

# clk_wr (25 MHz) and clk_rd (156.25 MHz) are asynchronous: crossings are xpm_cdc primitives, bounded datapath-only
# (a clock group here would override the max delay, TIMING-24); the flow adds the matching xpm constraints and led/sfp false paths
set_max_delay -datapath_only -from [get_clocks sys_clk_pin] -to [get_clocks gt_refclk] 6.4
