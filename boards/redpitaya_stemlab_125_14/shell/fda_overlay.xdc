# fda_overlay.xdc: our constraints for the Red Pitaya shell build (brief 235). Read after the vendor's own constraint files (tools/rp_shell.py --overlay);
# the vendor's files are never edited. What the build measured (Vivado 2026.1, vendor commit 728a4f37e9, results/235_redpitaya/): without this file the
# vendor shell misses timing by -5.3 ns in its own logic. None of that is a clock-crossing constraint that was dropped: every failing path is an ordinary
# same-clock path through a vendor instrument (the arbitrary-generator AXI engine on the 250 MHz AXI clock: 17 to 21 logic levels where 4 ns allows
# about 5; the AXI masters on the HP2 and HP3 ports; the generator's own pointer logic and the oscilloscope's decimator and calibration on the 125 MHz
# clock). The vendor's own constraint file names a register (dac_rd_clr_r*) that no longer exists in its RTL, so that one exception matches nothing.
#
# This image is the board as a TARGET: the owner's block (slot 7 or 6) is the instrument, the vendor's oscilloscope and generator are not used and nothing
# in the owner's scripts starts them (their registers read zero after the load). The two waivers below remove the paths into and out of the vendor
# instruments from the timing analysis so that the figure that remains is the figure for the logic this image is for: the shell's bus, the ADC and DAC
# front end, the housekeeping, and the owner's blocks. They do NOT make the vendor instruments work at speed: with this image loaded, the
# deep-memory generator, the generator's own waveform engine and the oscilloscope are not claimed to work (unproven, the paths above fail).

# The vendor's arbitrary-generator and oscilloscope logic, and the two AXI master bridges that carry their deep memory (HP2 and HP3), are not used by
# this image; their registers stay at the reset value 0 (generator off, scope not triggered) because nothing writes them. The block-to-DAC term
# (user_dac) is a separate path and stays timed.
# The synthesised netlist is flat, so the instruments are named by the leaf cells under their hierarchy names.
set fda_vendor_instr [get_cells -quiet -hierarchical -filter {NAME =~ i_asg/* || NAME =~ i_scope/* || NAME =~ ps/axi_master_2/* || NAME =~ ps/axi_master_3/*}]
set_false_path -from $fda_vendor_instr
set_false_path -to   $fda_vendor_instr
