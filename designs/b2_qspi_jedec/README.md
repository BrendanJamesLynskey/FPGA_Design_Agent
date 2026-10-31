# b2_qspi_jedec: board self-check (brief 04c)

Configuration flash JEDEC ID (S25FL128S or S25FL127S): RDID (9Fh) only, with SCK through STARTUPE2. It never writes the flash.

A board self-check, not an agent benchmark task: hand-written to prove the board inventory
(`boards/nexys_a7_100t/inventory.yaml`) on hardware. The test shell (`shell/`) carries its registers; the
register map is in the header of the `*_regs.sv` file.

| Path | What |
|---|---|
| `rtl/qspi_rdid.sv` | constant opcode 9Fh, 8 ID bytes, a clock preamble for STARTUPE2 |
| `rtl/qspi_regs.sv` | registers in the shell window |
| `rtl/b2_qspi_jedec_top.sv` | board top with STARTUPE2 |
| `lint/STARTUPE2.sv` | lint-only stand-in for the primitive |
| `selfcheck.py` | the on-board check and its **pass rule, pre-registered before any board run** (docstring) |
| `tests/` | cocotb + Icarus: source checks (9Fh is the only opcode; no write, erase or register-write opcode literal; no multi-bit input to the reader) and a flash model that decodes every command it receives |

```bash
flow/run_vivado.sh designs/b2_qspi_jedec base                  # build + gates (local Vivado)
python3 flow/board_check.py designs/b2_qspi_jedec --runs 3     # power gate, program SRAM, self-check
```

Results: `results/board_v2/b2_qspi_jedec.json` (one file per run in `results/board_v2/runs/`).
