// v_macros_paired.svh: the Yosys (-DFORMAL) V_SAME / V_NEXT / V_RST of ../checkers/v_macros.svh, each also declaring the cover
// NAME__ante in the same guard (brief 143c, flow/formal_rigour.py): if that cover is unreachable the assertion never has
// anything to check. Read after v_macros.svh in the same read_verilog command; the flow-owned v_macros.svh stays unchanged
// (the tests role sees it, and flow/tests/test_05i_checker_macros.py keeps the design's copy equal to flow/v_macros.svh).
`ifdef FORMAL
  `undef V_SAME
  `undef V_NEXT
  `undef V_RST
  `define V_SAME(name, ante, cons) always @(posedge clk) if (past_ok && seen_rst && !rst && !$past(rst) && (ante)) begin name: assert (cons); name``__ante: cover (1'b1); end
  `define V_NEXT(name, ante, cons) always @(posedge clk) if (past_ok && seen_rst && !rst && !$past(rst) && $past(ante)) begin name: assert (cons); name``__ante: cover (1'b1); end
  `define V_RST(name, cons)        always @(posedge clk) if (past_ok && $past(rst)) begin name: assert (cons); name``__ante: cover (1'b1); end
`endif
