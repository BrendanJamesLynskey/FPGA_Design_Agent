# critnets.tcl: the signal nets on the worst setup paths of a routed checkpoint, one full net name per line (brief 100, capability 3).
#   B100_IN_DCP, B100_OUT (the file to write), B100_PATHS (how many worst endpoints, default 20)
# Vivado's own timing analysis picks the nets; RapidWright then routes exactly these (flow/rw/route.py nets).
source [file join [file dirname [info script]] common.tcl]
open_checkpoint $::env(B100_IN_DCP)
set seen [dict create]
foreach p [get_timing_paths -setup -max_paths [env_or B100_PATHS 20] -nworst 1 -unique_pins] {
    foreach n [get_nets -quiet -of_objects $p] {
        if {[get_property TYPE $n] ne "SIGNAL"} { continue }
        if {[llength [get_pins -quiet -of_objects $n -filter {IS_CLOCK}]]} { continue }
        dict set seen [get_property NAME $n] 1
    }
}
set f [open $::env(B100_OUT) w]
foreach n [dict keys $seen] { puts $f $n }
close $f
puts "critnets: [dict size $seen] nets"
