# The check suite (brief 71)

One agent tool, `check`, runs every design check through one registry (`flow/checks`) and returns a compact digest. The
same registry is called by the sign-off gates (the reset gate in `flow/gates.py` and the DOC gate), so a finding means
the same thing in the Designer's loop and at sign-off. Measured results, seeded faults and token sizes:
[results/71_check_suite](../results/71_check_suite/README.md).

## Interface

Agent tool (offered to the Designer, record key `rtl`, at stages 1 to 9):

```
check(names=["all"], scope="auto", level="standard", variant="base")
```

Command line (same code):

```
python3 -m flow.checks designs/<d> [--names all|resets,cdc,...] [--scope auto|rtl|synth|route]
                       [--level summary|standard|detail] [--variant base|ila] [--vivado never|auto] [--json OUT] [--list]
```

| Argument | Values | Meaning |
|---|---|---|
| `names` | `all`, or any of the checks below | `all` runs every check whose scopes include the scope and that applies to the design (`fsm` needs `verif/fsm.yaml`, `gt_plan` a `link:` section in spec.yaml, `doc` a `handover.yaml`); the digest lists the ones left out and why. A named check always runs. |
| `scope` | `rtl`, `synth`, `route`, `auto` | `rtl`: the sources only. `synth`/`route`: the build's reports in `build/<variant>/` for that stage. `auto`: the latest stage the build reached. |
| `level` | `summary`, `standard`, `detail` | findings shown per check in the digest: 0, 5 or 30. The full result always has all of them. |
| `variant` | `base`, `ila` | which build directory is read. |
| `--vivado` (CLI) | `never` (default), `auto` | whether the CLI may start the one Vivado session; the agent tool always may (through the session's runner, memory-capped). |

## The registry

| Check | Decided by | Scopes | What it reads |
|---|---|---|---|
| `lint` | ours (Verilator) | rtl, synth, route | Verilator `--lint-only -Wall`; in a session the `lint` tool unchanged (Icarus elaboration, FDA-CON-8/9) |
| `standards` | ours | rtl, synth, route | `flow/standards_check.py`; post-synthesis rules at synth/route |
| `resets` | AMD reports and ours | rtl, synth, route | source scan; AMD LUTAR/DPIR/DPOR/RMIR/RMOR/RROR/ROAS rows and report_cdc's reset rows; our netlist scan `reset_scan_synth.tsv` |
| `cdc` | AMD report and ours | synth, route | report_cdc (Critical rows fail) and, after synthesis, `flow/cdc_structure.py` |
| `methodology` | AMD | rtl, synth, route | report_methodology: Critical Warnings fail, Warnings are advisory |
| `drc` | AMD | synth, route | report_drc: Errors and Critical Warnings fail |
| `exceptions` | ours | synth, route | `flow/exceptions_check.py` through `flow/gates.py`'s own helper |
| `io` | ours | synth, route | `flow/io_check.py` through `flow/gates.py`'s own helper |
| `clocking` | AMD reports and ours | synth, route | CLKC methodology rows; MMCM/PLL VCO and PFD ranges (`flow/cmt_check.tcl`) |
| `dsp_ram_mapping` | AMD | synth, route | DPIP/DPOP/SYNTH/RBOR/DPIR/DPOR/RMIR/RMOR/RROR rows; DSP and RAM utilisation |
| `control_sets` | AMD | synth, route | report_control_sets (count of unique control sets); ULMTCS rows |
| `fsm` | ours | rtl, synth, route | `flow/fsm_coverage.py` on the VCDs under `build/verif` |
| `axi` | ours | rtl, synth, route | `flow/amd_ip_notes.py` (brief 69): AMD AXI4-Lite IP next to our register blocks; advice only |
| `gt_plan` | ours | rtl, synth, route | `flow/gt_plan.py` (brief 56A): every reason the spec's link cannot be built |
| `doc` | ours | rtl, synth, route | the DOC gate (`agent/graph/document.py` `doc_gate`, brief 68) |

`python3 -m flow.checks --list` prints the registry from the code.

## Where the knowledge lives

- How to detect: the check's code (`flow/checks/`, and the checker it wraps).
- What a violation is, why, the one-line fix and the waiver policy: `flow/hdl_rules.yaml` (FDA-HDL v1.1). Every code a
  check can raise maps to a rule there, and every rule is covered by a check or marked `manual`
  (`flow/tests/test_71_check_suite.py` fails otherwise).
- The background: the KB skill each rule names (`skill`), shown in the digest.

## Verdicts, and what a user could guess wrong

- **`pass`** means every part of the check that ran found nothing blocking. **`PARTIAL`** in the digest (`incomplete`
  in the JSON) means a part could not run, for example the reset netlist scan with no Vivado; the suite's overall verdict
  is then not a pass. **`not run`** always carries its reason.
- **Advisory findings never fail a check**: in the checks that mirror a stage gate (methodology, drc, cdc), Warnings
  are advisory because the gates fail only on Critical Warnings (or Errors); Advisory and Info rows and the `axi` notes
  are advisory everywhere. **The `resets` check is stricter**: AMD's reset rows at Warning (LUTAR-1, DPIR, DPOR, CDC-8)
  block there, because the house rule forbids what they describe.
- **A waiver never makes a gate-mirroring check pass** (methodology, drc, cdc, exceptions, io): a waived blocking row is
  shown as waived "the stage gate still fails on it", and the check fails as the gate does.
- **synth and route scopes read the build, not the current RTL.** After an RTL change, build again before trusting them.
  Reports the build already wrote are read, not re-run.
- **The route scope reads the post-synthesis reset scan** (`reset_scan_synth.tsv`): resets do not change in
  implementation.
- **Builds before brief 71 have no reset scan.** For those the reset gate is absent (as before), and the `resets` check is
  PARTIAL unless the one Vivado session makes the scan from `post_synth.dcp`.
- **One Vivado session per call.** Every report the requested checks need and the build did not write
  (`reset_scan`, `cmt`, `control_sets`, `qor_suggestions`, or a missing AMD report) is made in one session on the
  checkpoint, in sequence, under `systemd-run ... MemoryMax=6G`, one thread, refused while another Vivado job runs
  (`FDA_VIVADO_MAX`). A report Vivado refuses (a licence tier) is recorded as `<name>.not_run.txt` with Vivado's message
  and its check says so; a partial file is never read.
- **Waivers** are the coding standard's (`lint/waivers.yaml`: rule, match over the finding key, reason, owner, date),
  except for `resets` and `doc`, which take no waivers: the Designer may write `lint/`. A reset exception is an
  architecture decision, frozen at approval: `architecture.yaml` `reset.synchronisers` (modules allowed an asynchronous
  reset) and `reset.async_inputs` (top-level ports from an external device whose reset is asynchronous).
- **Vendor IP** internals are left out of the reset rules: cells under one of the build's IP cores
  (an ancestor module named exactly as an IP in `build/<variant>/ip/`) or under a named XPM macro (`xpm_cdc_*`,
  `xpm_fifo_*`, `xpm_memory_*`). A user module is never vendor by its name alone. A LUT outside the IP driving an
  asynchronous reset inside it is still RST-LUT-01. A user source that defines a module named like a recognised
  synchroniser (`reset_sync`, an XPM macro) is reported, unless architecture.yaml declares it.
- **Latches** (LDCE/LDPE) with a clear or preset count as asynchronous resets. Other primitives with asynchronous
  resets (IDDR/ODDR with SRTYPE ASYNC, SERDES, FIFO) are not scanned.
- **A register whose reset comes from a register with no timed clock** cannot be judged for HDL-RST-04: the check is
  PARTIAL (`netlist_clocks`) and says how many; constrain every clock.
- **A reset made by logic (a LUT) from several registers** is not traced back to them for HDL-RST-04 (a known gap).
- **A session's reports older than the checkpoint are not read**: after a rebuild the next call makes them again.
- **The source part reads the current RTL; the netlist and AMD parts read the build.** After an RTL edit, rebuild before
  reading the two together.
- **Heavy slots**: the agent's `check` tool, like its `build` tool, starts Vivado through the session's runner without
  taking a heavy slot; the script refuses while `FDA_VIVADO_MAX` Vivado jobs already run (a check-then-start test, not a
  lock). A person running `--vivado auto` on the shared PC takes a slot first.
- **The reset source part fails closed** (review round 2). It reads every module, macromodule, interface and program
  of the build's own source list (flow/prepare.py's expansion, so `rtl/**/*.sv` recurses), with `` `include`` files
  inlined. A sensitivity list it cannot read (a macro, `iff`, nested parentheses), or an include it cannot find, makes
  the check PARTIAL (`source_unread`) instead of passing. Direct FDCE/FDPE/LDCE/LDPE instances and `always_latch` blocks
  with a reset test count as asynchronous resets. VHDL files are not scanned (`source_vhdl`, PARTIAL; the netlist part
  covers them), but a VHDL entity named like a recognised synchroniser is still reported and loses the netlist exemption.
- **`reset.async_inputs` exempt only the top module's own ports.** A submodule edge on a signal of the same name is
  reported; a submodule that legitimately takes the external reset asynchronously is declared in
  `reset.synchronisers` instead.
- **A declared synchroniser exempts its whole subtree**, so it must look like one: a module in `reset.synchronisers`
  with no `ASYNC_REG` register and no `xpm_cdc_*` instance is reported. The shell's `reset_sync` is exempt by its file
  (`shell/rtl/reset_sync.sv`), not by its name.
- **Polarity (HDL-RST-02) is judged on the netlist.** The source rule sees simple tests (`!r`, `~r`, `r == 0`,
  `r === 1'b0`, extra parentheses, any `if` of a clocked block, aliases through `assign a = ~b`) on reset-like names
  (rst, reset, clr, clear) within one module. Without a netlist scan the `polarity` part is "not run", so the check is
  PARTIAL at scope rtl, never a clean pass.
- The full result is `build/checks/<variant>/<scope>.json` (named in the digest's first line); the tool never returns it
  whole.

## The reset rules (FDA-HDL v1.1, owner rule of 2026-11-13: resets are synchronous)

| Rule | Ours | AMD (Vivado 2026.1, verified) |
|---|---|---|
| HDL-RST-01 asynchronous reset only in a synchroniser or from a declared external input | RST-ASYNC-01 (netlist FDCE/FDPE; source sensitivity list) | ROAS-1 (both asynchronous set and reset) |
| HDL-RST-02 one polarity per reset | RST-POL-01 (netlist: one root, both polarities, FD and DSP/RAM reset pins), RST-POL-02 (source) | none |
| HDL-RST-03 no asynchronous reset on DSP or block-RAM registers | RST-DSPRAM-01 | DPIR-1, DPIR-2 (methodology), DPIR-3, DPOR-1..3 (DRC), RMIR-1, RMOR-1, RROR-1 (Advisory) |
| HDL-RST-04 a reset enters each clock domain through a synchroniser | RST-CDC-01 (a reset register on one clock resets registers on another; a device pin reaches registers directly) | CDC-7, CDC-8 (report_cdc) |
| HDL-RST-05 no logic drives an asynchronous reset | RST-LUT-01 | LUTAR-1 |

AMD ids were checked against `get_methodology_checks` and `get_drc_checks` on Vivado 2026.1
(`results/71_check_suite/rule_catalogue_2026_1.tsv`); report_cdc has no catalogue command, so CDC-7 was confirmed by a
seeded design that produced it.

## Adding a check

A check is one `register(Check(...))` call in `flow/checks/__init__.py`: a name, its kind (`source`, `records` or
`vivado`), the scopes `all` runs it at, the codes it can raise under their `hdl_rules.yaml` tool key, a one-line summary,
the run function (it gets a `Ctx` with the design, scope, build directory and `report(name)`, and returns findings), the
Vivado reports it needs (if any), and optionally `applies(design)` and `waivable`. Then add the rule(s) to
`flow/hdl_rules.yaml` with `fix` and `skill`, and the name to `CHECK_NAMES` in `agent/core/tools.py` (the tool's enum;
a change to the model-facing schema is a golden re-pin). Brief 73's `axi_profile` check is that: a source check over the
design's interface profiles, codes under a new `axi_profile` tool key, rules `HDL-IF-04..`.
