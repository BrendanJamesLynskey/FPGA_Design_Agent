set_param general.maxThreads 1
source ./setup.tcl
catch {upgrade_ip [get_ips *]}
foreach b [get_files -quiet *.bd] { catch {generate_target simulation $b} }
foreach ip [get_ips] { if {![string match *bd/* [get_property IP_FILE $ip]]} { generate_target simulation $ip } }
launch_simulation
run all
close_sim
