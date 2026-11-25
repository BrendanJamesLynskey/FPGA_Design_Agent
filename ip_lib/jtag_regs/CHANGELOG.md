# jtag_regs changelog

## 0.1.0 (2026-11-24)

- First version (brief 209a): jtag_bus from designs/b58a_trigger/rtl/jtag_bus.sv unchanged, the common register map (ID, BUILD = USR_ACCESS, SCRATCH) and a pass-through register port for the design's own registers. The map is simulated with cocotb; jtag_bus is not simulated here and the entry has not been run on a board as a whole.
