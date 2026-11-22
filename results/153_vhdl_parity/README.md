# VHDL parity of the gates (brief 153, review item F9)

**Result.** Before the change, 12 of the 17 readers of a design's RTL that were probed returned a pass, an empty list or no finding
on a VHDL design and said nothing (and 2 more ran the VHDL as if it were SystemVerilog and failed with the wrong error). After it, 0
are silent: 12 read the VHDL and 5 say "no reader for .vhd" in their own result. A wrong design ID planted in a VHDL design (the brief
55 translation of `t1_gray_stepper`, one character changed) is caught by the derived-constants check (`CONST-ID-01`); before, the same
check passed it.

## Nulls first

- **Null A (the count is not 0): not met.** 0 silent readers after.
- **Null B (the planted constant is not caught): not met.** `CONST-ID-01` is raised on the planted VHDL design, and not on the clean
  one; the five brief 55 translations bind the same design IDs as their SystemVerilog references (below).
- **Null C (a port changes a SystemVerilog result): not met.** All 16 SystemVerilog controls still catch their plants; the 17th
  (R07) has nothing to catch by construction. The 17 pre-existing failures in `flow/tests` are the same tests that fail without the change.
- What this does **not** show: that a VHDL design is as well checked as a SystemVerilog one. Five readers read nothing of VHDL and the
  CDC injection run fails closed on a VHDL crossing; there is no VHDL code coverage; mixed-language simulation is a GHDL netlist
  (a synthesis view). The count is of readers that were probed; `inventory.md` lists the sites that were not and why.

## What was measured

One design, `t1_gray_stepper`, in two languages: its SystemVerilog reference and the brief 55 VHDL translation (arm B). Each of 17
readers is given the defect it is meant to find, planted in both languages, and one verdict per run: `caught`, `no_reader`
(says it did not read the VHDL), `silent`, `wrong`. The set was written before the change ([prereg.md](prereg.md)); the probe is
[tools/vhdl_parity_probe.py](../../tools/vhdl_parity_probe.py); the readers and where they are are in [inventory.md](inventory.md).

| Id | Reader | Planted defect | SV before | VHDL before | SV after | VHDL after |
|---|---|---|---|---|---|---|
| R01 | flow.checks lint (lint_ruleset.verilator_findings) | latch | caught | wrong | caught | caught |
| R02 | flow.checks standards (flow/standards_check.py) | async_reset | caught | caught | caught | caught |
| R03 | flow.checks resets, source part (flow/checks/resets.py) | async_reset | caught | caught | caught | caught |
| R04 | flow.checks xpm_sim (constraint_gates.xpm_sim_findings) | xpm_no_sim_assert | caught | silent | caught | caught |
| R05 | flow.checks constants (flow/derived_constants.py) | wrong_id | caught | silent | caught | caught |
| R06 | flow.checks axi (flow/amd_ip_notes.py), control | none (reader-specific input) | caught | caught | caught | caught |
| R07 | flow.checks axi_profile (flow/checks/axi_profile.py) | none (reader-specific input) | control | silent | control | no_reader |
| R08 | flow.checks fsm (flow/fsm_coverage.py parse_enum) | none (reader-specific input) | caught | wrong | caught | no_reader |
| R09 | flow.cdc_inject.design_crosses (V3 CDC checks) | crossing | caught | silent | caught | caught |
| R10 | flow.cdc_inject_run.evaluate (CDC injection run) | crossing | caught | silent | caught | no_reader |
| R11 | agent.graph.spectest (spec-test role RTL list) | none (reader-specific input) | caught | silent | caught | caught |
| R12 | agent.graph.spectest.rtl_hash (stale-evidence key) | edit | caught | silent | caught | caught |
| R13 | flow.trace_v1.legacy_items (RTL files per item) | none (reader-specific input) | caught | silent | caught | caught |
| R14 | flow.hw_dry_check (constant-0 BUILD_STAMP) | stamp_zero | caught | silent | caught | caught |
| R15 | flow.managed_rtl_import.build_files (managed project) | none (reader-specific input) | caught | silent | caught | no_reader |
| R16 | flow.review.prepare.infer_top (review of a user's RTL) | none (reader-specific input) | caught | silent | caught | caught |
| R17 | flow.inspect_views schematic sources | none (reader-specific input) | caught | silent | caught | no_reader |
Totals on the VHDL design, before: caught 3, no_reader 0, **silent 12**, wrong 2. After: caught 12, no_reader 5, **silent 0**, wrong 0
([before_final_probe.json](before_final_probe.json), [after.json](after.json)). `before.json` is the first run of the probe;
`before_final_probe.json` is the final probe run against the unchanged code (a scratch checkout of the pre-change commit): identical
outcomes. R02, R03 and R06 were already right (a control each).

Reading the rows:

- **R01 lint:** before, the registered lint passed the VHDL to Verilator, which read it as Verilog (`syntax error, unexpected ';'`).
  Now a VHDL top is linted by GHDL as the agent's lint tool does. The same change found that a Verilator run that itself fails (a
  broken install) was reported as a clean lint; it is now NOT RUN with Verilator's message.
- **R05 constants:** before, the table said "a design ID is quoted in the spec but no fpga_shell instance binds DESIGN_ID: not
  checked" and the check was a pass; now it reads the `generic map`.
- **R10 CDC injection run:** a VHDL design with a crossing used to be "not applicable, pass"; now the crossing is detected (R09) and
  the run fails closed because there is no injector for VHDL. This is a deliberate blocking result.

## Every registered check on the five brief 55 translations

[checks_before.json](checks_before.json) and [checks_after.json](checks_after.json): every source-reading check of `flow.checks`
(scope `rtl`, no Vivado) on the five translations (`t1_gray_stepper`, `t1_elevator_fsm`, `d24_registered_outputs`,
`t1_sync_fifo_regs`, `t1_debounce_bank`) and on their references. The checks that only digest Vivado reports are not in it (they read no
source). Two changes show:

- `lint`: before, `fail` on all five translations (Verilator reading VHDL); after, `pass` on all five (GHDL).
- `constants`: `pass` before and after, but the record of what it read differs. Before, no design-ID binding was read in any of the five
  VHDL designs; after, each binds the same value as its reference: `0x47524159`, `0x454c4556`, `0x52474f55`, `0x4649464f`,
  `0x44424e4b` ("GRAY", "ELEV", "RGOU", "FIFO", "DBNK").

## What changed

- [flow/sources.py](../../flow/sources.py): the one source-discovery helper (languages, the build's source list, the design's `rtl/`),
  `no_reader` (the fail-closed text), the VHDL literal reader, and `python -m flow.sources` (the table and the traps in its `--help`).
- Ported to read VHDL: `xpm_sim`, `constants`, `lint`, `cdc_inject.design_crosses`, the spec-test entry (through the GHDL netlist) and its
  evidence key, trace v1 and the trace matrix elements and waivers, the build-stamp check, review's top, and, outside the labelled set,
  the stage-2 plan's "has RTL" test and the closure snapshot (both looked only at `rtl/*.sv`: every stage-2 visit on a VHDL design
  rewrote its RTL instead of repairing it).
- Say "no reader": `axi_profile`, `fsm` (fsm_coverage), the managed RTL import, inspect schematics, and the CDC injection run (fails closed).
- Tests: [flow/tests/test_153_vhdl_parity.py](../../flow/tests/test_153_vhdl_parity.py) (70 tests; each port on a VHDL fixture, the
  SystemVerilog behaviour beside it, and the whole labelled set).

## Not done

- A VHDL injector for the CDC run, a VHDL FSM-coverage reader (GHDL's VCD form of an enumeration is unmeasured), a VHDL front end for
  the schematics, a VHDL register-map generator, VHDL in the managed import: each is stated in `python -m flow.sources --help`.
- NVC, GHDL code coverage and library blocks in VHDL (briefs F10 and F11).
- Sites in `inventory.md` under "not changed".

## Reproduce

```
python3 tools/vhdl_parity_probe.py run --out results/153_vhdl_parity/after.json
python3 tools/vhdl_parity_probe.py checks --out results/153_vhdl_parity/checks_after.json
python -m pytest -q flow/tests/test_153_vhdl_parity.py
```

Needs GHDL 4.1.0, Yosys with the ghdl and slang plugins (OSS CAD Suite), Verilator and Icarus. Light: no Vivado, no model call, no
simulation beyond the netlist elaboration.
