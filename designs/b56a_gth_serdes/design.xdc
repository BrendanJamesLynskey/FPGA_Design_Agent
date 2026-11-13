# design.xdc: kr260_gth_top on the Kria KR260 (xck26-sfvc784-2LV-c), SFP+ cage J24 on GTH quad 224 channel 2.
# Pins: package pins and GT sites resolved on Vivado 2026.1 with get_package_pins/get_sites (results/56a_serdes/gt_sites.txt):
#   MGTHRXP/N2_224 = T2/T1, MGTHTXP/N2_224 = R4/R3 -> GTHE4_CHANNEL_X0Y6; MGTREFCLK0P/N_224 = Y6/Y5 -> GTHE4_COMMON_X0Y1.
# The SFP+ control and I2C pin functions come from an open-source KR260 example (not AMD, not the schematic): unconfirmed.
# The pin-to-SOM-pin mapping is from the AMD board files (kr260_carrier/kr260_som 1.1), see the knowledge bank board/kr260.

# ---- 25 MHz input (the frequency is an open-source reference design's figure, unconfirmed) ----
set_property -dict {PACKAGE_PIN C3 IOSTANDARD LVCMOS18} [get_ports clk_25]
create_clock -name clk_25 -period 40.000 [get_ports clk_25]

# ---- transceiver: reference clock 156.25 MHz (6.400 ns) and the lane ----
set_property PACKAGE_PIN Y6 [get_ports sfp_mgt_refclk_p]
set_property PACKAGE_PIN Y5 [get_ports sfp_mgt_refclk_n]
create_clock -name sfp_mgt_refclk -period 6.400 [get_ports sfp_mgt_refclk_p]
set_property PACKAGE_PIN T2 [get_ports sfp_rx_p]
set_property PACKAGE_PIN T1 [get_ports sfp_rx_n]
set_property PACKAGE_PIN R4 [get_ports sfp_tx_p]
set_property PACKAGE_PIN R3 [get_ports sfp_tx_n]

# ---- SFP+ module control and I2C (3.3 V, banks 43 and 45) ----
set_property -dict {PACKAGE_PIN Y10  IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 8} [get_ports sfp_tx_disable]
set_property -dict {PACKAGE_PIN W10  IOSTANDARD LVCMOS33} [get_ports sfp_mod_abs]
set_property -dict {PACKAGE_PIN J12  IOSTANDARD LVCMOS33} [get_ports sfp_rx_los]
set_property -dict {PACKAGE_PIN A10  IOSTANDARD LVCMOS33} [get_ports sfp_tx_fault]
set_property -dict {PACKAGE_PIN AB11 IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 8} [get_ports sfp_i2c_scl]
set_property -dict {PACKAGE_PIN AC11 IOSTANDARD LVCMOS33 SLEW SLOW DRIVE 8} [get_ports sfp_i2c_sda]

# ---- user LEDs (AMD board files) ----
set_property -dict {PACKAGE_PIN F8 IOSTANDARD LVCMOS18 SLEW SLOW DRIVE 8} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN E8 IOSTANDARD LVCMOS18 SLEW SLOW DRIVE 8} [get_ports {led[1]}]

# ---- JTAG register front end: BSCANE2 (the clock is defined on INTERNAL_TCK, as AMD's own debug IP does) ----
create_clock -name tck -period 33.333 [get_pins u_jtag/u_bscan/INTERNAL_TCK]
create_generated_clock -name tck_out -source [get_pins u_jtag/u_bscan/INTERNAL_TCK] -divide_by 1 [get_pins u_jtag/u_bscan/TCK]

# ---- clock-domain crossings ----
# The free-running clock, the transmit user clock, the receive user clock and TCK are crossed only inside XPM macros (which carry
# their own constraints); there is no set_clock_groups, so any other crossing would show as a timing failure or a report_cdc item.
# The GT user clocks are the clocks Vivado derives from the reference through the QPLL and the BUFG_GT buffers.

# ---- slow board pins: laser disable, module status, I2C, LEDs ----
# No timing relationship to any clock (module status changes in milliseconds; each input goes through an xpm_cdc_single):
# 0 ns placeholder delays and false paths (flow/io_check.py rules), as designs/b58a_trigger.
set_output_delay -clock [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]] 0.000 [get_ports {sfp_tx_disable sfp_i2c_scl sfp_i2c_sda led[*]}]
set_input_delay -clock [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]] 0.000 [get_ports {sfp_mod_abs sfp_rx_los sfp_tx_fault sfp_i2c_scl sfp_i2c_sda}]
set_false_path -to [get_ports {sfp_tx_disable sfp_i2c_scl sfp_i2c_sda led[*]}]
set_false_path -from [get_ports {sfp_mod_abs sfp_rx_los sfp_tx_fault sfp_i2c_scl sfp_i2c_sda}]
