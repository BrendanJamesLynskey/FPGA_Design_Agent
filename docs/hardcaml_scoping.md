# Hardcaml scoping: OCaml-generated RTL through the flow (brief 171)

[Hardcaml](https://hardcaml.org), an open-source OCaml hardware library (hardcaml.org), was installed user-local and used to rewrite two
ip_lib blocks, `pipe_reg` and `credit_chan`. The generated Verilog was run through the existing cocotb benches and formal wrappers unchanged,
through Verilator lint and the reset-rule check, and built out of context in Vivado beside the hand-written SystemVerilog. A small, labelled
probe asked Sonnet for three small blocks in each language. This page is the result and the recommendation. Raw results: `results/b171/`.

## Summary

- **Install:** works user-local (opam 2.6.1, OCaml 5.3.0, Hardcaml v0.17.1, no sudo). Needs the system packages `libgmp-dev` and `m4` (a Zarith
  dependency; the owner installed them). `tools/hardcaml/install_hardcaml.sh`; every package licence is MIT, the compiler is LGPL with the
  OCaml linking exception, Zarith LGPL-2.0 with the same exception (`results/b171/licences.txt`).
- **Functional equivalence:** the generated Verilog passes the existing benches unchanged. `pipe_reg`: 73 of 73 pytest cases (32 random-traffic
  points, 32 measured-latency/throughput/capacity points and the 9 elaboration-guard cases); `credit_chan`: 52 of 52 (`results/b171/*_hc_sim.txt`).
- **Formal:** the existing wrappers run on the generated Verilog, but only as bounded model checks (depth 24): 14 of 14 `pipe_reg` and 10 of 10
  `credit_chan` points pass. The unbounded k-induction proofs do **not** close (UNKNOWN at every point): the SV proofs lean on invariants written
  inside the slices (`ifdef FORMAL`), and Hardcaml's Verilog has no place for them. So formal assurance of generated code is weaker than for the
  hand-written code until invariants can be bound from outside (next steps).
- **Quality of results:** 24 out-of-context synthesis builds (2 blocks, 6 points, a7 and k26): FF equal or lower for Hardcaml, LUT within 7 either way,
  all timing met; Hardcaml has the lower WNS in 8 of 12 pairs (gaps up to 0.4 ns). Synthesis only, single runs (section 4).
- **Agent fluency (a probe, not an eval):** Sonnet wrote all three small blocks in both languages; SV passed first time 9 of 9, Hardcaml 8 of 9
  (9 of 9 after one repair round). Ceiling effect: the tasks were too easy to separate the languages.
- **Recommendation:** do not make Hardcaml a first-class agent input language now. Offer it as an optional, human-driven source for generated
  IP, with the generated Verilog committed. Details and costs below.

## 1. Install

`tools/hardcaml/install_hardcaml.sh` (idempotent). Choices that matter:

| Item | Value |
|---|---|
| opam | 2.6.1 binary, GPG-verified when downloaded; root `~/.local/opt/opam`; `opam init --bare --disable-sandboxing -n` (no shell-profile edits, no bubblewrap) |
| Switch | `hardcaml-5.3.0`: OCaml 5.3.0 (the Hardcaml v0.17.1 packages need >= 5.3.0) |
| Packages | `hardcaml` v0.17.1, `ppx_hardcaml` v0.17.1, `hardcaml_waveterm`, `hardcaml_step_testbench`, `hardcaml_verify` v0.17.0, `ppx_jane`; the full solved list is `results/b171/opam_list.txt` (112 lines) |
| System packages | `libgmp-dev`, `m4` (owner-installed from Ubuntu). Nothing else was missing |
| Build time | tens of minutes in total (compiler, then 99 library packages), niced, `-j2`, under `MemoryMax=4G`; not timed separately, on a loaded PC |
| Licences | MIT for Hardcaml and the other libraries listed; LGPL-2.1-or-later with the OCaml linking exception for the compiler |

What is available, and what was used:

| Piece | Used here? | Note |
|---|---|---|
| `hardcaml` (signals, `Always` DSL, cyclesim, `Rtl` Verilog/VHDL writers) | yes | the whole design and test path |
| `ppx_hardcaml` / `ppx_jane` | tests only | `let%expect_test`; the library code uses no ppx for interfaces, so widths stay run-time values |
| `hardcaml_waveterm` | installed, not used | text waveforms inside expect tests; the tests print tables instead |
| `hardcaml_step_testbench` | installed, not used | a monad-style testbench over cyclesim; not needed for directed and scoreboard tests |
| `hardcaml_verify` | installed, not used | its formal helpers need a back-end solver; the existing SymbiYosys flow was used instead |

## 2. The two ports

| | `pipe_reg` | `credit_chan` |
|---|---|---|
| Hardcaml source | `ip_lib/pipe_reg/hardcaml/src/pipe_reg_hc.ml` (242 lines) | `ip_lib/credit_chan/hardcaml/src/credit_chan_hc.ml` (156 lines) |
| Hand-written SV | `rtl/pipe_reg.sv` + `rtl/pipe_reg_slice.sv` (553 lines, about a third is `ifdef FORMAL` ghost logic and assertions) | `rtl/credit_chan.sv` (283 lines, similar) |
| Covers | all five slice kinds, N slices, tlast, tkeep, tuser | the credit counter, LF and LB stages, the receive FIFO with pointers, all sidebands |
| Hardcaml tests | `test/test_pipe_reg_hc.ml`: five directed traces plus a 3000-clock scoreboard per mode and N (order, no loss, output holds while stalled) | via the shared cocotb bench (no separate expect tests; see gaps) |
| Existing cocotb bench, unchanged | 73 of 73 | 52 of 52 |
| Existing formal wrapper, unchanged | BMC depth 24: 14 of 14; k-induction: 0 of 14 (UNKNOWN) | BMC: 10 of 10; k-induction: 0 of 10 |

The second block is `credit_chan` (not the DWT, not `rate_match_gp`), the circular-buffer FIFO plus credit counter: the "pointer logic" of
brief 171 in a self-contained form.

**How the generated Verilog meets the existing benches.** Hardcaml writes Verilog with no parameters. `gen.exe` therefore writes one module
per parameter point (`pipe_reg_hc_w16_n2_m1_000`) and a generated wrapper named `pipe_reg` / `credit_chan` with the SV block's own parameters and
ports. The wrapper picks the module whose point matches (`generate if`); a point that was not generated stops elaboration with `$error`, so the
guard tests still see a failure for illegal parameters. The tests point at it through the existing `NET_RTL_<BLOCK>` variable. Nothing in
`tb/` or `formal/` was edited. A consequence: **the set of supported points is fixed when the Verilog is generated** (the bench's 32 points plus the default for
`pipe_reg`, 19 plus 3 sideband points plus the default for `credit_chan`), not open-ended like the SV's parameters.

**Formal.** `gen.exe -formal` adds the SV's ghost counters (`f_in_o`, `f_out_o`) as outputs so `formal_pipe.sv` and `formal_credit.sv` bind as written.
The slices' own invariants are the missing part (see summary). Run: `ip_lib/<block>/hardcaml/run_hc.sh formal`.

## 3. Flow gates and lint

`ip_lib/pipe_reg/hardcaml/lint_hc.py` (output `results/b171/pipe_reg_lint.json`):

- **Verilator `--lint-only -Wall`**, five parameter points, SV and Hardcaml side by side. Both exit non-zero under `-Wall`, as does the hand-written
  block (`DECLFILENAME`, `UNUSEDSIGNAL` and, for SV, `UNUSEDPARAM`). Hardcaml adds `UNDRIVEN` (6 at the sideband point) from the wrapper's tied-off
  unused sidebands, and the same `UNUSEDSIGNAL` family for ports it does not use. Nothing structural (no latch, no width truncation) was reported for either.
- **Reset source check** (`flow/checks/resets.py`, yosys-slang elaboration): `ran`, 0 findings for SV and 0 for Hardcaml (synchronous resets only,
  as the house rules require; Hardcaml's `Reg_spec` clear is synchronous).
- **Full flow gates** (`flow/gates.py`, the design-level checks) take a `designs/<d>` folder with `build.yaml` and architecture files. These blocks are
  ip_lib entries, not designs, so those gates were not run on either implementation. The design-level gates would see the generated Verilog as
  ordinary Verilog; the open question is only waivers and source mapping (below).

## 4. Vivado comparison (out of context)

Run 2026-11-24 (`python3 tools/hardcaml/ooc_compare.py run`, 24 builds, Vivado 2026.1, one thread, out-of-context synthesis only, no place and route).
Clocks: 3.0 ns on the Artix-7 `xc7a100tcsg324-1` (a7), 2.0 ns on the Kria K26 `xck26-sfvc784-2LV-c` (k26). Each cell is SV / Hardcaml.
WNS is the post-synthesis estimate in ns; Fmax is 1000 / (clock - WNS), the flow's own estimate, so it is not a routed figure.
Raw data: `results/b171/ooc_compare.json`.

| point | part | LUT | FF | WNS ns | Fmax MHz |
|---|---|---|---|---|---|
| credit_chan_w16_c8_f1_b1 | a7 | 26 / 27 | 34 / 34 | 0.964 / 1.176 | 491 / 548 |
| credit_chan_w64_c5_f2_b1 | a7 | 56 / 58 | 145 / 145 | 0.883 / 0.748 | 472 / 444 |
| credit_chan_w8_c16_f4_b4 | a7 | 45 / 40 | 47 / 43 | 0.866 / 0.423 | 469 / 388 |
| pipe_reg_comb_w16_n5 | a7 | 11 / 11 | 85 / 85 | 0.385 / 0.028 | 382 / 336 |
| pipe_reg_full_w64_n2 | a7 | 83 / 90 | 268 / 268 | 0.176 / 0.152 | 354 / 351 |
| pipe_reg_skid_w64_n2_tlast_tkeep | a7 | 81 / 81 | 298 / 298 | 0.465 / 0.355 | 394 / 378 |
| credit_chan_w16_c8_f1_b1 | k26 | 23 / 25 | 34 / 34 | 0.940 / 0.954 | 943 / 956 |
| credit_chan_w64_c5_f2_b1 | k26 | 52 / 54 | 145 / 145 | 1.028 / 0.868 | 1029 / 883 |
| credit_chan_w8_c16_f4_b4 | k26 | 41 / 40 | 47 / 43 | 0.913 / 0.619 | 920 / 724 |
| pipe_reg_comb_w16_n5 | k26 | 10 / 9 | 85 / 85 | 0.878 / 0.807 | 891 / 838 |
| pipe_reg_full_w64_n2 | k26 | 77 / 78 | 268 / 268 | 0.745 / 0.838 | 797 / 861 |
| pipe_reg_skid_w64_n2_tlast_tkeep | k26 | 80 / 80 | 298 / 298 | 0.750 / 0.677 | 800 / 756 |

**Reading.**
- FF are identical in 10 of 12 pairs and 4 lower for Hardcaml in the `w8_c16_f4_b4` credit channel on both parts (43 vs 47). LUT differ by at most
  7 (`pipe_reg_full` on a7, 83 vs 90) and by 1 to 2 elsewhere; neither language is consistently smaller.
- Timing differs by more, in both directions: Hardcaml is worse in 8 of 12 pairs (largest on a7: `pipe_reg_comb` 0.385 vs 0.028 ns, `w8_c16_f4_b4`
  0.866 vs 0.423 ns), better in 4. These are synthesis-only estimates with single runs and no repeats, so differences below about 0.1 ns are
  inside the noise we have not measured; the larger gaps (0.3 to 0.4 ns) are probably real but not explained (likely different net structure
  and flattened names changing what the synthesiser retimes or shares; not investigated).
- Every run met timing (WNS positive) and no build failed. Area cost of the generated Verilog is small; timing cost is not zero.
- Limits: two blocks, six points, synthesis only. Nothing here says what place and route would give.

## 5. Readability of the generated Verilog

- **Names.** Registers keep the names given with `--` (`g0_m_valid`, `g1_t_data`, `credits`, `wp`, `rp`), so the nets that matter appear in timing
  and utilisation reports. Everything combinational becomes numbered wires (`_19`, `_56`); in the `pipe_reg` w16 n2 skid module 37 of 64 declarations
  are `_N` wires. A timing path that starts and ends at registers is readable; one through logic needs the source side by side.
- **Hierarchy.** Flat. Each Hardcaml circuit is one Verilog module; slices and the FIFO are not separate modules (the generated wrapper adds one
  instance level). So `report_utilization -hierarchical` cannot attribute LUTs to slices, which the SV's `pipe_slice_skid` instances allow. Hardcaml
  has a `Hierarchy` mechanism that makes a module per sub-circuit; using it needs fixed-width interface records (ppx_hardcaml), which fights the
  run-time widths used here. Not tried.
- **Path to source.** Via the register names to the OCaml: `g1_m_data` is the `m_data` variable of slice 1 in `slice_skid`. There is no `#line`-style
  mapping, so a tool that reports a line number reports a line of the generated file. 
- **Size.** About 200 lines of Verilog per parameter point: the 33-point `pipe_reg` file is 6,900 lines. Commit the generated file and a hash of its sources, or regenerate in CI.
- **Behaviour in Verilog.** Hardcaml writes `reg` with an `always @(posedge clk)` per register, no `initial` blocks (registers start unknown in
  simulation, as in the SV), and synchronous reset exactly as `Reg_spec` says.

## 6. Agent fluency probe

A probe, not a scored eval: three tasks, three runs per language, one model, one session, no pre-registration, no held-out data, and the checker is
a bench written by the same session that wrote the tasks. `tools/hardcaml/probe/probe.py`; records `results/b171/probe/`.

- **Model:** Claude Sonnet 5.5 (`claude-sonnet-5-5`, via Claude Code headless on the plan, no tools, no repository access, empty working folder).
- **Tasks:** the cores of three dev-set tasks, restated as module specs (`gray_step`, `bcd_updown`, `fifo16` from `t1_gray_stepper`, `t1_bcd_updown`,
  `t1_sync_fifo_regs`); never a held-out task.
- **Attempt:** the spec plus a one-paragraph language instruction, no example code on either side, up to two repair rounds given the raw tool error.
- **Checker:** SV via `iverilog -g2012`; Hardcaml via `dune build` (warnings off) and the Verilog the circuit prints; then the shared cocotb bench (3000
  random clocks, mid-run resets, outputs checked every clock against a Python golden model).

| | compiled first time | passed first time | passed after repair (max 2 rounds) | cost (provider-reported, list price) |
|---|---|---|---|---|
| SystemVerilog | 9 / 9 | 9 / 9 | 9 / 9 | $0.12 total |
| Hardcaml | 9 / 9 | 8 / 9 | 9 / 9 (one repair round) | $0.24 total |

The one Hardcaml failure (`gray_step`, run 2) was a single mismatch in 3000 checks; the repaired file passed. Hardcaml answers were about 2.4 times as
long in output tokens (15,790 against 6,496, over 10 and 9 calls). Read this as: Sonnet already writes small Hardcaml that compiles and works, and
the cost is in tokens. It says nothing about harder blocks, about timing closure, or about the languages' ceilings. A real comparison needs
harder tasks, more runs and the full agent loop.

## 7. Recommendation

**Is Hardcaml worth full support as an input language for the agent and the IP library?** Not yet. The evidence supports a narrower step.

For:
- Functional parity is cheap to reach: both blocks passed every existing check first time after the gen step; the OCaml is shorter than the SV once
  formal logic is excluded, and parameter-dependent structure (N slices, LF/LB stages) is ordinary list code instead of `generate`.
- Sonnet writes small Hardcaml correctly (probe).

Quality of results (section 4): area is a wash and timing is slightly worse more often than not, so this is a cost to watch, not a reason to refuse.

Against, at what cost:
1. **Flow changes.** Generated Verilog must become a build step: install (opam, 25 min, two system packages), `dune build`, `gen.exe`; the
   build cache and the flow's source lists need a rule for "source of truth is OCaml, committed Verilog is a derived file". Estimate (opinion, not measured): about a day of flow
   work for the generator and CI (CI installs OCaml: caching the switch matters, the install is the slow part).
2. **Source mapping of reports.** Timing, utilisation, CDC and DRC reports name the generated Verilog's nets. We would need a name-preserving
   convention (done by hand here with `--`), hierarchy (not working yet) and a tool that maps a report line back to an OCaml definition. Estimate (opinion): about two
   days, and the result is only as good as the naming discipline.
3. **Formal.** The unbounded proofs do not carry over (UNKNOWN). Closing this needs invariants outside the generated module (SVA `bind` files that
   reach internal registers by their stable names) or a Hardcaml route to emit assertions. Until then, generated blocks are BMC-checked only; that
   is a weaker evidence level and the library's "verified" label (decisions 24 and 26) must say which blocks have it.
4. **Parameters.** The generated module has no parameters, so points are enumerated. For the library's reuse rules that is a regression from the
   parameter-space contract in `ip.yaml` (the wrapper hides it).
5. **Agent knowledge.** KB skills for Hardcaml (API shapes, the `Always` DSL, cyclesim, naming for report mapping) and a retrieval path; the
   agent's gates and error digests (lint, reset check) already work on the generated Verilog and need no change. Roughly a skill set of the size of
   one existing language skill.
6. **Maintenance.** A second toolchain (opam, OCaml, dune) to pin and a second language every reviewer must read.

**Suggested position.** Hardcaml as an **optional generator for library IP** whose structure is parametric (chains, pipelines, FIFOs, trees), written
and reviewed by a human or by the agent on request, with the generated Verilog committed beside the OCaml and tested by the existing benches
unchanged. Not an agent default: the agent's gates, proofs and reports are built around SV, and this scoping shows where they thin out.

**What a user could get wrong** (document these where a Hardcaml block is published):
- editing the generated Verilog instead of the OCaml; it is overwritten by the next `gen`;
- assuming the generated wrapper accepts any parameter value: only generated points elaborate, anything else stops with `$error`;
- assuming the formal proofs carry over: they are bounded (BMC depth 24) here;
- trusting numbered `_N` names across regeneration: they change when the circuit changes; only `--` names are stable;
- registers start unknown in simulation (no `initial`), and the generated reset is synchronous and active high inside (`rst = ~aresetn`);
- Hardcaml's Verilog drops unused inputs from a module's port list (an N = 0 `pipe_reg` has no clock port; the wrapper handles that);
- `OPAMROOT` must be set to `~/.local/opt/opam` and the switch activated (`eval $(opam env --switch=hardcaml-5.3.0)`); `opam init` was run with `-n`
  so no shell profile was edited.

## Next steps (ranked)

1. Close the formal gap: bind the slices' invariants from outside the generated module (SVA `bind` on stable register names) and re-run k-induction.
2. Hierarchy: try Hardcaml's `Hierarchy` for the slice and the FIFO so utilisation attributes to modules.
3. A report-to-source map for names (`--` discipline plus a script), then decide on agent support.
4. A harder fluency probe (a block with a protocol and a timing constraint), more runs, the full agent loop, the dev-set split.
5. If the library adopts it: a CI job that regenerates and diffs the committed Verilog.

## Gaps and limits

- One FPGA family pair (Artix-7 and Kria K26) and six parameter points: a comparison, not a characterisation.
- `credit_chan` has no Hardcaml expect tests of its own (its evidence is the existing bench); `pipe_reg` has them.
- `hardcaml_waveterm`, `hardcaml_step_testbench` and `hardcaml_verify` were installed but not exercised.
- Hardcaml v0.17.x only; the install resolves against the opam repository of 2026-11-22.
- No board run (none needed for this scoping).
