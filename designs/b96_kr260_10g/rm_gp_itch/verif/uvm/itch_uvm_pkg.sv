// itch_uvm_pkg.sv: the UVM package of the ITCH/OUCH bench (brief 170). Compile order: the design's RTL, itch_ref_pkg, the interfaces, this package, the SVA module, the top.
package itch_uvm_pkg;
  import uvm_pkg::*;
  import itch_pkg::*;
  `include "uvm_macros.svh"
  `include "env/itch_items.sv"
  `include "env/itch_gen.sv"
  `include "env/itch_cov.sv"
  `include "env/itch_agents.sv"
  `include "env/itch_scoreboard.sv"
  `include "env/itch_env.sv"
  `include "env/itch_seqs.sv"
  `include "tests/itch_tests.sv"
endpackage
