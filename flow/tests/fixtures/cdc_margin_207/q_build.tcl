# q_build.tcl: brief 207, one Quartus Prime Lite compile (analysis & synthesis + fitter) of cdc207_top.
#   quartus_sh -t q_build.tcl <rtl dir> <work dir> <family> <device> <BAD> <sdc file> <seed>
# Every port except the two clocks is a virtual pin (no I/O timing; the crossings are internal). The first stage of each
# synchroniser is marked "Forced If Asynchronous" so report_metastability can give a per-chain MTBF (Quartus help,
# report_metastability: automatically found chains get no MTBF); the rest of the design stays on Auto.
load_package flow
lassign $argv rtl work family device bad sdc seed
file mkdir $work
cd $work
project_new cdc207 -overwrite
set_global_assignment -name FAMILY $family
set_global_assignment -name DEVICE $device
set_global_assignment -name TOP_LEVEL_ENTITY cdc207_top
set_global_assignment -name VERILOG_FILE $rtl/cdc207_top.v
set_parameter -name BAD $bad
set_global_assignment -name SDC_FILE $sdc
set_global_assignment -name SEED $seed
set_global_assignment -name NUM_PARALLEL_PROCESSORS 1
set_global_assignment -name SYNCHRONIZER_IDENTIFICATION AUTO
set_global_assignment -name OPTIMIZE_FOR_METASTABILITY ON
foreach p {rst_a rst_b arst_n lvl_in_a pls_in_a lvl_cnt_b[*] pls_cnt_b[*] din_a[*] wr_a full_a rd_b dout_b[*] empty_b
           hs_data_a[*] hs_go_a hs_busy_a hs_data_b[*] hs_valid_b cfg_in_a[*] cfg_we_a cfg_b[*] rcnt_b[*]
           fa_x[*] fa_y[*] fa_acc[*] fb_x[*] fb_y[*] fb_acc[*]} {
    set_instance_assignment -name VIRTUAL_PIN ON -to $p
}
foreach r {lvl_s1 tg_s1 wq1_b[*] rq1_a[*] rq1_b aq1_a ct1_b rb1_b} {
    set_instance_assignment -name SYNCHRONIZER_IDENTIFICATION "FORCED IF ASYNCHRONOUS" -to $r
}
export_assignments
execute_module -tool map
execute_module -tool fit
project_close
