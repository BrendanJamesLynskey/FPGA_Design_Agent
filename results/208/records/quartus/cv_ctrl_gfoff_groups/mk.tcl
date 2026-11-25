project_new cv_ctrl_gfoff_groups -overwrite
set_global_assignment -name FAMILY "Cyclone V"
set_global_assignment -name DEVICE 5CEBA4F23C7
set_global_assignment -name TOP_LEVEL_ENTITY q_clkctrl
set_global_assignment -name VERILOG_FILE /home/brendan/Claude_sandbox/_worktrees/208-clock-mux/results/208/quartus/q_clkctrl.v
set_global_assignment -name SDC_FILE /home/brendan/Claude_sandbox/_worktrees/208-clock-mux/results/208/quartus/groups.sdc
set_global_assignment -name NUM_PARALLEL_PROCESSORS 1
set_parameter -name GF "OFF"
project_close
