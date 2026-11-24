# Draft issue 4 (not posted): `synth_xilinx -widemux 5` stops with "invalid width range -1" in cells_map.v on a design with a registered square-root pipeline

Status of the upstream check (2026-11-21): the same message is in closed issues #4590 and #4687 (fixed by #4989, April 2025, for muxes whose data inputs are all undefined). It still occurs on
Yosys 0.70+385 (OSS CAD Suite build, git sha1 098e46a36) on the case below. Not checked on current master (the machine has no way to build it), so it may already be fixed: if the
maintainers see it pass on master, close this.

## Reproduction

Files: `isqrt_ooc.sv`, `isqrt_sel.sv`, `isqrt_restoring_iter.sv`, `isqrt_restoring_pipe.sv`, `isqrt_nonrestoring_pipe.sv` (directory `issue_4_repro/`; from this repository's arithmetic library; the repository licence applies, check it before attaching).

```
yosys -p "plugin -i slang; read_slang --top isqrt_ooc -G VARIANT=1 -G W=16 -G PIPE=1 isqrt_*.sv; synth_xilinx -family xcup -top isqrt_ooc -noiopad -noclkbuf -widemux 5"
```

Observed: `.../share/yosys/xilinx/cells_map.v:153: ERROR: Signal `\B' with invalid width range -1!`, after warnings "Range [1:-1] select out of bounds on signal `\B`" from
`\$__XILINX_SHIFTX` (cells_map.v:185).

Same design, other parameters:
* W = 4, 6, 8, 10: no error. W = 16: error. `-family xc7` fails the same way. Without `-widemux`: no error. `VARIANT=0` (the iterative variant) at W = 16: no error.
* `isqrt_sel` as the top (no wrapper that registers the ports): no error. The wrapper only adds one register stage at every port.
* A second design, a 16-bit pipelined divider (`VARIANT=2`, W=16), fails the same way.

Not reduced further: the failing shift is created after the front end (a `$shiftx` whose select width reaches zero after constant trimming), so a smaller source probably needs the
same trimming of a growing-root pipeline.

Cost to the user: with `-widemux` the flow has no way to finish on this design; without it the design synthesises, so the workaround is to leave the option off.
