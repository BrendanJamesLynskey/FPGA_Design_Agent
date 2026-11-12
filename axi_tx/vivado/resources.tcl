# resources.tcl (brief 59A): out-of-context synthesis of the transactor, checkers and counters per configuration, on the
# Nexys A7 part; one "FDA-RES" line each (LUT, FF, BRAM tiles from report_utilization). No implementation, no board.
#   vivado -mode batch -source axi_tx/vivado/resources.tcl -tclargs <repo root> <out dir>
lassign $argv root out
file mkdir $out
set_param general.maxThreads 1
set_param synth.maxThreads 1
set rtl [glob $root/axi_tx/rtl/*.sv]
set la  [glob $root/ip_lib/logic_analyser/rtl/*.sv]
proc util {f} {
    set t [read [open $f]]
    set lut 0; set ff 0; set bram 0
    regexp {\|\s*Slice LUTs\*?\s*\|\s*([0-9]+)} $t -> lut
    regexp {\|\s*Slice Registers\s*\|\s*([0-9]+)} $t -> ff
    regexp {\|\s*Block RAM Tile\s*\|\s*([0-9.]+)} $t -> bram
    return [list $lut $ff $bram]
}
set configs {
    {core_full_s32      axi_tx_core  {LCHK=1 SCHK=1 MON=1 SDATA_W=32}}
    {core_chk_nomon     axi_tx_core  {LCHK=1 SCHK=1 MON=0 SDATA_W=32}}
    {core_bare          axi_tx_core  {LCHK=0 SCHK=0 MON=0 SDATA_W=32}}
    {axil_checker_d32   axil_checker {DATA_W=32}}
    {axil_checker_d64   axil_checker {DATA_W=64}}
    {axis_checker_d32   axis_checker {DATA_W=32}}
    {axis_checker_d64   axis_checker {DATA_W=64}}
    {axis_checker_d128  axis_checker {DATA_W=128}}
    {axil_mon_d32       axil_mon     {DATA_W=32}}
    {axis_mon_d32       axis_mon     {DATA_W=32}}
    {axil_demo_periph   axil_demo_periph {}}
    {axis_demo_fifo     axis_demo_fifo {DATA_W=32}}
}
foreach c $configs {
    lassign $c name top gens
    create_project -in_memory -part xc7a100tcsg324-1
    foreach f [concat $rtl $la] { read_verilog -sv $f }
    set g {}
    foreach x $gens { lappend g -generic $x }
    set t0 [clock seconds]
    if {[catch {synth_design -mode out_of_context -top $top -part xc7a100tcsg324-1 {*}$g} err]} {
        puts "FDA-RES $name FAIL [string map {"\n" " "} $err]"
        close_project
        continue
    }
    report_utilization -file $out/$name.rpt
    lassign [util $out/$name.rpt] lut ff bram
    puts "FDA-RES $name top $top generics {$gens} LUT $lut FF $ff BRAM $bram seconds [expr {[clock seconds]-$t0}]"
    close_project
}
puts "FDA-RES DONE"
