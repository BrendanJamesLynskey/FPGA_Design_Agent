# Brief 71: the check suite, measured

This folder holds the evidence for brief 71's check suite (`flow/checks`, [docs/check_suite.md](../../docs/check_suite.md)):
the reset check's seeded faults synthesised with Vivado 2026.1, the release's rule catalogue used to verify every AMD rule
id the suite reads, the digest size against the raw reports it replaces on three designs, and a replay of recorded runs
showing that the gate code change moves no gate of a build made before it (those builds have no reset scan, so
the new reset gate is absent in all of them).

## Records

- `seeded/<case>/`: one out-of-context synthesis per seeded design (`flow/checks/seeded/*.sv`, xc7a100tcsg324-1, two
  asynchronous clocks), each with `report_methodology`, `report_drc`, `report_cdc -details`, `report_control_sets
  -verbose`, `report_utilization` and the reset netlist scan `reset_scan.tsv`, all from one Vivado 2026.1 session
  (`flow/checks/seeded/seeded.tcl`). `rst_clean` follows every reset rule; each `rst_f*` breaks one or two:

| Case | Fault seeded | Rules raised (the reset check) | AMD's own rows among them |
|---|---|---|---|
| `rst_clean` | none: xpm_cdc_async_rst and the shell's reset_sync, synchronous resets on the DSP, RAM and counters | none | none |
| `rst_f1_async` | the counter has an asynchronous reset from the synchroniser output | HDL-RST-01 | none (no AMD rule covers it) |
| `rst_f2_polarity` | one reset tested active high in some blocks and active low in another | HDL-RST-02 | none |
| `rst_f3_dsp_async` | the multiplier's input and output registers have an asynchronous reset | HDL-RST-01, HDL-RST-03 | DPIR-1 |
| `rst_f3b_bram_async` | the RAM's output register has an asynchronous reset | HDL-RST-01, HDL-RST-03 | none (RBOR-1 and SYNTH-6 appear, as pipelining advice) |
| `rst_f4_cdc_sync` | clk_a's reset used as clk_b's synchronous reset, no synchroniser | HDL-RST-04 | none in the reset check (report_cdc calls it CDC-1, a data crossing) |
| `rst_f4b_cdc_async` | the same, as an asynchronous reset | HDL-RST-01, HDL-RST-04 | CDC-7 |
| `rst_f5_lut_async` | an OR with a soft reset drives the synchroniser's asynchronous input | HDL-RST-05 | none: LUTAR-1 did not fire on this out-of-context netlist |

  `flow/tests/test_71_check_suite.py` reads these records in CI and requires exactly these rules for each case (every case
  compiled; a case that does not compile writes `synth_failed.txt` and fails the test).
  The seeded records were made again in brief 70 (one Vivado 2026.1 session, `flow/checks/seeded/seeded.tcl`): `rst_clean` no longer
  raises AMD DRC REQP-1840 (the RAM's output register now takes its synchronous reset from one plain register after the synchroniser, in `flow/checks/seeded/rst_common.svh`), and the
  rules above are unchanged.
- `rule_catalogue_2026_1.tsv`: every methodology and DRC rule Vivado 2026.1 knows (`get_methodology_checks`,
  `get_drc_checks`: kind, id, severity, description); the test checks every AMD id the reset check reads is in it.
- `tokens.json`: for T1 (`t1_dimmer_counter`), the brief 65A AXI4-Lite SoC (`b65a_axil_soc`) and the brief 56A GTH link
  (`b56a_gth_serdes`), post-synthesis builds made with Vivado 2026.1: each check's verdict, the bytes of every record the
  checks read, the raw total and the digest at each level in tokens (characters / 4), and the standard digest's text.
- `designs/<design>/synth.json`: the suite's full result for each of the three (the file the digest names).
- `replay.json`: every local recorded run with a build (`runs/*/<design>/build/base`, agent runs of 2026-11-01 to
  2026-11-09 on Vivado 2025.2): the gates re-evaluated with origin/main's `flow/gates.py` and with this branch's, and each
  registry check's verdict against the gate it shares a decision with.

## Measured

Digest size in tokens (characters / 4) against the raw records the checks read, post-synthesis scope:

| Design | Raw records | Raw without the reset scan | Build's gates.json | Digest, summary | standard | detail |
|---|---|---|---|---|---|---|
| T1 | 32543 | 17504 | 3037 | 135 | 173 | 173 |
| b65a AXI4-Lite SoC | 56982 | 14310 | 2983 | 143 | 303 | 303 |
| b56a GTH link | 145645 | 80752 | 615121 | 142 | 1011 | 1374 |

The b56a gates.json (the file brief 56A reported as too large to read) is not read by the suite: the checks read the
reports, and the digest stays small because it caps the findings per check. "Raw without the reset
scan" is the fairer comparison with what an agent read before, since the scan is new.

Verdicts on the three designs (from `tokens.json`): T1 passes every check that ran; b65a fails `standards` (STD-ARCH-00:
the design has no architecture.yaml); b56a fails `standards` (STD-CLK-01 and STD-CLK-03 on the GT user clocks, STD-CDC-01, STD-INIT-01)
and `resets`: our logic outside the GT Wizard (LUT4 and LUT5 cells in `u_core`) drives the Wizard's asynchronous reset
inputs, which AMD's LUTAR-1 and our RST-LUT-01 both report. `lint` did not run on this machine (no Verilator); CI runs it.

Replay (`replay.json`): on every recorded run, origin/main's `flow/gates.py` and this branch's give the same value for
every gate and the same first failed stage (those builds have no reset scan, so the new gate is absent). Where a
registry check and its gate both had their reports, they agree; most pairs could not be compared because those older
builds lack the reports the flow added later (the check says "not run", the gate fails on the missing report).

## Reproduce

Vivado runs take a heavy slot (`_handoff/take_heavy_slot.sh`) and run under `systemd-run --user --scope -p MemoryMax=6G`.

```
# seeded designs and the rule catalogue: one Vivado 2026.1 session (about 6 minutes on the build PC)
vivado -mode batch -source flow/checks/seeded/seeded.tcl -tclargs <out_root>
# the three designs: build to synthesis first, then one Vivado session each for the reports the build did not write
python3 -m flow.checks designs/<d> --scope synth --vivado auto
python3 -m flow.checks.measure designs/t1_dimmer_counter designs/b65a_axil_soc designs/b56a_gth_serdes --scope synth \
    --json results/71_check_suite/tokens.json
# replay (no Vivado): the base gates are origin/main's flow/gates.py
git show origin/main:flow/gates.py > /tmp/gates_main.py
python3 -m flow.checks.replay runs/*/<design> --base-gates /tmp/gates_main.py --json results/71_check_suite/replay.json
```

The builds of the three designs were made by earlier briefs (54B, 65A, 56A) and are not committed; the replayed runs are
local run directories, not committed either.

## Known gaps and limits

- The seeded designs are one small design per fault on one part (Artix-7). The netlist scan ran on UltraScale+ too
  (b56a, xck26), with no seeded faults there.
- LUTAR-1 did not fire on `rst_f5_lut_async` (out of context); our RST-LUT-01 did. It did fire on b56a. Why AMD's rule
  stayed silent on the small case was not investigated.
- Polarity (HDL-RST-02) is seen only on reset pins: a reset that synthesis folds into the D logic, or two polarities in
  different modules joined through ports with renaming, are found only by the source part within one module.
- Brief 71B replaced the source part's text scanner by elaboration (Yosys with slang and ghdl): `ifdef`, macros, includes and
  VHDL are now read by a real front end, and a design it cannot read makes the check PARTIAL. The second review's 23 designs
  (`flow/tests/data/b71_resets/`) and the third review's 212 (`flow/tests/data/b71b_cases/`) are regression cases with their
  expected outcomes; the netlist gate was attacked with real builds (`results/71b_netlist_attack/`).
- A device pin used as a synchronous reset is reported (HDL-RST-04) only when an IBUF is on its path, so out-of-context
  builds, whose ports have none, are not checked for it.
- The token figure is characters / 4, not a model's tokenizer.
- The replayed runs are Vivado 2025.2 builds; they test that the gate code did not change, not anything about 2026.1.
- After the review (2026-11-14) the scan also covers latches (LDCE/LDPE); the committed seeded scans were made just
  before that change and contain no latches, so they are unaffected.
- A synchronous reset made by a LUT from registers on several clocks is not traced for HDL-RST-04.
- The DSP/RAM rule (HDL-RST-03) uses neighbours of the register (D from, or Q to, a DSP or RAM data pin); a register two
  stages away from the primitive is not reported.
