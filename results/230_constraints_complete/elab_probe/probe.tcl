# Brief 230 probe: what does Vivado report on an ELABORATED design (synth_design -rtl) and on the synthesised one?
#   vivado -mode batch -source probe.tcl -tclargs <outdir> <top> <part> <mode: rtl|both> <xdc> <sv or - > [ip_tcl or -] [src ...]
# For each of check_timing -verbose, report_clocks, all_inputs/all_outputs, get_ports: did the command run, and what did it list.
set outd [lindex $argv 0]; set top [lindex $argv 1]; set part [lindex $argv 2]; set mode [lindex $argv 3]; set xdc [lindex $argv 4]
set ip_tcl [lindex $argv 5]; set srcs [lrange $argv 6 end]
file mkdir $outd
set part_name $part
set out $outd
set_param general.maxThreads 1
set_param synth.maxThreads 1
foreach f $srcs { read_verilog -sv $f }
if {$xdc ne "-"} { read_xdc $xdc }
if {$ip_tcl ne "-"} { set part $part_name; source $ip_tcl }
proc probe {tag} {
    global outd
    set ::tag $tag
    set ::outd $outd
    set log [open $outd/probe_$tag.txt w]
    foreach {name script} {
        check_timing        {check_timing -verbose -file $::outd/check_timing_$::tag.rpt}
        report_clocks       {report_clocks -file $::outd/report_clocks_$::tag.rpt}
        report_clock_networks {report_clock_networks -file $::outd/clock_networks_$::tag.rpt}
        all_inputs          {llength [all_inputs]}
        all_outputs         {llength [all_outputs]}
        get_ports           {llength [get_ports]}
        get_clocks          {get_clocks -quiet}
        get_pins_CCLK       {get_pins -quiet -hier -filter {REF_PIN_NAME == CCLK}}
        report_timing_summary {report_timing_summary -max_paths 1 -file $::outd/timing_summary_$::tag.rpt}
        unclocked_clock_pins {
            set n 0; set un {}
            foreach p [all_registers -clock_pins] { incr n; if {[llength [get_clocks -quiet -of_objects $p]] == 0} { lappend un $p } }
            set f [open $::outd/unclocked_pins_$::tag.txt w]; puts $f "registers' clock pins: $n; with no clock: [llength $un]"; foreach p $un { puts $f $p }; close $f
            list $n [llength $un]
        }
        ports_with_no_timing {
            set f [open $::outd/ports_$::tag.txt w]
            foreach p [get_ports] { puts $f "[get_property DIRECTION $p] $p clocks=[get_clocks -quiet -of_objects $p]" }
            close $f
            llength [get_ports]
        }
    } {
        if {[info exists ::env(PROBE_STEPS)] && [lsearch $::env(PROBE_STEPS) $name] < 0} { continue }
        set t0 [clock milliseconds]
        if {[catch {uplevel #0 $script} res]} { puts $log "$name: ERROR [string range $res 0 160] ([expr {[clock milliseconds]-$t0}] ms)" } else { puts $log "$name: ok ([string range $res 0 200]) ([expr {[clock milliseconds]-$t0}] ms)" }
    }
    close $log
}
synth_design -rtl -rtl_skip_ip -top $top -part $part
probe rtl
if {$mode eq "both"} {
    synth_design -top $top -part $part
    probe synth
}
puts "PROBE-DONE"
