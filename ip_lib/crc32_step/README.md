# crc32_step 0.1.0

One CRC-32 update (IEEE 802.3, reflected, polynomial 0xEDB88320) by a 32-bit word: two operands, one result, no state; the shape of a CPU custom instruction.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated bit-exact against model.py and zlib in both variants; built into a pinned copy of the BRV32P RV32 core as a custom instruction and run there in simulation (results/64a_hwsw); not run on a board.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `IMPL` | word | word, byte | implementation variant (see variants) |

Out-of-space values fail at elaboration with `$error` (tested: `IMPL=nibble`).

## Interfaces

- `operation`: native; in_valid, crc_in, data_in -> out_valid, crc_out (LATENCY clocks later)

Clocks: `clk`. Reset: `rst`, active high, synchronous.

## Latency and throughput

- result: the variant's latency (1 or 4 clocks) from the in_valid pulse to the out_valid pulse
- throughput: the variant's II (a new word every clock, or every 4 clocks)

## Evidence

Bit-exact against `model.py` (written from the CRC definition, not from the RTL) and against zlib over whole buffers; latency and II measured; cocotb with Icarus Verilog 12. Tests: `ip_lib/crc32_step/tb/test_crc32_step_rtl.py`.
Parameter points simulated: `IMPL=['word', 'byte']`.

Seeded faults (`faults.yaml`, run by `hil/ip_faults.py --blocks crc32_step`):

| Fault | What it breaks | Result |
|---|---|---|
| `wrong_polynomial` | the normal (unreflected) polynomial in a reflected update | caught |
| `msb_first` | the word variant drops the last bit of the update | caught |
| `byte_order` | the byte variant starts from the most significant byte | caught |
| `accepts_while_busy` | an operation offered while the byte variant is busy restarts it (the II contract) | caught |
| `valid_early` | the byte variant reports after three bytes (latency 3, wrong result) | caught |

## Variants

Selected by `IMPL`; every variant has the same ports, the same bit-exact result and the same tests. Latency is clocks from an accepted input to its result; II (initiation interval) is clocks between accepted inputs, 1 meaning a new input every clock.

| Variant | What | Latency | II | Use when |
|---|---|---|---|---|
| `word` | the 32-bit update in one clock (an XOR network) | `1` | `1` | the lowest latency: the custom-instruction variant and the word-per-clock stream. Measured: 95 LUTs out of context, but 297 LUTs inside the BRV32P core, where its operand inputs are timed (results/64a_hwsw/core_ooc.json) |
| `byte` | one byte per clock through an 8-bit update, four clocks per word | `4` | `4` | area before speed. Measured: out of context no saving (96 LUTs against 95), but inside the BRV32P core 165 LUTs against 297 for word; as a custom instruction it costs three more stall clocks per word (2.29 against 1.54 cycles per byte) |

Measured at : built alone (out of context) on an Artix-7, xc7a100tcsg324-1, for a 4.0 ns clock (250 MHz), Vivado 2026.1 (build 6511674). Not run on a board.

| Variant | DSP | Block RAM tiles | LUT | Fmax estimate (MHz) | II | Latency |
|---|---|---|---|---|---|---|
| `word` | 0 | 0 | 95 | - | 1 | 1 |
| `byte` | 0 | 0 | 96 | 290 | 4 | 4 |

Fmax is estimated from one routed run at the target clock (1000 / (period - WNS)); it is not a closure at that frequency. WNS (worst slack against the clock) below zero means the target was missed. A dash means the block has no register-to-register path out of context (its logic sits between its input ports and its output registers, which an out-of-context run does not time).

<details><summary>Every measured point (2 rows; source: <a href="char/xc7a100tcsg324-1.json">char/xc7a100tcsg324-1.json</a>)</summary>

| Variant |  | LUT | FF | LUT RAM | Block RAM tiles | DSP | WNS (ns) | Fmax estimate (MHz) | Dynamic power (W) | Latency | II |
|---|---|---|---|---|---|---|---|---|---|---|
| `word` |  | 95 | 33 | 0 | 0 | 0 | - | - | 0.005 | 1 | 1 |
| `byte` |  | 96 | 92 | 0 | 0 | 0 | 0.551 | 289.9 | 0.009 | 4 | 4 |

Dynamic power is vectorless (default toggle rates, no simulation activity): use it to rank variants, not as a measurement. Regenerate with `python3 -m flow.ipchar crc32_step` (Vivado, minutes per point).

</details>

## Boundary and reuse

- Registered outputs: yes.
- Clock crossings: none.
- Part, board or pin: none.
- Depends on: nothing.
- Limits: the word variant has a combinational XOR network from the operand inputs to the result register: out of context that path is not timed, so neither its Fmax nor its LUT count there is the in-context figure (95 LUTs out of context, 297 inside the BRV32P core: results/64a_hwsw/core_ooc.json).

## Cost table

measured costs are in the Variants section above.

Licence: MIT (this repository).
