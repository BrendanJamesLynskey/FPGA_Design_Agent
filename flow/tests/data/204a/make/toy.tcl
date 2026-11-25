set_param general.maxThreads 1
set here /home/brendan/Claude_sandbox/_worktrees/204a-report-gates/build/toy
set out $here/out
file mkdir $out
proc stamp {name cmd} {
    if {[catch {uplevel #0 $cmd} err]} { puts "FDA204A-FAIL $name $err" } else { puts "FDA204A-OK $name" }
}
# --- logic levels: a 12-level KEEP chain, timed at 1.6 ns (cannot close even with no net delay) and at 10 ns; and a 5-level one at 4 ns
foreach {tag lv per} {lvl12_tight 12 1.6  lvl12_loose 12 10.0  lvl5_250mhz 5 4.0} {
    set d $out/$tag; file mkdir $d
    create_project -in_memory -part xc7a100tcsg324-1
    read_verilog $here/toy_lvl.v
    synth_design -top toy_lvl -part xc7a100tcsg324-1 -generic LV=$lv -mode out_of_context
    create_clock -name clk -period $per [get_ports clk]
    stamp $tag-ll  "report_design_analysis -logic_level_distribution -logic_level_dist_paths 5000 -file $d/logic_levels.rpt"
    stamp $tag-ts  "report_timing_summary -max_paths 10 -file $d/timing_summary_synth.rpt"
    close_project
}
# --- clocks
set d $out/clk_cascade; file mkdir $d
create_project -in_memory -part xc7a100tcsg324-1
read_verilog $here/toy_clk.v
synth_design -top toy_clk -part xc7a100tcsg324-1 -mode out_of_context -flatten_hierarchy none
create_clock -name clk -period 10 [get_ports clk]
stamp clk-util "report_clock_utilization -file $d/clock_utilization.rpt"
stamp clk-net  "report_clock_networks -file $d/clock_networks.rpt"
stamp clk-ts   "report_timing_summary -max_paths 10 -file $d/timing_summary_synth.rpt"
stamp clk-meth "report_methodology -file $d/methodology_synth.rpt"
close_project
# --- fan-out
set d $out/fanout6000; file mkdir $d
create_project -in_memory -part xc7a100tcsg324-1
read_verilog $here/toy_fo.v
synth_design -top toy_fo -part xc7a100tcsg324-1 -generic FO=6000 -mode out_of_context
create_clock -name clk -period 4 [get_ports clk]
stamp fo "report_high_fanout_nets -timing -load_types -max_nets 25 -file $d/high_fanout_synth.rpt"
stamp fo-ts "report_timing_summary -max_paths 3 -file $d/timing_summary_synth.rpt"
close_project
# --- control sets: 500 (about 9.6 percent of an xc7a35t) and 900 (about 17.3 percent)
foreach {tag n} {cs500 500 cs900 900 cs100 100} {
    set d $out/$tag; file mkdir $d
    create_project -in_memory -part xc7a35tcpg236-1
    read_verilog $here/toy_cs.v
    synth_design -top toy_cs -part xc7a35tcpg236-1 -generic N=$n -mode out_of_context
    create_clock -name clk -period 10 [get_ports clk]
    stamp $tag-cs "report_control_sets -verbose -file $d/control_sets.rpt"
    stamp $tag-ut "report_utilization -file $d/utilization_synth.rpt"
    close_project
}
# --- IP status: the current IP, then an older version of the same IP
set d $out/ip; file mkdir $d
create_project -in_memory -part xc7a100tcsg324-1
foreach nm {blk_mem_gen c_counter_binary} { puts "FDA204A-IPDEFS $nm [get_ipdefs -all -filter "NAME =~ *$nm"]" }
create_ip -name c_counter_binary -vendor xilinx.com -library ip -module_name cnt_cur -dir $d/ip
stamp ip-cur "report_ip_status -file $d/ip_status_current.rpt"
set defs [get_ipdefs -all -filter {NAME =~ *blk_mem_gen}]
puts "FDA204A-DEFS $defs"
if {[llength $defs] > 1} {
    foreach def $defs {
        set ver [lindex [split $def :] end]
        catch {create_ip -name blk_mem_gen -vendor xilinx.com -library ip -version $ver -module_name bmg_$ver -dir $d/ip} e
    }
}
stamp ip-two "report_ip_status -file $d/ip_status_two.rpt"
close_project
puts "FDA204A-DONE"
