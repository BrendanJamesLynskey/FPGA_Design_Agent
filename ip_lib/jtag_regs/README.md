# jtag_regs 0.1.0

Register window over the board JTAG cable (BSCANE2 USER4): the host reads and writes 32-bit registers with no UART and no processor. Common map ID 0x000, BUILD 0x004 (USR_ACCESS), SCRATCH 0x008; the design own registers from 0x010 through a simple register port.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: the common map (jtag_regs_map) simulated with cocotb and Icarus Verilog 12; jtag_bus (BSCANE2 USER4 and two xpm_cdc crossings) is designs/b58a_trigger/rtl/jtag_bus.sv, whose host script read and wrote registers on the owner KR260 on 2026-11-17 (the K26 USER4 code 0x923 and 65-bit DR are in boards/kr260/board.yaml); this entry as a whole has not been built or run on a board.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `DESIGN_ID` | 0 | 0..2147483647 | the value register 0x000 reads (a 32-bit pattern; an ID with bit 31 set is passed as the same bits, a negative int) |

Out-of-space values fail at elaboration with `$error` (tested: no parameters).

## Interfaces

- `registers`: native; u_we, u_re, u_addr[11:0] (byte address), u_wdata[31:0], u_rdata[31:0] (the design's registers, addresses 0x010 and up)

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- result: a read returns on the bus within 2 clocks of u_re; the host needs a read scan and two more JTAG scans for the data
- throughput: one register access per JTAG scan group; this is a bring-up and control window, not a data path

## Evidence

The common map (ID, BUILD, SCRATCH, read-only registers, unmapped reads 0, pass-through of the design addresses, reset of SCRATCH) in cocotb. The BSCANE2 and CDC part is the code of designs/b58a_trigger, checked there and on the KR260. Tests: `ip_lib/jtag_regs/tb/test_jtag_regs_rtl.py`.

Try it: `python3 -m pytest ip_lib/jtag_regs/tb/test_jtag_regs_rtl.py`.

Parameter points simulated: `DESIGN_ID=546439169`.

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: two, in jtag_bus: the TCK-side command into clk (xpm_cdc_single and xpm_cdc_array_single) and the clk-side response into TCK (xpm_cdc_array_single).
- Part, board or pin: BSCANE2 and USR_ACCESSE2 are Xilinx 7-series and UltraScale primitives; the BSCANE2 chain 4 (USER4) is used.
- Depends on: nothing.

## Cost table

not measured as a library entry.

Licence: all rights reserved (this repository).

## Known gaps and limits

- Jtag_bus itself is not simulated here (it needs the Xilinx models); the design is simulated through the register port h_*/u_*; the JTAG chain code is board specific (board.yaml).
- Board: no board run of this entry is recorded; its evidence is simulation.
- Cost: no out-of-context characterisation (no `characterisation:` in ip.yaml), so resources, Fmax and power are not measured for this entry.

## Next steps

1. Build it out of context and in the KR260 pilot designs (brief 209), and add the Vivado simulation test of jtag_bus with the xpm models.

## History

- 0.1.0 (2026-11-24): First version (brief 209a): jtag_bus from designs/b58a_trigger/rtl/jtag_bus.sv unchanged, the common register map (ID, BUILD = USR_ACCESS, SCRATCH) and a pass-through register port for the design's own registers. The map is simulated with cocotb; jtag_bus is not simulated here and the entry has not been run on a board as a whole.

Full entries: [CHANGELOG.md](CHANGELOG.md).
