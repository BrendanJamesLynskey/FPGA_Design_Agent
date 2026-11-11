# eth_mac_rmii 0.1.0

10/100 Ethernet MAC for an RMII PHY: preamble/SFD, FCS (CRC-32) generate and check/strip, padding, inter-frame gap; byte-wide AXI-Stream user ports.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated (brief 40); OOC cost table pending.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `MIN_FRAME` | 64 | 5..1522 | receive: shortest good frame, FCS included |
| `MIN_DATA` | 60 | 1..1514 | transmit: pad to this many bytes before the FCS |
| `IFG_BYTES` | 12 | 1..255 | transmit: inter-frame gap in byte times |

Out-of-space values fail at elaboration with `$error` (tested: `MIN_FRAME=4`, `MIN_DATA=0`, `IFG_BYTES=0`, `MIN_FRAME=2000`).

## Interfaces

- `rmii`: native; rmii_crs_dv, rmii_rxd[1:0], rmii_rx_er, rmii_tx_en, rmii_txd[1:0]
- `rx_axis`: axis (dir master, tdata 8, tuser 1, tready False). no back-pressure: the line cannot wait; put a FIFO after it
- `tx_axis`: axis (dir slave, tdata 8, tuser 1). a frame must be supplied without gaps once started (underrun = aborted frame with bad FCS)

Clocks: `clk` (the 50 MHz RMII reference clock (the PHY's REF_CLK)). Reset: `rst`, active high, synchronous.

## Latency and throughput

- rx: the stream lags the wire by 5 bytes (FCS strip) plus 2 registers
- tx: first dibit 1 dibit time after the first beat is offered (when idle)
- throughput: line rate at 10 and 100 Mb/s; back-to-back minimum frames: 148,809 frames/s at 100 Mb/s measured (results/b40/measure.json mac_rx)

## Evidence

Bit-exact against the Python golden model (`flow/net/model.py`), file-driven bench (the brief-19 harness method), Icarus Verilog 12. Tests: `flow/net/tests/test_40_mac_rtl.py`.
Parameter points simulated: `MIN_FRAME=64, MIN_DATA=60, IFG_BYTES=12`; `MIN_DATA=46, IFG_BYTES=16`; `MIN_DATA=1, IFG_BYTES=1`.

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `rx_crc_skips_first_byte` | the FCS check is computed over one byte too few (the brief's example) | caught |
| `rx_ends_on_first_low_crs_dv` | CRS_DV toggling at the end of a frame is taken as the end of the frame | caught |
| `rx_runt_not_flagged` | frames shorter than 64 bytes pass as good | caught |
| `tx_pad_fcs_not_inverted` | padded frames go out with the wrong first FCS byte | caught |
| `tx_short_ifg` | the inter-frame gap is one byte time short | caught |

## Boundary and reuse

- Registered outputs: rmii_tx_en/txd and rx_axis are registers; RMII inputs registered once (IOB candidates).
- Clock crossings: none (one clock).
- Part, board or pin: none in RTL; the 50 MHz clock, its 45-degree copy to the PHY and the pins are the board's (KB board/nexys_a7_100t/ethernet).
- Depends on: nothing.
- Limits: full duplex only; no pause frames, no MDIO, no half-duplex collision handling.

## Cost table

pending: OOC synthesis sweep deferred (no heavy slot free on 2026-11-11).

Licence: MIT (this repository).
