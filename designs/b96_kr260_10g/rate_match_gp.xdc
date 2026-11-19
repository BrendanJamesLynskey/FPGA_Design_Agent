# rate_match_gp.xdc (brief 96E): the write-clock entry flops of rate_match_gp.sv are read by the read clock's logic through a multiplexer selected by the read pointer. The read pointer
# only selects an entry after the gray write pointer (xpm_cdc_gray, 2 flops) has admitted it, at least about 2 read clocks after the entry changed, so this path needs a bound, not a timing
# relationship between the two clocks: without one the two user clocks would be timed together through the multiplexer. Datapath-only maximum delay of one read-clock period
# (TXUSRCLK2, 161.1328125 MHz = 6.206 ns), from the entry flops to the read-clock registers of this instance (the output register r_d/r_c, the policy state and counters), as AMD does for the
# xpm_fifo_async memory read path (flow/xpm_cdc.tcl). Used by the rm_gp build only.
set_max_delay -datapath_only -from [get_cells -hierarchical -filter {NAME =~ *g_own.u_rm/ent_reg*}] -to [get_cells -hierarchical -filter {NAME =~ *g_own.u_rm/* && IS_SEQUENTIAL && NAME !~ *g_own.u_rm/ent_reg* && NAME !~ *u_wp/* && NAME !~ *u_rp/*}] 6.206
