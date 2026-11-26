link_design -part xck26-sfvc784-2LV-c
foreach s [get_sites -quiet -filter {SITE_TYPE == GTHE4_COMMON}] { puts "COMMON $s [get_property CLOCK_REGION $s] bels=[lsort [get_bels -quiet -filter {TYPE =~ IBUFDS*} -of_objects $s]]" }
foreach p [get_package_pins -quiet -filter {PIN_FUNC =~ MGTREFCLK*}] { puts "REF $p [get_property PIN_FUNC $p] [get_sites -quiet -of_objects $p]" }
