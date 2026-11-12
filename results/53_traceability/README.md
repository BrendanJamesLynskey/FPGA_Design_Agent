# 53: traceability matrices, the HDL coding standard and the known-bad runs

Brief 53 (2026-11-11/12). Method: [docs/traceability.md](../../docs/traceability.md),
[docs/hdl_coding_standard.md](../../docs/hdl_coding_standard.md). Every number below is in `summary.json` or the file it
names. This is DO-254-style evidence, not a claim of compliance with any standard.

## The three designs

| Design | Source | Requirements (methods) | Methods passing | Pending | Tests and properties (cite a requirement / structural / untagged) | Coverage holes (justified) | Matrix gates | FDA-HDL v1.0 |
|---|---|---|---|---|---|---|---|---|
| T1 dimmer counter | hand-written reference, tags added by hand | 11 (14) | 14 | 0 | 57 (56 / 1 / 0) | 113 (113) | all pass | pass (1 rule waived: XDCH-2) |
| c11 NCO mixer | agent dev-set run 20261109-083226-ecc1, tags migrated from its testplan | 12 (20) | 14 | 6 hardware | 14 (13 / 1 / 0) | 0 | all pass | fail: HDL-METH-01 (DPIP-1, DPOP-2), HDL-DRC-01 (CFGBVS-1) |
| c12 PWM audio | agent dev-set run 20261109-141014-43e3, tags migrated from its testplan | 10 (18) | 15 | 3 hardware | 19 (18 / 1 / 0) | 75 (0) | `coverage_holes_justified` fails | fail: HDL-XDC-01 (XDCH-2), HDL-METH-01 (DPOP-1, DPOP-2) |

Files per design: `<design>_trace.json` (the matrix, schema `fpga-design-agent/trace/v1`), `<design>_trace.md` (the
table), `<design>_trace.txt` (the gate output), `<design>_lint.json` and `_lint.txt` (FDA-HDL v1.0).

Evidence each matrix read (all made in this brief):

- **Simulation:** Verilator 5.048 with the bound checkers and coverage, seeds 1-3; Icarus 12 as the cross-check
  (`--also`). T1 through `designs/t1_dimmer_counter/tests/test_t1_verif_rtl.py`; c11 and c12 through their own
  `tests/test_*_rtl.py`. All seeds pass on both simulators for all three.
- **Formal:** T1's two SymbiYosys jobs (`debounce`, `scan`), `bmc` and `cover` all PASS. c11 and c12 re-planned their
  formal methods to simulation in the agent run (SymbiYosys was not installed there); the matrix shows those rows as
  `replan formal->simulation`, judged by the replacement test, as `flow/verif_gates.py` does.
- **Analysis:** a fresh Vivado 2026.1 base build of each (`flow/run_vivado.sh`, one heavy slot): T1 passes every gate;
  c12 passes every gate; c11 passes the gates its requirements name (`post_route:setup`,
  `post_synth:post_synth_resources_in_range`) but fails the I/O-constraint gates (`post_synth_io_constraints_clean`,
  `io_timing_clean`) added by brief 20 part B after its run. No requirement of c11 names those gates, so the matrix does
  not show the failure: a gap in that agent's requirements, not in the build record.
- **Hardware:** T1 only, from the committed F0B bring-up (`results/f0b/t1_dimmer_counter_bringup.json`). That bitstream
  predates this brief; the RTL has changed since only by comment lines, which this record cannot prove on its own (the
  build ID of brief 54 closes this). c11 and c12 were not run on the board: their hardware rows are `pending`
  (`--defer hardware`).

What the matrices say:

- **T1:** complete. All 113 holes (111 toggle points and two cover properties) are justified in
  `designs/t1_dimmer_counter/verif/justifications.yaml`, in four classes: read bits constant by the register map, the
  blank digits 4 and 5, the prescaler's constant top bit, and one open gap (bits 7:4 of the 8-bit press counters: no
  seed presses a button 16 times), justified by similarity and labelled as an open gap.
- **c11:** complete apart from the board. Its hidden tests passed in that run (4 of 4, `results/course/c11_nco_mixer/run_2.json`).
- **c12:** every requirement has passing evidence, yet 75 toggle holes in the top module have no justification: all 16
  `LED` bits, the read-data and address bits of the register window at the top, and both directions of `AUD_PWM` and
  `AUD_SD` 1->0. The agent's run passed V3 (its toggle floor is 75 %; measured 84.18 %), so only the new gate shows
  them. Its hidden tests failed in that run (1 of 2, a spec-interpretation escape, `results/course/c12_nexys_pwm_audio/run_2.json`):
  a complete matrix does not show that the spec was read wrongly, because the tests and the RTL share the reading.
- **Design-element column:** T1's modules carry `// req:` tags; the agent designs do not, so their column shows only the
  modules their tagged checkers are bound into.

## Migrating the agent designs

`flow/trace_tag.py --write` inserted 13 tags in c11 and 18 in c12 from their testplans (`# req: ... (from testplan)`).
Each design's coverage-export test was then marked `structural` by hand (the testplan does not map it). The simulations
were re-run after tagging (above) to show the tags change nothing.

The clarify check (`agent/graph/spec_schema.py requirement_quality_errors`) on recorded agent specs: c11 2 of 12
requirements compound, c12 3 of 10, the c14 run-4 fixture 5 of 12, the T1 run `dd0e` fixture 2 of 13 (12 of 47). Today's
clarify gate would have sent each back to be split. T1's own three compound requirements were split (REQ-01, -02, -08
kept their ids; REQ-09, -10, -11 added).

## Known-bad runs (T1, real simulations)

Each in its own worktree of this branch; the change is in `known_bad/kb<N>.diff`, the gate output in
`known_bad/kb<N>_trace.txt`, the matrix in `known_bad/kb<N>_trace.json`.

| Run | Change | Simulation | Gate that fails | Message (start) |
|---|---|---|---|---|
| kb1 | deleted `t1_cocotb.pwm_on_time_matches_duty`, REQ-03's only simulation evidence | Icarus, seeds 1-3, all remaining tests pass | `requirements_verified` only | `REQ-03:simulation=fail (REQ-03:simulation: t1_cocotb.pwm_on_time_matches_duty named in the testplan proof list but not a test in the bench)` |
| kb2 | added `t1_verif.extra_identity_smoke` with no tag | Icarus, seeds 1-3, all pass | `artefacts_cite_requirements` only | `untagged: test t1_verif.extra_identity_smoke (designs/t1_dimmer_counter/tests/t1_verif.py:175)` |
| kb3 | added an RTL branch no test reaches (a sticky bit set by writing 0xDEADBEEF to offset 0x7F) | Verilator with coverage, seeds 1-3, all pass | `coverage_holes_justified` only | `3 coverage hole(s) neither closed nor justified: branch dimmer_counter.sv:54 if, toggle dimmer_counter.sv:51 sticky:0->1, toggle dimmer_counter.sv:51 sticky:1->0` |

In each case every simulation still passes: only the matrix gate catches the change. kb1 and kb2 defer coverage
(Icarus records none); all three defer analysis (no build of the modified tree).

## Reproduce

```bash
SIM=verilator T1_SEEDS=1,2,3 pytest designs/t1_dimmer_counter/tests/test_t1_verif_rtl.py    # Verilator 5.036+ (heavy slot)
SIM=icarus    T1_SEEDS=1,2,3 pytest designs/t1_dimmer_counter/tests/test_t1_verif_rtl.py
flow/formal.sh designs/t1_dimmer_counter
flow/run_vivado.sh designs/t1_dimmer_counter base                                              # Vivado 2026.1
python3 flow/standards_check.py designs/t1_dimmer_counter --json build/t1_standards.json
python3 flow/traceability.py designs/t1_dimmer_counter --runs build/verif/verilator --also build/verif/icarus \
    --formal build/verif/formal --gates designs/t1_dimmer_counter/build/base/gates.json \
    --hw results/f0b/t1_dimmer_counter_bringup.json --json t1.json --md t1.md
python3 flow/lint_ruleset.py designs/t1_dimmer_counter --gates designs/t1_dimmer_counter/build/base/gates.json \
    --standards build/t1_standards.json
```

c11 and c12 were copies of the agent's run directories (`runs/` is not in the repository) with `build.yaml` pointed at
the copy; their matrices name the copies' paths (`build/b53/...`).

The matrices are baselines: a later `flow/traceability.py ... --baseline results/53_traceability/t1_dimmer_counter_trace.json`
lists what changed since, and fails `changed_requirements_reverified` for a requirement whose text changed while its
evidence did not.
