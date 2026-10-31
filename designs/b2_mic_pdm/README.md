# b2_mic_pdm: board self-check (brief 04c)

PDM microphone: clocks it at 2.381 MHz and counts ones and bit changes over a window of bits.

A board self-check, not an agent benchmark task: hand-written to prove the board inventory
(`boards/nexys_a7_100t/inventory.yaml`) on hardware. The test shell (`shell/`) carries its registers; the
register map is in the header of the `*_regs.sv` file.

| Path | What |
|---|---|
| `rtl/pdm_stats.sv` | clock divider, sample point, counters |
| `rtl/mic_regs.sv` | registers in the shell window |
| `rtl/b2_mic_pdm_top.sv` | board top |
| `selfcheck.py` | the on-board check and its **pass rule, pre-registered before any board run** (docstring) |
| `tests/` | cocotb + Icarus: against a microphone model (the counts must match the bits sent; a stuck line) |

```bash
flow/run_vivado.sh designs/b2_mic_pdm base                  # build + gates (local Vivado)
python3 flow/board_check.py designs/b2_mic_pdm --runs 3     # power gate, program SRAM, self-check
```

Results: `results/board_v2/b2_mic_pdm.json` (one file per run in `results/board_v2/runs/`).
