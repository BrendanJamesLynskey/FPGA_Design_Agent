# clkwiz_probe.tcl: read the Clocking Wizard's own results in batch (brief 18, section 2b).
#   vivado -mode batch -source flow/clkwiz_probe.tcl -tclargs <part> <out dir> <name>:<fin MHz>:<PLL|MMCM>:<f1,f2,...> ...
# For each target set: create_ip clk_wiz, set CONFIG.*, read back M/D/O, jitter, phase error; generate the output
# products and copy the generated XDC. No GUI, no synthesis. Writes <out dir>/clkwiz_<name>.json lines in clkwiz.jsonl.
set_param general.maxThreads 1
set part [lindex $argv 0]; set out [file normalize [lindex $argv 1]]
file mkdir $out
create_project -in_memory -part $part
set jf [open $out/clkwiz.jsonl w]
foreach spec [lrange $argv 2 end] {
    lassign [split $spec :] name fin prim freqs
    set ipdir $out/ip_$name
    file mkdir $ipdir
    create_ip -name clk_wiz -vendor xilinx.com -library ip -module_name cw_$name -dir $ipdir
    set ip [get_ips cw_$name]
    set cfg [list CONFIG.PRIMITIVE $prim CONFIG.PRIM_IN_FREQ $fin CONFIG.NUM_OUT_CLKS [llength [split $freqs ,]]]
    set i 1
    foreach f [split $freqs ,] {
        lappend cfg CONFIG.CLKOUT${i}_USED true CONFIG.CLKOUT${i}_REQUESTED_OUT_FREQ $f
        incr i
    }
    set err ""
    if {[catch {set_property -dict $cfg $ip} err]} { puts "SET-ERR $name: $err" }
    set d [dict create name $name part $part fin $fin primitive $prim req $freqs seterr [string map [list \" ' \n { }] $err]]
    foreach p [list_property $ip] {
        if {[regexp {^CONFIG\.(MMCM_(CLKFBOUT_MULT_F|DIVCLK_DIVIDE|CLKOUT\d_DIVIDE_F|CLKOUT\d_DIVIDE)|PLL_(CLKFBOUT_MULT|DIVCLK_DIVIDE|CLKOUT\d_DIVIDE)|CLKOUT\d_(JITTER|PHASE_ERROR)|PRIMITIVE|AUTO_PRIMITIVE)$} $p]} {
            dict set d $p [get_property $p $ip]
        }
    }
    set gen_ok [expr {![catch {generate_target all $ip} gerr]}]
    dict set d generate_ok $gen_ok
    if {!$gen_ok} { dict set d generate_err [string map [list \" ' \n { }] $gerr] }
    set xdcs [glob -nocomplain -directory $ipdir -types f -tails */*.xdc */*/*.xdc */*/*/*.xdc]
    dict set d xdc_files $xdcs
    set items {}
    dict for {k v} $d { lappend items "\"$k\": \"[string map {\" '} $v]\"" }
    puts $jf "{[join $items {, }]}"
    flush $jf
}
close $jf
