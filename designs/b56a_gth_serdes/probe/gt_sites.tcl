# gt_sites.tcl (brief 56A): the GT pins and sites of the KR260 part on Vivado 2026.1.
#   vivado -mode batch -source designs/b56a_gth_serdes/probe/gt_sites.tcl      (a bare link_design -part: no netlist, no licence feature used)
# Output lines FUNC / MGTPIN / SITE are what results/56a_serdes/gt_sites.txt and flow/gt_parts/xck26.json hold.
link_design -part xck26-sfvc784-2LV-c
foreach pf {MGTHRXP2_224 MGTHRXN2_224 MGTHTXP2_224 MGTHTXN2_224 MGTREFCLK0P_224 MGTREFCLK0N_224 MGTREFCLK1P_224} {
  foreach p [get_package_pins -quiet -filter "PIN_FUNC == $pf"] {
    puts "FUNC $pf -> pin $p  sites=[get_sites -quiet -of_objects $p] props=[list_property $p]"
  }
}
foreach p [get_package_pins -filter {PIN_FUNC =~ MGT*}] { puts "MGTPIN $p [get_property PIN_FUNC $p] [get_sites -quiet -of_objects $p]" }
foreach s [get_sites -quiet -filter {NAME =~ *GTHE4* || NAME =~ *IBUFDS_GTE4*}] { puts "SITE $s [get_property SITE_TYPE $s] [get_property CLOCK_REGION $s]" }
