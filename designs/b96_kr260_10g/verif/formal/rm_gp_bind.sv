`ifndef FV_KB
`define FV_KB 0
`endif
// rm_gp_bind.sv (brief 115): attaches rm_gp_props to every rate_match_gp instance; the port names of rm_gp_props are the names of rate_match_gp's own signals.
bind rate_match_gp rm_gp_props #(.AW(AW), .ENT_SYNC(ENT_SYNC), .KB(`FV_KB)) u_props (.*);
