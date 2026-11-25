## design.xdc: pins from the board's master XDC (kr260-pins.xdc); timing lines appended.

set_property -dict { PACKAGE_PIN C3   IOSTANDARD LVCMOS18 } [get_ports { c3_clk }];  # clk_25
create_clock -add -name c3_clk_pin -period 40.00 -waveform {0 20} [get_ports { c3_clk }];
set_property -dict { PACKAGE_PIN F8   IOSTANDARD LVCMOS18 } [get_ports { led[0] }];  # led[0]
set_property -dict { PACKAGE_PIN E8   IOSTANDARD LVCMOS18 } [get_ports { led[1] }];  # led[1]
set_property -dict { PACKAGE_PIN Y10  IOSTANDARD LVCMOS33 } [get_ports { sfp_tx_disable }];  # sfp_tx_disable

# 156.25 MHz GT reference clock (MGTREFCLK0 of the SFP quad); the input buffer is placed by its GT refclk site.
set_property PACKAGE_PIN Y6 [get_ports { ref_clk_p }];
set_property PACKAGE_PIN Y5 [get_ports { ref_clk_n }];
create_clock -name ref_clk_pin -period 6.40 [get_ports { ref_clk_p }];

# JTAG TCK from the BSCANE2 inside jtag_bus: a clock of its own (nominally up to 33 MHz, constrained at 100 ns).
create_clock -name jtag_tck -period 100.00 [get_pins { u_bus/u_bscan/INTERNAL_TCK }];

# USR_ACCESSE2 config clock (CCLK pin): its DATA is constant after configuration, so it is read as a static word.
create_clock -name usr_cclk -period 20.00 [get_pins { u_core/u_usr/CCLK }];

# The clocks are unrelated (asynchronous); every crossing goes through an xpm_cdc primitive.
set_false_path -from [get_clocks ref_clk_pin] -to [get_clocks c3_clk_pin]
set_false_path -from [get_clocks usr_cclk] -to [get_clocks ref_clk_pin]
# c3->ref, jtag->ref and ref->jtag crossings end at xpm_cdc synchroniser inputs, which the
# xpm_cdc scoped constraints already cut; a second exception there would be overridden.

# LED and SFP disable outputs are static or slow indicators with no external timing relation:
# zero output delay (so check_timing sees a delay) and no timing check.
set LED_PORTS [get_ports { led[*] sfp_tx_disable }]
set_output_delay -clock [get_clocks c3_clk_pin] 0.000 $LED_PORTS
set_false_path -to $LED_PORTS
