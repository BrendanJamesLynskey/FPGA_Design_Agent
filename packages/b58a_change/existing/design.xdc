# design.xdc: kr260_top on the Kria KR260 (xck26-sfvc784-2LV-c).
# Pins: AMD board files kr260_carrier 1.1 (pl_gem2, pl_gem3, User_led, hpa_clk0p_clk) mapped to package pins through
# kr260_som 1.1 part0_pins.xml (Apache-2.0, shipped with Vivado); PHY2 agrees with the project knowledge base (board/kr260/ethernet)
# (an open-source reference design). All PL Ethernet pins are in the 1.8 V HP banks (LVCMOS18).

# ---- clock in: 25 MHz on HPA_CLK0P (the frequency is an open-source reference design's figure, unconfirmed) ----
set_property -dict {PACKAGE_PIN C3 IOSTANDARD LVCMOS18} [get_ports clk_25]
create_clock -name clk_25 -period 40.000 [get_ports clk_25]

# ---- port A: PHY2, J10B (Ethernet 2) ----
set_property -dict {PACKAGE_PIN D4 IOSTANDARD LVCMOS18} [get_ports a_rxc]
set_property -dict {PACKAGE_PIN A1 IOSTANDARD LVCMOS18} [get_ports {a_rxd[0]}]
set_property -dict {PACKAGE_PIN B3 IOSTANDARD LVCMOS18} [get_ports {a_rxd[1]}]
set_property -dict {PACKAGE_PIN A3 IOSTANDARD LVCMOS18} [get_ports {a_rxd[2]}]
set_property -dict {PACKAGE_PIN B4 IOSTANDARD LVCMOS18} [get_ports {a_rxd[3]}]
set_property -dict {PACKAGE_PIN A4 IOSTANDARD LVCMOS18} [get_ports a_rx_ctl]
set_property -dict {PACKAGE_PIN A2 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports a_txc]
set_property -dict {PACKAGE_PIN E1 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {a_txd[0]}]
set_property -dict {PACKAGE_PIN D1 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {a_txd[1]}]
set_property -dict {PACKAGE_PIN F2 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {a_txd[2]}]
set_property -dict {PACKAGE_PIN E2 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {a_txd[3]}]
set_property -dict {PACKAGE_PIN F1 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports a_tx_ctl]
set_property -dict {PACKAGE_PIN B1 IOSTANDARD LVCMOS18} [get_ports a_rst_n]
set_property -dict {PACKAGE_PIN F3 IOSTANDARD LVCMOS18 PULLUP TRUE} [get_ports a_mdio]
set_property -dict {PACKAGE_PIN G3 IOSTANDARD LVCMOS18} [get_ports a_mdc]

# ---- port B: PHY3, J10A (Ethernet 3) ----
set_property -dict {PACKAGE_PIN K4 IOSTANDARD LVCMOS18} [get_ports b_rxc]
set_property -dict {PACKAGE_PIN H1 IOSTANDARD LVCMOS18} [get_ports {b_rxd[0]}]
set_property -dict {PACKAGE_PIN K2 IOSTANDARD LVCMOS18} [get_ports {b_rxd[1]}]
set_property -dict {PACKAGE_PIN J2 IOSTANDARD LVCMOS18} [get_ports {b_rxd[2]}]
set_property -dict {PACKAGE_PIN H4 IOSTANDARD LVCMOS18} [get_ports {b_rxd[3]}]
set_property -dict {PACKAGE_PIN H3 IOSTANDARD LVCMOS18} [get_ports b_rx_ctl]
set_property -dict {PACKAGE_PIN J1 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports b_txc]
set_property -dict {PACKAGE_PIN U9 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {b_txd[0]}]
set_property -dict {PACKAGE_PIN V9 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {b_txd[1]}]
set_property -dict {PACKAGE_PIN U8 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {b_txd[2]}]
set_property -dict {PACKAGE_PIN V8 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports {b_txd[3]}]
set_property -dict {PACKAGE_PIN Y8 IOSTANDARD LVCMOS18 SLEW FAST DRIVE 12} [get_ports b_tx_ctl]
set_property -dict {PACKAGE_PIN K1 IOSTANDARD LVCMOS18} [get_ports b_rst_n]
set_property -dict {PACKAGE_PIN T8 IOSTANDARD LVCMOS18 PULLUP TRUE} [get_ports b_mdio]
set_property -dict {PACKAGE_PIN R8 IOSTANDARD LVCMOS18} [get_ports b_mdc]

# ---- user LEDs (AMD board files) ----
set_property -dict {PACKAGE_PIN F8 IOSTANDARD LVCMOS18 SLEW SLOW DRIVE 8} [get_ports {led[0]}]
set_property -dict {PACKAGE_PIN E8 IOSTANDARD LVCMOS18 SLEW SLOW DRIVE 8} [get_ports {led[1]}]

# ---- RGMII receive: each port's RX_CLK, 125 MHz at 1000 Mb/s (T = 8 ns) ----
# Derivation. The PHY launches a nibble on each edge of its own clock: the low nibble on the rising edge, the high
# nibble on the falling edge. With the PHY's internal RX delay on (M88E1111 register 20 bit 7, set over MDIO before
# use), the RX_CLK it drives is shifted by about T/4 so that each data nibble is centred on the RX_CLK edge that should
# capture it: the low nibble on the rising edge, the high nibble on the falling edge. The PHY's datasheet (Marvell
# 88E1111, MV-S100649-00 Rev. M, section 4.12.2, the RX_CLK output table for register 20 bit 7 = 1) gives data valid
# at least tSU = 1.2 ns before and tH = 1.2 ns after that edge (the RGMII v2.0 figures with the delay are the same).
# Vivado's model: a virtual clock in phase with RX_CLK at the pins launches each nibble half a period before the edge
# that captures it, so a nibble captured on the rising edge is launched on the virtual falling edge and vice versa.
#   setup (max): arrival must be T/2 - tSU after the launch edge         -> -max = 4.0 - 1.2 = 2.8 ns
#   hold  (min): the next nibble may change only tH after the capture edge -> -min = tH = 1.2 ns
# The capture clock is RX_CLK through a global buffer, which delays the IDDRE1 edge by about 2 ns; without more, the
# hold check fails (routed: -0.74 ns). Each data input therefore goes through an IDELAYE3 (rtl/kr260_top.sv,
# RX_IDELAY_PS) that moves the data window onto the delayed edge; the analysis below then checks both sides.
# These are the intended checks: setup between opposite edges (requirement T/2 = 4 ns) and hold on the same edge
# (requirement 0). They are also Vivado's most restrictive pairs, so no exception is needed: the other pairs (setup
# over a full period, hold against the edge before) are looser and never the worst. flow/io_check.py checks the
# applied requirements (IO-DDR-REQUIREMENT), with the interfaces declared in build.yaml.
create_clock -name a_rxc -period 8.000 [get_ports a_rxc]
create_clock -name b_rxc -period 8.000 [get_ports b_rxc]
create_clock -name a_rxc_v -period 8.000
create_clock -name b_rxc_v -period 8.000
# port A, nibbles captured on the falling edge (launched on the virtual rising edge): max = T/2 - tSU, min = tH
set_input_delay -clock a_rxc_v -max 2.800 [get_ports {a_rxd[*] a_rx_ctl}]
set_input_delay -clock a_rxc_v -min 1.200 [get_ports {a_rxd[*] a_rx_ctl}]
# port A, nibbles captured on the rising edge (launched on the virtual falling edge): max = T/2 - tSU, min = tH
set_input_delay -clock a_rxc_v -clock_fall -max 2.800 -add_delay [get_ports {a_rxd[*] a_rx_ctl}]
set_input_delay -clock a_rxc_v -clock_fall -min 1.200 -add_delay [get_ports {a_rxd[*] a_rx_ctl}]
# port B, the same: max = T/2 - tSU = 2.8 ns, min = tH = 1.2 ns
set_input_delay -clock b_rxc_v -max 2.800 [get_ports {b_rxd[*] b_rx_ctl}]
set_input_delay -clock b_rxc_v -min 1.200 [get_ports {b_rxd[*] b_rx_ctl}]
# port B, falling-edge launch: max = T/2 - tSU = 2.8 ns, min = tH = 1.2 ns
set_input_delay -clock b_rxc_v -clock_fall -max 2.800 -add_delay [get_ports {b_rxd[*] b_rx_ctl}]
set_input_delay -clock b_rxc_v -clock_fall -min 1.200 -add_delay [get_ports {b_rxd[*] b_rx_ctl}]

# ---- RGMII transmit: data on both edges of the core clock, TXC forwarded edge-aligned, PHY TX delay on ----
# Derivation. ODDRE1 launches the low nibble on the rising edge of the core clock and the high nibble on its falling
# edge. TXC comes from the same clock through the same kind of ODDRE1 (rtl/rgmii_tx.sv, TXC_CLK90 = 0), so it leaves
# edge-aligned with the data, and the PHY delays GTX_CLK itself (M88E1111 register 20 bit 1 = 1, set over MDIO before
# use). The PHY's own input requirement in that mode (Marvell 88E1111 datasheet, MV-S100649-00 Rev. M, section 4.12.2,
# the GTX_CLK input table for register 20 bit 1 = 1), in our words: measured at the PHY pins from a TXC edge, the
# data must have settled by 0.9 ns after the edge (its set-up figure is negative) and must stay until 2.7 ns after
# it. So, around each TXC edge, a data change may come
#   up to skew_after  = 0.9 ns after its own edge, and
#   no earlier than skew_before = T/2 - 2.7 = 1.3 ns before the next edge.
# (Wider than RGMII v2.0's generic +/-0.5 ns, which an earlier build used and missed by up to 0.2 ns.)
# Board: the KR260's TXC-to-TXD trace skew is not in our notes, so an ASSUMED allowance of 0.1 ns (either sign) is taken
# off both sides: skew_after = 0.8 ns, skew_before = 1.2 ns. Vivado's model: the generated clock TXC captures each
# nibble on the opposite edge (requirement T/2) for set-up and on its own edge (requirement 0) for hold:
#   setup (max): the nibble must have settled skew_after after its own edge -> -max = T/2 - skew_after = 4.0 - 0.8 = 3.2 ns
#   hold  (min): it must not change earlier than skew_before before the next edge; an output's hold required time is
#                the edge minus -min                                     -> -min = +skew_before = +1.2 ns
# These are Vivado's most restrictive pairs as well, so no exception is needed. build.yaml carries the same numbers
# (data_sheet skew_before_ns 1.3, skew_after_ns 0.9, board_skew_ns 0.1) and flow/io_check.py derives -max/-min from
# them (IO-VALUE). (A TXC from a 90-degree MMCM output on a second global buffer, PHY TX delay off, was built and
# routed as well and did not close: results/b58a/build_tx_centred_trial.)
create_generated_clock -name a_txc -source [get_pins u_atx/u_txc/C] -multiply_by 1 [get_ports a_txc]
create_generated_clock -name b_txc -source [get_pins u_btx/u_txc/C] -multiply_by 1 [get_ports b_txc]
# port A, both edges: max = T/2 - skew_after = 3.2 ns, min = +skew_before = +1.2 ns
set_output_delay -clock a_txc -max 3.200 [get_ports {a_txd[*] a_tx_ctl}]
set_output_delay -clock a_txc -min 1.200 [get_ports {a_txd[*] a_tx_ctl}]
set_output_delay -clock a_txc -clock_fall -max 3.200 -add_delay [get_ports {a_txd[*] a_tx_ctl}]
set_output_delay -clock a_txc -clock_fall -min 1.200 -add_delay [get_ports {a_txd[*] a_tx_ctl}]
# port B, both edges: max = T/2 - skew_after = 3.2 ns, min = +skew_before = +1.2 ns
set_output_delay -clock b_txc -max 3.200 [get_ports {b_txd[*] b_tx_ctl}]
set_output_delay -clock b_txc -min 1.200 [get_ports {b_txd[*] b_tx_ctl}]
set_output_delay -clock b_txc -clock_fall -max 3.200 -add_delay [get_ports {b_txd[*] b_tx_ctl}]
set_output_delay -clock b_txc -clock_fall -min 1.200 -add_delay [get_ports {b_txd[*] b_tx_ctl}]

# ---- JTAG register front end: BSCANE2 (the clock is defined on INTERNAL_TCK, as AMD's own debug IP does) ----
create_clock -name tck -period 33.333 [get_pins u_jtag/u_bscan/INTERNAL_TCK]
create_generated_clock -name tck_out -source [get_pins u_jtag/u_bscan/INTERNAL_TCK] -divide_by 1 [get_pins u_jtag/u_bscan/TCK]
# TDO: the shift register (TCK) to the primitive's TDO, timed within the TCK clocks (no exception: a false path here
# makes report_cdc call it a crossing into a non-FD primitive, CDC-13)

# Clock-domain crossings (each RX_CLK, TCK and the core clock) are all inside XPM macros, which carry their own
# constraints; there is no set_clock_groups, so any other crossing would show as a timing failure.
# The one path XPM leaves timed as synchronous: each xpm_fifo_async (distributed RAM) is written on RX_CLK and read
# into its output register on the core clock. The read address only reaches an entry after the write pointer has
# crossed (two synchroniser stages), so the data path needs only to settle within one core clock period: 8 ns.
set_max_delay -datapath_only 8.000 -from [get_clocks a_rxc] -to [get_cells -hierarchical -filter {NAME =~ u_acdc/u_fifo/*doutb_reg_reg*}]
set_max_delay -datapath_only 8.000 -from [get_clocks b_rxc] -to [get_cells -hierarchical -filter {NAME =~ u_bcdc/u_fifo/*doutb_reg_reg*}]

# ---- slow pins: PHY resets (held 16.8 ms), MDIO (1.95 MHz, the input synchronised by xpm_cdc_single), LEDs ----
# No timing relationship to any clock: 0 ns placeholder delays and false paths (flow/io_check.py rules).
set_output_delay -clock [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]] 0.000 [get_ports {a_rst_n b_rst_n a_mdc b_mdc a_mdio b_mdio led[*]}]
set_input_delay -clock [get_clocks -of_objects [get_pins u_mmcm/CLKOUT0]] 0.000 [get_ports {a_mdio b_mdio}]
set_false_path -to [get_ports {a_rst_n b_rst_n a_mdc b_mdc a_mdio b_mdio led[*]}]
set_false_path -from [get_ports {a_mdio b_mdio}]
