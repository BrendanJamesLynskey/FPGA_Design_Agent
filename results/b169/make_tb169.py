#!/usr/bin/env python3
"""Brief 169: derive tb_lat_core169.sv from brief 126's derived testbench (results/b126/make_tb.py on sim/tb_lat_core.sv).
usage: make_tb169.py <tb_lat_core.sv> <out.sv>      (bypass is always on: every 169 case is a lat_all3_bypass descendant)
Changes (each asserted): the EARLY_MAC and FAST_PRE generics reach the core; with EARLY_MAC the decision's `fire` is seen one clock before the MAC register holds word 7, so
the w7 probe waits for td_wi == 8 and `fire` no longer waits for w7; with FAST_PRE the order's start stamp (`sop`) is in the go clock, before cur_kind loads, so the kind probe is bus_kind;
and a new line "RET <n> <sop ns> <t ns>" records when the order frame comes back round the loopback: the first start block at the receive PCS output after the order's start stamp
(a true transmit-to-receive measurement that does not rely on the +2 convention for the start block on the GT port)."""
import subprocess, sys
src, out = sys.argv[1], sys.argv[2]
here = __file__.rsplit("/", 1)[0]
subprocess.run([sys.executable, here + "/../b126/make_tb.py", src, out, "1"], check=True)
t = open(out).read()
def sub(old, new):
    global t
    assert t.count(old) == 1, old
    t = t.replace(old, new)
sub("parameter bit GO_REG = 1'b1", "parameter bit GO_REG = 1'b1,\n    parameter bit EARLY_MAC = 1'b0,\n    parameter bit FAST_PRE = 1'b0")
sub(".GO_REG(GO_REG), .BUILD_STAMP", ".GO_REG(GO_REG), .EARLY_MAC(EARLY_MAC), .FAST_PRE(FAST_PRE), .BUILD_STAMP")
sub("if (!RATE_MATCH && have_x && !have_w7 && m_v && td_wi == 7 && td_feed)", "if (!RATE_MATCH && have_x && !have_w7 && m_v && td_wi == (EARLY_MAC ? 8 : 7) && td_feed)")
sub("if (!RATE_MATCH && have_w7 && !have_fire && fire)", "if (!RATE_MATCH && (have_w7 || EARLY_MAC) && have_x && !have_fire && fire)")
sub("assign kind0 = (u.g_old.u_tx.cur_kind == 0);", "assign kind0 = (u.g_old.u_tx.bus_kind == 0);")
# the return of the order frame
sub("    int  nbx, nby, nord;", "    int  nbx, nby, nord;\n    real t_ord_sop; logic wait_ret;\n    initial begin t_ord_sop = 0.0; wait_ret = 0; end")
sub("        if (x_v && t > quiet_until) begin", "        if (x_v && wait_ret && t > t_ord_sop && ((x_c == 8'h01 && x_d[7:0] == 8'hFB) || (x_c == 8'h1F && x_d[39:32] == 8'hFB))) begin $display(\"RET %0d %0.3f %0.3f\", nord - 1, t_ord_sop, t); wait_ret = 0; end\n        if (x_v && t > quiet_until) begin")
sub("            nord = nord + 1;\n", "            nord = nord + 1; t_ord_sop = t_sop; wait_ret = 1;\n")
open(out, "w").write(t)
