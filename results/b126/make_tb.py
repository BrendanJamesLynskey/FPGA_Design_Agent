#!/usr/bin/env python3
"""Brief 126: derive tb_lat_core126.sv from sim/tb_lat_core.sv (96E), so no 200-line copy is kept in the tree.
usage: make_tb.py <tb_lat_core.sv> <out.sv> <bypass 0|1>
Changes (each asserted): the GO_REG generic reaches the core; with bypass the controllers' generics BP_TX_TO, BP_RX_TO, BP_RETRIES come from `BPTO and `BPRTY;
the host tasks drive on the falling edge (see below); the run no longer finishes at the last order: it waits, takes a snapshot and prints every safety counter ("SAFETY <name> <value>"), then "END"."""
import re, sys
src, out, bp = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
t = open(src).read().replace("always_ff @(", "always @(")
def sub(old, new):
    global t
    assert t.count(old) == 1, old
    t = t.replace(old, new)
sub("module tb_lat_core #(", "module tb_lat_core126 #(")
sub("parameter int NORD = 8", "parameter int NORD = 8,\n    parameter bit GO_REG = 1'b1")
sub("b96_core #(.BUILD_STAMP(32'h96),", "b96_core #(" + (".BP_TX_TO(`BPTO), .BP_RX_TO(`BPTO), .BP_RETRIES(`BPRTY), " if bp else "") + ".GO_REG(GO_REG), .BUILD_STAMP(32'h96),")
sub('if (nord == NORD) begin $display("DONE orders %0d", nord); $finish; end', 'if (nord == NORD) $display("DONE orders %0d", nord);')
# The original host tasks drive h_we and h_re with blocking assignments at the clock edge, which races with the core's sampling (a write that follows a read or a #3000 wait was lost: the snapshot command never
# took effect and every counter read 0). Drive on the falling edge instead; the same number of clocks per access.
sub("h_addr = a; h_wdata = d; h_we = 1'b1; @(posedge clk); h_we = 1'b0; @(posedge clk);", "@(negedge clk); h_addr = a; h_wdata = d; h_we = 1'b1; @(negedge clk); h_we = 1'b0; @(negedge clk);")
sub("h_addr = a; h_re = 1'b1; @(posedge clk); h_re = 1'b0; @(posedge clk); @(posedge clk); #1; d = h_rdata;", "@(negedge clk); h_addr = a; h_re = 1'b1; @(negedge clk); h_re = 1'b0; @(negedge clk); @(negedge clk); d = h_rdata;")
reads = ""
for name, base, i in [("poisoned", 0x200, 4), ("dropped", 0x200, 5), ("underrun", 0x200, 6), ("late", 0x200, 7), ("stale", 0x200, 8), ("n_order", 0x200, 0),
                      ("bad", 0x100, 9), ("err", 0x100, 10), ("fired", 0x100, 11), ("blocked", 0x100, 12), ("toolong", 0x100, 13), ("order_ok", 0x100, 16), ("order_bad", 0x100, 17)]:
    reads += f'        hr(12\'h{base + 4 * i:03X}, st); $display("SAFETY {name} %0d", st);\n'
reads += '        hr(12\'h020, st); $display("GT_BUF %h", st);\n'
sub('$display("TIMEOUT orders %0d", nord);\n        $finish;', 'if (nord != NORD) $display("TIMEOUT orders %0d", nord);\n' + reads + '        $display("END");\n        $finish;')
if bp:   # the status read at link-up, as results/b96f1b/core_sim.sh does
    sub('$display("LINK UP at %0t", $time);', '$display("LINK UP at %0t", $time);\n        hr(12\'h008, st); $display("UP FEATURES %h", st);\n        hr(12\'h020, st); $display("UP GT_BUF %h", st);')
    sub('$display("LINK DID NOT COME UP: GTSTAT %h", st); $finish;', 'begin $display("LINK DID NOT COME UP: GTSTAT %h", st); hr(12\'h020, st); $display("NOLINK GT_BUF %h", st); $finish; end')
open(out, "w").write(t)
