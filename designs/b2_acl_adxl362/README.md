# b2_acl_adxl362: board self-check (brief 04c)

ADXL362 accelerometer (SPI mode 0): reads the ID registers, starts measurement, reads one X/Y/Z sample and returns the part to standby.

A board self-check, not an agent benchmark task: hand-written to prove the board inventory
(`boards/nexys_a7_100t/inventory.yaml`) on hardware. The test shell (`shell/`) carries its registers; the
register map is in the header of the `*_regs.sv` file.

| Path | What |
|---|---|
| `rtl/spi_burst.sv` | SPI mode-0 master, 1-8 byte transfers |
| `rtl/acl_regs.sv` | registers in the shell window |
| `rtl/b2_acl_adxl362_top.sv` | board top |
| `selfcheck.py` | the on-board check and its **pass rule, pre-registered before any board run** (docstring) |
| `tests/` | cocotb + Icarus: against an ADXL362 model (commands 0x0A/0x0B, address auto-increment, a mode-0 check) |

```bash
flow/run_vivado.sh designs/b2_acl_adxl362 base                  # build + gates (local Vivado)
python3 flow/board_check.py designs/b2_acl_adxl362 --runs 3     # power gate, program SRAM, self-check
```

Results: `results/board_v2/b2_acl_adxl362.json` (one file per run in `results/board_v2/runs/`).
