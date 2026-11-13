# axil_table_ctrl 0.1.0

AXI4-Lite front end for the match tables: 512-bit staging DATA, CMD and STATUS registers; one command at a time.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated (brief 40); OOC cost table pending.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| (none) | | | |

Out-of-space values fail at elaboration with `$error` (tested: no parameters).

## Interfaces

- `s_axil`: axi4-lite (dir slave, addr 7, data 32)
- `cmd`: native (dir master)

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Registers

This block differs from the house register conventions (docs/hwsw.md) in 2 ways: byte strobes are ignored, so every write changes the whole word (house: strobes honoured); the reset is `rst`, synchronous, active high (house: `aresetn`, synchronous, active low). Generated from `register_map` in `ip.yaml` by `hwsw/regmap.py`; the 0x80-byte window decodes address bits [6:2]. Unmapped addresses answer OKAY and read 0.

### Register map

| Offset | Register | Reset | Summary |
|---|---|---|---|
| 0x000 | DATA0 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x004 | DATA1 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x008 | DATA2 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x00c | DATA3 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x010 | DATA4 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x014 | DATA5 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x018 | DATA6 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x01c | DATA7 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x020 | DATA8 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x024 | DATA9 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x028 | DATA10 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x02c | DATA11 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x030 | DATA12 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x034 | DATA13 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x038 | DATA14 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x03c | DATA15 | 0x00000000 | Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's). |
| 0x040 | CMD | 0x00000000 | A write issues one command to the table core. A write while STATUS.BUSY is 1 is accepted (OKAY) and ignored. |
| 0x044 | STATUS | 0x00000000 | Command state; software polls BUSY after writing CMD. |
| 0x048 | ID | 0x7ab10001 | Block identity. |

Reset is what a read returns after reset with every hardware input low.

### Access types

| Access | Meaning |
|---|---|
| RO | read-only: the value comes from a hardware input (or is a constant); writes are ignored |
| WO | write-only: the hardware uses the value written; reads return 0 |
| RO const | read-only constant, fixed when the block is built |

### Behaviour

- **Unmapped addresses.** An address inside this block's 0x80-byte window that holds no register answers OKAY and reads 0; a write there is ignored. Addresses outside the window belong to the interconnect (an AXI crossbar answers DECERR there).
- **Reserved bits.** Bits that belong to no field read 0 and ignore writes. Write them as 0, so that a later version can give them a meaning.
- **Reads have no side effects.** Reading any register changes nothing, so a debugger, a retried read or a read-modify-write is safe. Writes act on the hardware only through CMD. A write to a read-only register is answered OKAY and ignored.
- **Same-clock priority (the house convention).** None applies: this block has no W1C or W1S bits.
- **Partial writes.** Byte strobes (WSTRB) are ignored on every register: every write changes the whole 32-bit word, so a CPU's byte or halfword store overwrites the other bytes. Use 32-bit stores only.
- **Access width and alignment.** 32-bit registers on a 32-bit AXI4-Lite bus. AXI4-Lite has no transfer size: a CPU's byte or halfword load reads the whole word, and its store arrives as a word write with fewer strobes (see Partial writes). Address bits [1:0] are not decoded, so an unaligned address reaches the word that holds it; only bits [6:2] are decoded, so the window repeats every 0x80 bytes. Use aligned 32-bit accesses.
- **Values wider than 32 bits.** Staging group DATA (DATA0 to DATA15, 512 bits): the hardware uses these registers only for a command (a write to CMD). Write them in any order before writing CMD, and leave them unchanged until that command has finished.
- **Reset.** `rst`, synchronous, active high (sampled on the rising edge of `clk`). Every stored field takes the reset value in its table. Every register is reset.
- **Interrupt.** None: this block has no interrupt output; software polls its status.
- **Clock domain and timing.** Every field is in the `clk` domain; hardware inputs must be synchronous to `clk` (the block has no synchronisers). A write takes effect on the hardware in the clock its write response (BVALID) is raised. A read returns the hardware's values as they were in the clock the read address was accepted.

### DATA0 to DATA15 (0x000 to 0x03c, 16 registers, the same fields)

Staging data for the next command; DATAn holds bits 32n+31 to 32n of 512 (its use is the table core's).

| Bits | Field | Access | Reset | Summary |
|---|---|---|---|---|
| 31:0 | WORD | WO | 0 |  |

### CMD (0x040)

A write issues one command to the table core. A write while STATUS.BUSY is 1 is accepted (OKAY) and ignored.

| Bits | Field | Access | Reset | Summary |
|---|---|---|---|---|
| 31:16 | ADDR | WO | 0 | the table address |
| 3:0 | OP | WO | 0 | the table operation (see the table core) |

### STATUS (0x044)

Command state; software polls BUSY after writing CMD.

| Bits | Field | Access | Reset | Summary |
|---|---|---|---|---|
| 31:16 | DONE | RO | 0x0 | commands finished since reset (wraps) |
| 7:4 | LAST | RO | 0x0 | the status code of the last command to finish |
| 0 | BUSY | RO | 0x0 | a command is running |

### ID (0x048)

Block identity.

| Bits | Field | Access | Reset | Summary |
|---|---|---|---|---|
| 31:0 | VALUE | RO const | 0x7ab10001 |  |


## Latency and throughput

- command: about 37 clocks a table command including the AXI4-Lite writes and the STATUS poll (median, exact table)
- throughput: software-bound

## Evidence

Bit-exact against the Python golden model (`flow/net/model.py`), file-driven bench (the brief-19 harness method), Icarus Verilog 12. Tests: `flow/net/tests/test_40_tables_rtl.py`.

Try it: `python3 -m pytest flow/net/tests/test_40_tables_rtl.py`.

Parameter points simulated: `defaults`.

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none.
- Depends on: nothing.
- Limits: no write strobes; one outstanding read and write.

## Cost table

pending: OOC synthesis sweep deferred (no heavy slot free on 2026-11-11).

Licence: MIT (this repository).
