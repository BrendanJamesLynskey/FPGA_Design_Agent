# b2_tmp_adt7420: board self-check (brief 04c)

ADT7420 temperature sensor (I2C address 0x4B): reads the ID register (0x0B = 0xCB) and the temperature. It only ever sets the register pointer and reads.

A board self-check, not an agent benchmark task: hand-written to prove the board inventory
(`boards/nexys_a7_100t/inventory.yaml`) on hardware. The test shell (`shell/`) carries its registers; the
register map is in the header of the `*_regs.sv` file.

| Path | What |
|---|---|
| `rtl/i2c_ptr_read.sv` | I2C master: pointer write, repeated START, 1-2 byte read; open drain; waits while SCL is stretched |
| `rtl/tmp_regs.sv` | registers in the shell window |
| `rtl/b2_tmp_adt7420_top.sv` | board top (shell + registers + pins) |
| `selfcheck.py` | the on-board check and its **pass rule, pre-registered before any board run** (docstring) |
| `tests/` | cocotb + Icarus: against an ADT7420 model that loses its pointer on a STOP, NACKs a wrong address and stretches SCL |

```bash
flow/run_vivado.sh designs/b2_tmp_adt7420 base                  # build + gates (local Vivado)
python3 flow/board_check.py designs/b2_tmp_adt7420 --runs 3     # power gate, program SRAM, self-check
```

Results: `results/board_v2/b2_tmp_adt7420.json` (one file per run in `results/board_v2/runs/`).
