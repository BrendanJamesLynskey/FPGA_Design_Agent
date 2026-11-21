// pcs_mac_uvm_pkg.sv: the UVM package of the b96 PCS and MAC bench (brief 112). Compile order: b96 RTL, pcs_ref_pkg, interfaces, this package, the top.
package pcs_mac_uvm_pkg;
  import uvm_pkg::*;
  `include "uvm_macros.svh"
  `include "env/pcs_mac_items.sv"
  `include "env/pcs_mac_cov.sv"
  `include "env/pcs_mac_agents.sv"
  `include "env/pcs_mac_scoreboard.sv"
  `include "env/pcs_mac_env.sv"
  `include "env/pcs_mac_seqs.sv"
  `include "tests/pcs_mac_tests.sv"
endpackage
