# amd_ip_ila.tcl (brief 196, build dbg only): one Integrated Logic Analyzer (ila 6.2), a 16-bit probe, 1024 samples, in flow/build.tcl's in-memory project.
# This is the debug core the production_secure check must find and fail. Same helper as designs/b96_kr260_10g/ip/amd_ip_xvc.tcl (global synthesis, no out-of-context checkpoint).
set_part $part
set fda_ip_dir [file join $out ip]
file mkdir $fda_ip_dir
proc fda_ip {vlnv name cfg} {
    global fda_ip_dir
    create_ip -vlnv $vlnv -module_name $name -dir $fda_ip_dir
    set ip [get_ips $name]
    if {[llength $cfg]} { set_property -dict $cfg $ip }
    set_property GENERATE_SYNTH_CHECKPOINT false [get_files [get_property IP_FILE $ip]]
    generate_target {synthesis instantiation_template} $ip
}
fda_ip xilinx.com:ip:ila:6.2 ila_dbg [list CONFIG.C_NUM_OF_PROBES 1 CONFIG.C_PROBE0_WIDTH 16 CONFIG.C_DATA_DEPTH 1024 CONFIG.C_EN_STRG_QUAL 0 CONFIG.C_INPUT_PIPE_STAGES 0]
