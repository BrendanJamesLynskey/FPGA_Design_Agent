set_param general.maxThreads 1
file mkdir {/home/brendan/Claude_sandbox/_worktrees/216-closure-recipes/results/216_closure_recipes/live/adder_csel_a7_w64b16/work/p0}
set t0 [clock seconds]
open_checkpoint {/home/brendan/Claude_sandbox/_worktrees/216-closure-recipes/build/216/synth/adder_csel_a7_w64b16/default/post_synth.dcp}
opt_design
place_design -directive ExtraNetDelay_high
phys_opt_design -directive AggressiveExplore
route_design -directive NoTimingRelaxation
report_utilization -file {/home/brendan/Claude_sandbox/_worktrees/216-closure-recipes/results/216_closure_recipes/live/adder_csel_a7_w64b16/work/p0/utilization.rpt}
report_timing_summary -max_paths 5 -file {/home/brendan/Claude_sandbox/_worktrees/216-closure-recipes/results/216_closure_recipes/live/adder_csel_a7_w64b16/work/p0/timing_summary.rpt}
report_timing -max_paths 1 -path_type full -file {/home/brendan/Claude_sandbox/_worktrees/216-closure-recipes/results/216_closure_recipes/live/adder_csel_a7_w64b16/work/p0/worst_path.rpt}
write_checkpoint -force {/home/brendan/Claude_sandbox/_worktrees/216-closure-recipes/results/216_closure_recipes/live/adder_csel_a7_w64b16/work/p0/result.dcp}
set f [open {/home/brendan/Claude_sandbox/_worktrees/216-closure-recipes/results/216_closure_recipes/live/adder_csel_a7_w64b16/work/p0/done.txt} w]; puts $f [expr {[clock seconds] - $t0}]; close $f
