# Cleanup bundle: records (brief 80)

This folder records the measurements behind brief 80, a bundle of small follow-ups: the check of Claude Code 2.1.321 against the
agent's tool-text criterion, the formal checks of the strict register-block profile, the local run of the 63d formal tests, and the
synchronous-reset patch for the pinned BRV32P core. Each row says what was run and what it gave.

## Records

| Item | Record |
|---|---|
| Claude Code 2.1.321 | Live tool-text check: `claude-haiku-5-5` on `t1_dimmer_counter`, `python -m agent run ... --harness claude_code --stop-after 2`, stopped by hand during stage 2 after 132 tool results. CLI 2.1.321 in every init event. `mcp_text_check.py <run dir>` counts them: 132 results, 89 successful with their output text, **0 successful without text**, 43 errors (tool failures the role handled), 33 `read_file` results, none empty. Same criterion as the 2.1.318 and 2.1.319 checks. The run itself is not scored and its directory is not committed. |
| Strict profile, formal | `hwsw/tests/regmap_formal.py` oracle on the demo map under `strict` (map's own `unmapped:` line removed): bounded proof depth 20 **PASS** (wall 3 min 56 s on a loaded machine), cover depth 20 **PASS** (each rejection reachable), nine seeded strict-RTL faults each **FAIL** the proof (depth 14; `hwsw/tests/test_80_strict_formal_rtl.py`, 12 tests pass). Bounded, not unbounded. |
| 63d formal tests | `flow/net/tests/test_63d_formal.py` with `~/.local/opt/oss-cad-suite/bin` on PATH: 4 passed, 0 failed (wall 24 min 25 s on a loaded machine, 3 min CPU). The 17 failures 64A2 saw there are not reproduced; they were the missing tool path. |
| `strict` slack | Read from `results/73_profiles/raw/*/timing_summary.rpt`; table in `results/73_profiles/README.md`. No rebuild. |
| BRV32P synchronous reset | `hwsw/cfu_core/brv32p_sync_reset.patch` (37 blocks); `hwsw/tests/test_64a_cfu_core_rtl.py` checks the CRC program, trap, interrupts, kernel cycles against the committed record, and the stale-prediction verdicts with it applied. |

## Reproduce

The commands below re-run each record. The CLI check needs the Claude Code token file and uses a Haiku model call; the formal
checks need the OSS CAD Suite on PATH; the core test needs Icarus Verilog and the RISC-V GCC and takes about ten minutes.

```
# CLI check (a model call on the Max plan; Haiku): then count tool results in the run directory
python -m agent run designs/t1_dimmer_counter/spec.md --harness claude_code --cc-model claude-haiku-5-5 --stop-after 2
python3 results/80_cleanup/mcp_text_check.py runs/<run id>
# formal (oss-cad-suite on PATH)
python3 -m pytest -q hwsw/tests/test_80_strict_formal_rtl.py flow/net/tests/test_63d_formal.py
# synchronous-reset patch against the committed benches (Icarus; this test alone took 14 min on a loaded machine)
python3 -m pytest -q hwsw/tests/test_64a_cfu_core_rtl.py
```

## Known gaps and limits

- The CLI check is one run of one model on one design, stopped during stage 2; it shows tool text reaching the model, not that
  nothing else changed in 2.1.321.
- The strict formal proof is bounded (depth 20) and covers the demo map only; its oracle uses the map's own field and reserved
  definitions, so a wrong definition there would be shared with the block.
- The synchronous-reset core was simulated, not built: its area and Fmax were not measured.
