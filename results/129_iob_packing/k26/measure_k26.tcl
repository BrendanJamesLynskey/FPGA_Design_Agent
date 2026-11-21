# measure_k26.tcl (brief 129): place and route iob_probe_k26 on the K26, dump what flow/iob_check.py reads.
#   vivado -mode batch -log <out>/vivado.log -source measure_k26.tcl -tclargs <repo root> <out dir>
set_param general.maxThreads 2
set_param synth.maxThreads 2
lassign $argv root out
file mkdir $out
create_project -in_memory -part xck26-sfvc784-2LV-c
set here $root/results/129_iob_packing/k26
read_verilog -sv $here/iob_probe_k26.sv
read_xdc $here/iob_probe_k26.xdc
synth_design -top iob_probe_k26 -part xck26-sfvc784-2LV-c
opt_design
place_design
route_design
source $root/flow/io_paths.tcl
source $root/flow/iob_paths.tcl
io_dump_paths $out/io_paths_route.txt
iob_dump $out/iob_route.txt
report_drc -file $out/drc.rpt
report_timing_summary -max_paths 3 -file $out/timing_summary.rpt
puts "MEASURE-DONE k26"
