# netlist.tcl (brief 101, part 2b): Vivado post-synthesis functional netlists, one session.
#   vivado -mode batch -source netlist.tcl -tclargs <jobs.tcl>
# <jobs.tcl> sets nl(part) and nl(jobs), a list of {name top wd kind sources}; kind as in ooc.tcl (rtl:<directive>[:retime]).
# Each job: synth_design out of context, then write_verilog -mode funcsim <wd>/synth_funcsim.v (UNISIM instances, no timing).
# No placement or routing: this is the netlist Vivado's own synthesis produced, which flow/eqy_gate.py compares with the RTL.
set_param general.maxThreads 1
set_param synth.maxThreads 1
source [lindex $argv 0]
foreach job $nl(jobs) {
    lassign $job name top wd kind sources
    file mkdir $wd
    if {[catch {
        create_project -in_memory -part $nl(part)
        lassign [split $kind :] k directive retime
        foreach s $sources { if {[string match *.v $s]} { read_verilog $s } else { read_verilog -sv $s } }
        set args [list -top $top -part $nl(part) -mode out_of_context -directive $directive]
        if {$retime eq "retime"} { lappend args -retiming }
        synth_design {*}$args
        write_verilog -mode funcsim -force $wd/synth_funcsim.v
    } err]} {
        set f [open $wd/error.txt w]; puts $f $err; close $f
        puts "netlist: $name failed: $err"
    }
    close_project -quiet
}
