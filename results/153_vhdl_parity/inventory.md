# Brief 153: the inventory of readers

How the 17 readers of the labelled set were found: the review's section 5.1 table (the rows marked "skips VHDL", "sees no VHDL RTL",
"not seen as staleness", "not supported"), then `grep -rnE '\*\.sv|"\.sv"|\.svh|\.suffix in \(' flow agent hwsw project tools` over the
non-test code (202 hits in 64 files at origin/main e645abec), each hit classified. The table lists the readers; the sites that are not
readers of a design's own RTL are named after it, with the reason.

| Id | Reader | Where (at e645abec) | Before (SystemVerilog glob) | After |
|---|---|---|---|---|
| R01 | check `lint` | `flow/lint_ruleset.py:103`, `flow/checks/__init__.py` `_lint` | Verilator over every file of the build list, VHDL included: syntax errors named as the design's | GHDL lint when the top is VHDL; NOT RUN "no reader" for a SystemVerilog top over VHDL; Verilator failing is NOT RUN, not a pass |
| R02 | check `standards` | `flow/standards_check.py:311,334` | already read the GHDL netlist | unchanged (control) |
| R03 | check `resets`, source part | `flow/checks/__init__.py:299`, `flow/checks/resets.py` | already elaborated with the ghdl plugin | unchanged; `build_sources` fallback (no build.yaml) now includes VHDL |
| R04 | check `xpm_sim` | `flow/checks/__init__.py:436` | `.sv .v .svh .vh` filter: VHDL never read | VHDL reader (`constraint_gates.xpm_sim_findings_vhdl`) |
| R05 | check `constants` | `flow/derived_constants.py:124-126` | `.sv .v .svh .vh` filter; a note in the table only | VHDL reader of the `generic map`; PARTIAL when the quoted ID is not readable |
| R06 | check `axi` | `flow/amd_ip_notes.py:29` | text scan of Tcl/XDC/YAML/HDL | unchanged (control, language-neutral) |
| R07 | check `axi_profile` | `flow/checks/axi_profile.py:57` | generated `.sv` blocks only, nothing said | PARTIAL "no reader for .vhd" when `interfaces:` is declared (the generator emits SystemVerilog only) |
| R08 | check `fsm` | `flow/fsm_coverage.py:48` | `ValueError: no typedef enum` (a wrong reason) | NOT RUN "no reader for .vhd" |
| R09 | `cdc_inject.design_crosses` | `flow/cdc_inject.py:238` | `rtl/*.sv, *.v`: a VHDL crossing is "no crossing" | detects `attribute ASYNC_REG` and `xpm_cdc_*` in VHDL |
| R10 | CDC injection run | `flow/cdc_inject_run.py:58` | "not applicable, pass" | fails closed: "no reader for .vhd", pass False |
| R11 | spec-test role | `agent/graph/spectest.py:213` | `own = rtl/*.sv` (empty for VHDL) | `vhdl.own_sources`: the GHDL netlist of the VHDL |
| R12 | spec-test evidence key `rtl_hash` | `agent/graph/spectest.py:327` | `rtl/*.sv` | every language |
| R13 | trace matrix v1 `legacy_items` | `flow/trace_v1.py:132` | `rtl/*.sv` | every language |
| R14 | `hw_dry_check` constant-0 BUILD_STAMP | `flow/hw_dry_check.py:77` | `rtl/*.sv` | VHDL `BUILD_STAMP => x"0..."` |
| R15 | managed RTL import | `flow/managed_rtl_import.py:113,125` | `.v/.sv` filter; the VHDL file dropped from `build_files` | said so (`ValueError`, `not_run`, interface problem) |
| R16 | review `infer_top` | `flow/review/prepare.py:66` | `.sv/.v` modules only | the unique VHDL entity nobody instantiates; the generated build.yaml lists `*.vhd` |
| R17 | inspect schematics | `flow/inspect_views.py:424` | `.sv/.v` filter; nothing said | `schematic_sources` returns the "no reader" text; the page and the notes show it |

Also ported, outside the labelled set (a test on a VHDL fixture each, no before/after probe because no probe was written before the change):
`traceability.rtl_elements` and `inline_waivers` (`-- req:` and `-- std-waive:` in VHDL, `entity` as the element) and the RTL list of
`traceability` line 445; the stage-2 plan's "has RTL" test (`agent/graph/run.py:749`) and the closure snapshot
(`agent/graph/closure.py`); see the report.

## Sites that are not readers of a design's own RTL (not changed)

- `flow/cocotb_run.py` (the shell's `shell/rtl/*.sv`, a design's `verif/checkers/*.sv`), `flow/verif_gates.py` (checker macros): the
  shell and the bound checkers are SystemVerilog in every design.
- `flow/blockdesign/*`, `flow/net/*`, `flow/ipgen/*`, `hwsw/*` (the register-map and CFU generators), `project/contract_test.py`: they
  generate or read generated SystemVerilog (review section 5.1: "register maps: no VHDL output", "block designs: not supported").
- `agent/graph/latency_loop.py`: refuses anything but `rtl/*.sv` with an explicit message ("only rtl/*.sv may be edited in this loop").
- `agent/graph/document.py:260,400`: the 7-segment claim and the checker-bind text read `rtl/*.sv`; a VHDL design has no claim text
  there. Not changed (follow-up).
- `agent/graph/plan_arm.py`, `agent/graph/ip_closure_task.py`: the IP-library closure tasks, SystemVerilog entries only (no `.vhd`
  in `ip_lib`, review section 5.3).
