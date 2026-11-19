# neutralise_block.tcl: make the supplier's checkpoint context-neutral (brief 102, stage 2). The out-of-context run created the block's clock on its own
# port (create_clock -name clk), and a checkpoint read into a cell brings that clock along as a second primary clock (u_blk/clk) in the integrator's
# design: TIMING-4/6/7/27 and CDC-1 between it and the real clock. The integrator owns the clocks, so the supplier drops its own timing constraints
# after implementation (reset_timing); placement and routing stay locked. Environment: FDA_PR_IN, FDA_PR_OUT.
open_checkpoint $::env(FDA_PR_IN)
reset_timing
write_checkpoint -force $::env(FDA_PR_OUT)
