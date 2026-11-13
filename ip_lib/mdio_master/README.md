# mdio_master 0.1.0

PHY management (MDIO, IEEE 802.3 clause 22): the two-wire bus (MDC clock, MDIO data) that reads and writes an Ethernet PHY chip's registers; one access at a time, MDC = clk / (2 x DIV), the line released for the PHY in a read from the turnaround on.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: Meets 125 MHz out of context (285-307 MHz estimated at a 250 MHz target); simulated against a clause 22 PHY model at DIV 2, 5 and 32; frame timing proved by k-induction at DIV 2 (SymbiYosys); built alone on an Artix-7 with Vivado 2026.1; first written for designs/b58a_trigger (its own copy is used there); not yet run on a board as a library entry.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `DIV` | 32 | 2..1024 | clocks per half MDC period |

Out-of-space values fail at elaboration with `$error` (tested: `DIV=1`, `DIV=1025`).

## Interfaces

- `cmd`: native; go, rd, phy[4:0], reg_a[4:0], wdata[15:0], rdata[15:0], busy. go is taken while busy is low; rdata holds the value read once busy falls
- `mdio`: native; mdc, mdio_o, mdio_t, mdio_i. mdio_t = 1 releases the line (the board top makes the tristate; the pin needs a pull-up); mdio_i must be synchronised by the board top

Clocks: `clk` (any; DIV sets MDC (at 125 MHz, DIV 32 gives 1.95 MHz, under the 2.5 MHz of clause 22)). Reset: `rst`, active high, synchronous.

## Latency and throughput

- frame: 64 bit times of 2 x DIV clocks from go to busy falling (measured in the bench and proved formally)
- throughput: one register access per 128 x DIV clocks plus one idle clock

## Evidence

cocotb against a clause 22 PHY written from IEEE 802.3 clause 22.2.4.5 (ip_lib/mdio_master/model.py) that samples on rising MDC and answers reads after a random clock-to-output delay; every bit driven, the releases, MDIO steady a clock either side of each rising MDC edge, the MDC period, the frame length and the values read; Icarus Verilog 12. Formal: the frame position, the MDC waveform, the releases and the setup and hold rule proved by k-induction at DIV 2, and a whole read covered. Tests: `flow/net/tests/test_63d_mdio_rtl.py`, `flow/net/tests/test_63d_formal.py`.

Try it: `python3 -m pytest flow/net/tests/test_63d_mdio_rtl.py flow/net/tests/test_63d_formal.py` (the formal jobs need SymbiYosys on PATH; they are skipped without it).

Parameter points simulated: `DIV=32`; `DIV=2`; `DIV=5`.

Terms (ARP, ICMP, IGMP, MDIO, RMII, RGMII, VLAN, pause, OOC, WNS, Fmax) are defined in [the library's terms](../README.md#terms).

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `mdio_preamble_31_ones` | the preamble has 31 ones before the start bits | caught |
| `mdio_turnaround_driven` | in a read the station drives the second turnaround bit that belongs to the PHY | caught |
| `mdio_read_lsb_first` | the read value is assembled least significant bit first (clause 22 sends the most significant first) | caught |
| `mdio_release_without_hold` | the line is released one clock after the last rising edge of MDC, short of the hold time at small DIV | caught |

## Cost (out of context)

Built alone (out of context) on an Artix-7, xc7a100tcsg324-1, for a 4.0 ns clock (250 MHz), Vivado 2026.1 (build 6511674); source: [char/xc7a100tcsg324-1.json](char/xc7a100tcsg324-1.json). Not run on a board.

| DIV | LUT | FF | LUT RAM | Block RAM tiles | DSP | WNS (ns) | Fmax estimate (MHz) | Dynamic power (W) |
|---|---|---|---|---|---|---|---|---|
| 2 | 101 | 167 | 0 | 0 | 0 | 0.487 | 284.7 | 0.003 |
| 32 | 99 | 162 | 0 | 0 | 0 | 0.738 | 306.6 | 0.002 |

Defaults: DIV 32. WNS is the worst negative slack (the timing margin at the target clock; below zero the target is missed).

Fmax is estimated from one routed run at the target clock (1000 / (period - WNS)); dynamic power is vectorless (default toggle rates). Regenerate with `python3 -m flow.ipchar mdio_master` (Vivado, minutes per point).

## Boundary and reuse

- Registered outputs: yes (mdc, mdio_o, mdio_t, busy, rdata).
- Clock crossings: none inside; mdio_i comes from the pin through the board top's synchroniser.
- Part, board or pin: none (the tristate buffer is the board top's).
- Depends on: nothing.

## Cost table

measured out of context: see the Cost section above.

Licence: MIT (this repository).

## Known gaps and limits

- Clause 22 only (no clause 45 indirect access); no preamble suppression; one access at a time; the line changes DIV clocks after each rising edge of MDC, so the hold time is DIV clock periods (at least 10 ns asks DIV >= 2 at 125 MHz).
- Board: no board run of this entry is recorded; its evidence is simulation and out-of-context builds.

## Next steps

1. Run the library entry on a board against a real PHY (the KR260 or the Nexys A7 network design).

## History

- 0.1.0 (2026-11-12): Initial version: simulated against a Python model, seeded faults caught, formal checks (bounded except where the README says proved), out-of-context cost on an Artix-7 (Vivado 2026.1); not run on a board. See README.md.

Full entries: [CHANGELOG.md](CHANGELOG.md).
