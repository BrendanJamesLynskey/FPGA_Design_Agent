link_design -part xck26-sfvc784-2LV-c
foreach s [get_sites -quiet -filter {SITE_TYPE =~ IBUFDS_GTE4*}] { puts "SITE $s [get_property SITE_TYPE $s] [get_property CLOCK_REGION $s]" }
foreach s [get_sites -quiet -filter {SITE_TYPE =~ BUFG_GT*}] { puts "SITEB $s [get_property SITE_TYPE $s] [get_property CLOCK_REGION $s]" }
foreach p [get_package_pins -quiet -filter {PIN_FUNC =~ MGTREFCLK*}] { puts "REF $p [get_property PIN_FUNC $p] sites=[get_sites -quiet -of_objects $p]" }
puts "BANK-SITES-OF-REFCLK-DONE"
