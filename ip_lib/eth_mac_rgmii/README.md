# eth_mac_rgmii 0.1.0

Tri-mode (10/100/1000 Mb/s) Ethernet MAC for an RGMII PHY: cut-through receive with the FCS verdict at the end, optional store-and-forward AXI-Stream receive, AXI-Stream transmit with padding, FCS and inter-frame gap; RX clock crossing inside.

Generated from `ip.yaml` by `flow/net/ipdoc.py`; do not edit by hand.

Status: simulated (brief 58A); built inside the brief 58A KR260 design; OOC cost table pending; not yet on a board.

## Parameters

| Name | Default | Allowed | Note |
|---|---|---|---|
| `CUT_THROUGH` | 1 | 0, 1 | 1 = cut-through view only; 0 = also the store-and-forward buffer and m_axis |
| `MIN_FRAME` | 64 | 18..2000 | receive: shortest good frame, FCS included |
| `MAX_FRAME` | 1522 | 64..2000 | receive: longest good frame, FCS included |
| `MIN_DATA` | 60 | 1..1514 | transmit: pad to this many bytes before the FCS |
| `IFG_BYTES` | 12 | 1..255 | transmit: idle byte times after the FCS (the gap is one more when a frame is waiting) |
| `SF_DEPTH` | 4096 | 2048..65536, power of two | store-and-forward buffer in bytes (CUT_THROUGH = 0) |

Constraints: `MIN_FRAME <= MAX_FRAME`; `SF_DEPTH >= 2 * MAX_FRAME when CUT_THROUGH = 0`.

Out-of-space values fail at elaboration with `$error` (tested: `CUT_THROUGH=2`, `MIN_FRAME=17`, `MAX_FRAME=2001`, `CUT_THROUGH=0, SF_DEPTH=3000`, `MIN_DATA=0`, `IFG_BYTES=0`).

## Interfaces

- `rgmii`: native; rgmii_rx_clk, rgmii_rxd[3:0], rgmii_rx_ctl, rgmii_txc, rgmii_txd[3:0], rgmii_tx_ctl
- `rx_ct`: native; rx_sof_pulse, rx_valid, rx_sof, rx_data[7:0], rx_idx[10:0], rx_end_valid, rx_end_good, rx_end_fcs_err, rx_end_runt, rx_end_giant, rx_end_er, rx_end_len[10:0]. cut-through view, always present: every frame byte (FCS included) one clock after mac_rx takes it, before the frame is known good; the verdict follows the last byte. No back-pressure
- `m_axis`: axis (dir master, tdata 8, tready True). store-and-forward, CUT_THROUGH = 0 only; good frames without their FCS; bad and overflowing frames dropped and counted (rx_sf_dropped, rx_sf_overflow)
- `s_axis`: axis (dir slave, tdata 8, tuser 1). a frame must keep coming once started (an underrun ends it with a bad FCS, tx_underrun); tuser or tx_poison marks the frame bad (inverted FCS)

Clocks: `clk` (125 MHz at every speed), `clk90` (clk, 90 degrees later (forms TXC)), `rgmii_rx_clk` (the PHY's RX_CLK (125, 25 or 2.5 MHz), on a clock buffer). Reset: `rst`, active high, synchronous.

## Latency and throughput

- rx: cut-through: a byte leaves rx_* one clock after it leaves the clock-crossing FIFO; loop simulation from the transmit MAC's first preamble byte to mac_rx's SFD: 17 clocks, 8 of them the preamble and SFD on the wire (results/b58a/pins_sim.json; the FIFO is its simulation model). Store-and-forward: the whole frame, then 2 clocks
- tx: first preamble byte on the MAC's output 2 clocks after s_axis_tvalid while idle; 2 more to TX_CTL at the pins (a register and the ODDRE1, simulation model; results/b58a/pins_sim.json)
- throughput: line rate at 10, 100 and 1000 Mb/s; frames offered back to back leave IFG_BYTES + 1 idle byte times apart (flow/net/tests/mac_rgmii_cocotb.py)

## Evidence

cocotb against a Python RGMII PHY model written from RGMII v2.0 and IEEE 802.3 (zlib's CRC-32 for the FCS), Icarus Verilog 12; at 1000, 100 and 10 Mb/s in both directions Tests: `flow/net/tests/test_58_mac_rgmii_rtl.py`.
Parameter points simulated: `CUT_THROUGH=1`; `CUT_THROUGH=0, SF_DEPTH=4096`; `CUT_THROUGH=0, SF_DEPTH=2048, MIN_FRAME=60, MAX_FRAME=1000, MIN_DATA=46, IFG_BYTES=16`.

Seeded faults (`faults.yaml`, run by `flow/net/faults.py`):

| Fault | What it breaks | Result |
|---|---|---|
| `rx_ddr_nibbles_swapped` | at 1000 Mb/s the rising-edge nibble is taken as the upper half of the byte | caught |
| `rx_nibble_alignment_ignores_sfd` | at 10/100 Mb/s bytes are aligned on the preamble instead of the SFD | caught |
| `rgmii_rx_crc_skips_first_byte` | the FCS check is computed over one byte too few | caught |
| `rgmii_rx_runt_not_flagged` | frames shorter than MIN_FRAME are not reported as runts | caught |
| `rgmii_tx_short_ifg` | the inter-frame gap is one byte time short | caught |
| `tx_no_padding` | short frames are sent without padding to MIN_DATA | caught |
| `tx_underrun_not_poisoned` | a frame cut short by an AXI-Stream underrun leaves with a good FCS | caught |
| `tx_10_100_nibbles_swapped` | at 10/100 Mb/s the upper nibble is sent first | caught |
| `sf_commits_bad_frames` | the store-and-forward buffer passes frames with a bad FCS | caught |
| `sf_keeps_fcs` | the store-and-forward output includes the FCS bytes | caught |

## Boundary and reuse

- Registered outputs: RGMII data and control through ODDRE1/IDDRE1 (behavioural models in simulation); rx_*, m_axis and the MAC's GMII side are registers.
- Clock crossings: one crossing, RX_CLK to clk: an xpm_fifo_async (16 entries, 2 synchroniser stages), the receive reset by xpm_cdc_sync_rst and the speed setting by xpm_cdc_array_single; TXC's waveform moves from clk to clk90 through one register.
- Part, board or pin: IDDRE1/ODDRE1 (UltraScale and UltraScale+) under `ifdef SYNTHESIS`; 7-series needs IDDR/ODDR instead (not yet written). Pins, IO standards, RGMII delay mode and the RX clock buffer are the board's (KB board/kr260/ethernet/kr260-four-gbe).
- Depends on: eth_mac_rmii.
- Limits: full duplex only; no MDIO (brief 58A has its own mdio_master), no pause frames, no VLAN handling, no statistics block; 10/100 nibble alignment needs the SFD; RGMII input timing is closed only for the PHY's internal RX delay mode (board XDC); measured only in simulation so far.

## Cost table

pending: the OOC sweep is not run; the whole brief 58A design on the KR260 is in results/b58a.

Licence: MIT (this repository).
