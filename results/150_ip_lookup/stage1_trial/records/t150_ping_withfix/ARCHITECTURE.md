# Ping responder: architecture (t150_ping_withfix)

Target: Nexys A7-100T (xc7a100tcsg324-1). Top module `ping_top`. Spec: `spec.yaml`.
Status: proposal for owner approval. architecture.yaml and this file are frozen once approved.

## Scope and decisions

- RGMII at 1000 Mb/s only (125 MHz). MDIO not accessed; eth_mdc driven low, eth_mdio tri-stated.
- The design ID is the window register at shell address 0x80 (design offset 0x00), value 0x50494E47 ("PING").
  The shell's DESIGN_ID parameter is also 0x50494E47, so shell address 0x00 reads "PING" too.
- Frame handling: only IPv4 with IHL = 5 (20-byte header) is answered. Options are discarded (assumption; owner to confirm).
- ICMP checksum is produced without a second pass over the payload: rx_frame accumulates the ones-complement sum
  while the frame is stored, so the reply starts within the 1024 tx_clk latency budget even for 1518-byte frames.
- The CRC-32 check (rx) and CRC-32 generation (tx) are written fresh; no library entry was used (see below).

## Block diagram

```text
                 +-------------------------- ping_top ---------------------------+
 CLK100MHZ ----->| clock_gen (MMCM) --> tx_clk, tx_clk90                          |
 CPU reset ----->| reset_sync (xpm_cdc_async_rst x3) --> rst_clk100/rx/tx          |
                 |                                                                |
 UART <--------->| fpga_shell -- win --> id_reg          led_ctrl ---> led (LD0)  |
                 |                          ^ reply_start (xpm_cdc_pulse) --------+
                 |                                                                |
 eth_rxc, eth_rxd|-> rgmii_rx -> rx_frame -----write-----> frame_buf (2 KB) <---+  |
 eth_rx_ctl      |   (rx_clk)     | |  |  |                  dual clock          |  |
                 |                | |  +--frame_ready (xpm_cdc_handshake)--->|  |
                 |   tx_busy <----+ |     (rx_clk -> tx_clk)                 |  |
                 |  (xpm_cdc_single,tx->rx)                                  |  |
                 |                  |                                        |  |
                 |          responder (tx_clk) <--read--------------------+  |  |
                 |                  |  buffer_release (xpm_cdc_handshake, tx->rx)
                 |                  v                                          |
 eth_txd,        |             tx_frame (tx_clk): preamble, IFG, pad, CRC-32   |
 eth_tx_ctl <----|-- rgmii_tx (tx_clk data, ODDR) <-------------------------+  |
 eth_txc  <------|-- rgmii_tx (tx_clk90 ODDR)                                   |
 eth_rst_n  <----| = ~rst_clk100                                                |
                 +----------------------------------------------------------------+
```

## Clock plan

| Domain | Source | Frequency | Used by |
|---|---|---|---|
| clk100 | clk100mhz (board oscillator) | 100 MHz | fpga_shell, reset_sync, led_ctrl, id_reg, clock_gen input |
| rx_clk | eth_rxc (PHY RGMII clock) | 125 MHz | rgmii_rx, rx_frame, frame_buf write port |
| tx_clk | MMCM CLKOUT0 via BUFG | 125 MHz | responder, tx_frame, rgmii_tx, frame_buf read port |
| tx_clk90 | MMCM CLKOUT1 (90 deg) via BUFG | 125 MHz | eth_txc ODDR only |

No gated or derived clocks outside the MMCM and BUFG. Resets are active high internally; cpu_reset
is synchronised per domain with xpm_cdc_async_rst (asynchronous assert, synchronous release).

## Reset plan

- cpu_reset (active high, spec) goes through reset_sync into rst_clk100, rst_rx and rst_tx.
- Control registers take a synchronous reset. Datapath registers (CRC, shift registers, RAM) take none.
- eth_rst_n = ~rst_clk100: low while cpu_reset is asserted.

## Clock domain crossings

| From | To | Signal | Primitive |
|---|---|---|---|
| async | clk100, rx_clk, tx_clk | cpu_reset | xpm_cdc_async_rst (in reset_sync) |
| tx_clk | clk100 | reply_start | xpm_cdc_pulse (in led_ctrl) |
| rx_clk | tx_clk | frame_ready + metadata | xpm_cdc_handshake (in rx_frame) |
| tx_clk | rx_clk | tx_busy | xpm_cdc_single (in rx_frame) |
| tx_clk | rx_clk | buffer_release | xpm_cdc_handshake (in responder) |

Known risk for STD-CDC-01: frame_buf is one dual-clock RAM (rx_clk write, tx_clk read). It is a memory, not a
synchroniser, and is read only after the frame_ready handshake and not written while buffer_release is pending.
It is not in the bank primitive list. Owner to confirm this is acceptable or to name the primitive to use.

## Resource prediction

| Resource | Predicted | Spec estimate |
|---|---|---|
| LUT | 1500 to 3500 | 2500 |
| FF | 1200 to 2800 | 2000 |
| BRAM36 tiles | 1 to 2 | 2 |
| DSP | 0 | 0 |

## Pin list (port names; pin locations come from board_constraints, not written here)

| Port | Dir | Width | Board resource |
|---|---|---|---|
| clk100mhz | in | 1 | CLK100MHZ |
| cpu_reset | in | 1 | CPU RESET (active low on the board; see open point 1) |
| led | out | 1 | LD0 |
| eth_rst_n | out | 1 | PHY reset |
| eth_txd | out | 4 | PHY RGMII TXD |
| eth_tx_ctl | out | 1 | PHY RGMII TX_CTL |
| eth_txc | out | 1 | PHY RGMII TXC |
| eth_rxd | in | 4 | PHY RGMII RXD |
| eth_rx_ctl | in | 1 | PHY RGMII RX_CTL |
| eth_rxc | in | 1 | PHY RGMII RXC |
| eth_mdc | out | 1 | PHY MDC |
| eth_mdio | inout | 1 | PHY MDIO |
| UART_TXD_IN | in | 1 | USB-UART (shell receive) |
| UART_RXD_OUT | out | 1 | USB-UART (shell send) |

## Library entries considered

- ip_lookup was not run: the tool is not exposed to the Designer in this session. CRC-32 (rx and tx),
  IPv4 header checksum and ICMP checksum are written fresh. To be re-checked with ip_lookup before RTL.

## Open points for the owner

1. Polarity at the pin: the spec port cpu_reset is active high, but the Nexys A7 CPU reset pin (CPU_RESETN) is
   active low. The inversion must happen once at the pin. Choose: (a) the top port keeps the name cpu_reset and
   board_constraints maps CPU_RESETN with an inverter in the top, which needs a separate port for the raw pin;
   or (b) accept an active-low top port. Pending owner decision.
2. frame_buf dual-clock RAM is not in the CDC primitive list (see above).
3. IPv4 options (IHL > 5) are discarded in this design.
