# mig_impl_check.tcl: implement the MIG example design for one .prj and record which DRCs / placer errors reject it
# (brief 18, section 2, step 2).
#   vivado -mode batch -source flow/mig_impl_check.tcl -tclargs <part> <prj> <out dir> [route]
# Steps: create_ip mig_7series from the .prj (as in 13b), open_example_project, synth_1, opt_design, place_design,
# report_drc (default and bitstream_checks), optionally route_design. Each step is wrapped so that a failure is
# recorded and the later reports still run. Writes <out dir>/result.txt (one STEP/RESULT line per step).
set_param general.maxThreads 1
set_param synth.maxThreads 1
lassign $argv part prj out
set do_route [expr {[llength $argv] > 3 && [lindex $argv 3] eq "route"}]
set out [file normalize $out]; file mkdir $out
set rf [open $out/result.txt w]
proc res {args} { global rf; puts $rf [join $args " "]; flush $rf; puts "MIGCHK: [join $args { }]" }
proc step {name body} {
    set t [clock seconds]
    if {[catch {uplevel 1 $body} err]} { res STEP $name FAIL "[string map [list \n { | }] [string range $err 0 600]]" ; return 0 }
    res STEP $name OK "[expr {[clock seconds]-$t}]s"
    return 1
}
create_project -force mig_chk $out/proj -part $part
set ipdir $out/ip; file mkdir $ipdir
step create_ip {
    create_ip -name mig_7series -vendor xilinx.com -library ip -module_name ddr2_vga -dir $ipdir
    file copy -force $prj $ipdir/ddr2_vga/mig_a.prj
    set_property -dict [list CONFIG.XML_INPUT_FILE mig_a.prj CONFIG.RESET_BOARD_INTERFACE Custom \
        CONFIG.MIG_DONT_TOUCH_PARAM Custom CONFIG.BOARD_MIG_PARAM Custom] [get_ips ddr2_vga]
    generate_target {instantiation_template synthesis} [get_ips ddr2_vga]
}
set ok [step example_project {
    open_example_project -force -in_process -dir $out/ex [get_ips ddr2_vga]
}]
if {!$ok} { res RESULT no-example-project; close $rf; exit 0 }
res INFO project [current_project] xdc [get_files -quiet -filter {FILE_TYPE == XDC}]
set nloc [llength [get_ports -quiet *]]
step synth {
    set_property STEPS.SYNTH_DESIGN.ARGS.FLATTEN_HIERARCHY rebuilt [get_runs synth_1]
    launch_runs synth_1 -jobs 1
    wait_on_run synth_1
    if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} { error "synth_1 [get_property STATUS [get_runs synth_1]]" }
}
set placed 0
if {[step open_synth { open_run synth_1 -name synth_1 }]} {
    res INFO ports [llength [get_ports]] unplaced [llength [get_ports -filter {!IS_LOC_FIXED}]]
    step drc_synth { report_drc -file $out/drc_synth.rpt }
    step opt { opt_design }
    step place { place_design }
    set placed [expr {[llength [get_cells -quiet -filter {IS_PLACED}]] > 0}]
    step drc_place { report_drc -file $out/drc_place.rpt }
    step drc_bitstream { report_drc -ruledeck bitstream_checks -file $out/drc_bitstream.rpt }
    if {$do_route} {
        step route { route_design }
        step drc_route { report_drc -file $out/drc_route.rpt }
        step drc_bitstream_route { report_drc -ruledeck bitstream_checks -file $out/drc_bitstream_route.rpt }
    }
}
res RESULT done placed $placed
close $rf
