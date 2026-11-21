// v_macros.svh: one property source, three readers (brief 04f).
// (Do not start a comment with the simulator's name: Verilator reads `// verilator ...` as a metacomment.)
//   Verilated 5.x and xsim : concurrent assertions in the implicit-clock form (|-> and |=>, $past, no ## sequences).
//   Yosys/SymbiYosys 0.33  : the same property as an immediate assertion in an always block (-DFORMAL); open Yosys
//                            does not read `assert property (@(posedge clk) ...)`.
//   Icarus 12              : no concurrent assertions at all, so the checker compiles to nothing (__ICARUS__).
// Every property is named (A_* assertion, C_* cover) so the testplan can trace to it by name.
// Yosys only (-DFORMAL): every assertion NAME is paired with a cover NAME__ante of its own antecedent in the same guard
// (brief 143c, flow/formal_rigour.py): if the cover is unreachable the assertion never has anything to check.
// The module that includes this file must declare `clk`, `rst`, `seen_rst` (high once reset has been seen:
// nothing is checked before the first reset) and (for FORMAL) `past_ok`.
`ifndef V_MACROS_SVH
`define V_MACROS_SVH
`ifdef __ICARUS__
  `define V_SAME(name, ante, cons)
  `define V_NEXT(name, ante, cons)
  `define V_RST(name, cons)
  `define V_COVER(name, expr)
`elsif FORMAL
  `define V_SAME(name, ante, cons) always @(posedge clk) if (past_ok && seen_rst && !rst && !$past(rst) && (ante)) begin name: assert (cons); name``__ante: cover (1'b1); end
  `define V_NEXT(name, ante, cons) always @(posedge clk) if (past_ok && seen_rst && !rst && !$past(rst) && $past(ante)) begin name: assert (cons); name``__ante: cover (1'b1); end
  `define V_RST(name, cons)        always @(posedge clk) if (past_ok && $past(rst)) begin name: assert (cons); name``__ante: cover (1'b1); end
  `define V_COVER(name, expr)      always @(posedge clk) if (past_ok && !rst) name: cover (expr);
`else
  `define V_SAME(name, ante, cons) name: assert property (@(posedge clk) disable iff (rst || !seen_rst) (!$past(rst) && (ante)) |-> (cons));
  `define V_NEXT(name, ante, cons) name: assert property (@(posedge clk) disable iff (rst || !seen_rst) (!$past(rst) && (ante)) |=> (cons));
  `define V_RST(name, cons)        name: assert property (@(posedge clk) $past(rst) |-> (cons));
  `define V_COVER(name, expr)      name: cover property (@(posedge clk) disable iff (rst || !seen_rst) (expr));
`endif
`endif
