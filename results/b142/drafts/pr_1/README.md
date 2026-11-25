# Draft change 1: map UltraScale and UltraScale+ adders to CARRY8 (not for posting as a pull request: see the report)

Files: `carry8.patch` (the diff against YosysHQ/yosys master 11d972c, 2026-11-20: `techlibs/xilinx/arith_map.v`, `techlibs/xilinx/synth_xilinx.cc`),
`arith_map_carry8.v` (the patched techmap file on its own), `add_sub_xcup.ys` (the regression test to add as
`tests/arch/xilinx/add_sub_xcup.ys`), `tests/carry8_equiv.sh` and `tests/carry8_equiv.log` (equivalence runs).

What it does: `synth_xilinx -family xcu|xcup` passes `-D HAS_CARRY8` to the `techmap` that loads `arith_map.v`; with it `$alu` and `$lcu` map to
`CARRY8` (eight bits per cell, `CI` chained from the previous `CO[7]`) instead of `CARRY4`. Other families are unchanged.

How it was tested (and what was not):
* Not tested: a rebuilt Yosys. No `cmake` is installed on this machine and the checkout needs the `abc` submodule built, so `synth_xilinx.cc` (a four-line change)
  was not compiled. The machine's installed Yosys (0.70+385) was driven through exactly the commands the changed `synth_xilinx` would run: `synth_xilinx -run begin:fine`,
  then `opt -full; xilinx_srl -variable -minlen 3; techmap -map +/techmap.v -D LUT_SIZE=6 -D HAS_CARRY8 -map <patched arith_map.v>; opt -fast`, then `synth_xilinx -run map_cells:`.
  The `techlibs/xilinx` data files of that install are byte-identical to master's for `arith_map.v`, `cells_sim.v`, `cells_map.v`, `xcu_dsp_map.v`, `brams_xcu_map.v`, `urams_map.v`, `lut_map.v`, `mux_map.v`, `ff_map.v`.
* `add_sub_xcup.ys` was not run either (it needs the rebuilt binary); the same design under the emulation gives 2 CARRY8 and 8 LUT2.
* Equivalence: `equiv_opt -assert -map +/xilinx/cells_sim.v` (which carries the CARRY8 model) proves the mapped design equal to the RTL for add, subtract with carry, `<`, `==`
  at widths 3, 8, 9, 17, 32, 33 and for six registered designs (`tests/carry8_equiv.log`).
* Vivado accepting the netlist, and the effect on timing and area: see `results/b142/README.md` (Vivado 2026.1 place and route of the EDIF, CARRY4 against CARRY8 against Vivado's own synthesis).
* Known gap in the draft: `CARRY8` has no `abc9_box` / `specify` timing in `cells_sim.v` (the CARRY4 timing is from public 7-series data; no public UltraScale+ figures were found), so `abc9`
  does not see carry delay through the new cells. A reviewer would have to decide whether to add boxes with estimated delays.
