# c13_hough_lines, original reference (closure-loop proof case)

`rtl/` is the course reference RTL of `benchmark/course/tasks/c13_hough_lines/ref/rtl/` as it was on origin/main at
commit 11ea2c4 (before the hand fix of branch `fu-0112-c13-amend`), copied here so the proof case does not depend on when
that amendment merges. SHA-256:

| File | SHA-256 |
|---|---|
| hough.sv | 17cab0b27460f09085d8d9f5601e4375be68efee324f4a895860216c0b7dbe97 |
| c13_hough_lines_regs.sv | 65a4200c295dc171ba9343fd7bae3a3dcecc4ac345eefa2032334592feed6f99 |
| c13_hough_lines_top.sv | 685e6088dae928f8263dc49ce51da3e9cb4f435d5d22ddaa92cfa7e4f203784b |

`reports/` holds the routed reports of its whole-board build on Vivado 2026.1 (`benchmark/tools/ref_build.py`;
WNS -0.166 ns, 2 failing endpoints), with the Date, Host and Command header lines removed, and a subset of that build's
`gates.json`. They are the parser fixtures of `flow/digest/` and the starting goal vector of the proof case.
