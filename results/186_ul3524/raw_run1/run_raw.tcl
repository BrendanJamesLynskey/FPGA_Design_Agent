set_param general.maxThreads 1
source ./setup.tcl
catch {upgrade_ip [get_ips *]}
generate_target simulation [get_ips *]
launch_simulation
run all
close_sim
