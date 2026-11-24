# Ping responder: architecture (ping_top on nexys_a7_100t)

Status: proposed for owner approval. Frozen with architecture.yaml once approved; no RTL before that.

## Scope

Answer ICMP echo requests and ARP requests addressed to 192.168.1.50 over the Nexys A7-100T RMII Ethernet PHY
at 100 Mb/s. Light LD0 for 100 ms on each echo reply. Expose the design ID "PING" (0x50494E47) through the
test shell window. Reset from CPU_RESETN.

## Block diagram

```text
                     +------------------------- ping_top ---------------------------+
 host UART  <------> | fpga_shell (uart_rx/sync2, uart_tx, shell_core)               |
 (UART_TXD_IN,       |      | win_* (window 0x80-0xFF)                               |
  UART_RXD_OUT)      |      v                                                        |
                     |  reg_block (ID RO 0x50494E47)                                 |
                     |                                                               |
 CPU_RESETN ---------+--> rst_sync (reset_sync x2: clk, refclk) --> rst (clk)        |
                     |                              |--> rst (refclk)                |
                     |                                                               |
 CLK100MHZ --> clk_gen (MMCME2 + BUFG) --refclk 50 MHz--> ODDR --> eth_refclk (out)  |
                     |                                                               |
 eth_rxd[1:0],       |  refclk domain             clk domain                         |
 eth_crsdv,          |  +---------+  rx_cdc   +----------+                          |
 eth_rxerr --------->|  | rmii_rx |---------->| frame_buf|--> proto (ARP, ICMP echo)|
                     |  | FCS/len |  (async   | 2 RAMB36 |        |                 |
                     |  +---------+   FIFO)   +----------+        v                 |
                     |                                       tx_cdc (async FIFO)    |
 eth_txd[1:0],       |  +---------+  <-----------------------------+                  |
 eth_txen <----------|  | rmii_tx |   FCS, preamble, SFD                            |
                     |  +---------+                                                  |
 eth_rstn  <---------|  (driven low while rst (clk) is high)                         |
 eth_mdc   <---------|  (constant 0)                                                 |
                     |  led_timer (clk): starts on reply start, LED_HOLD_CYCLES      |
 LD0 (led) <---------|                                                               |
                     +---------------------------------------------------------------+
```

## Blocks

| Block | Clock | Function |
|---|---|---|
| ping_top | - | board top, instantiates fpga_shell and the blocks below, ID register and window mapping |
| clk_gen | clk to refclk | MMCME2 100 MHz to 50 MHz, BUFG, ODDR forwarding refclk to the eth_refclk pin |
| rst_sync | clk, refclk | reset_sync: active-low CPU_RESETN to active-high synchronous reset, one per domain |
| rmii_rx | refclk | dibit to byte assembly, preamble/SFD, CRC-32 FCS check, runt (<64 B) and oversize (>1518 B) drop |
| rx_cdc | refclk to clk | xpm_fifo_async of {byte, last, good} |
| frame_buf | clk | one-frame store, 2 RAMB36, holds request and reply |
| proto | clk | EtherType 0x0806/0x0800 dispatch, ARP reply, IPv4 checks, ICMP echo reply build with recomputed checksums, TTL 64 |
| tx_cdc | clk to refclk | xpm_fifo_async of reply bytes |
| rmii_tx | refclk | dibit serialisation on eth_txd, eth_txen, FCS append, preamble/SFD |
| led_timer | clk | LED_HOLD_CYCLES countdown, restarted by each reply start |
| reg_block | clk | ID register at window offset 0x00 (shell address 0x80) |

## Clock plan

| Domain | Source | Frequency | Use |
|---|---|---|---|
| clk | CLK100MHZ (pin via board_constraints), 10 ns | 100 MHz | all logic, protocol, frame buffer, led timer, shell |
| refclk | MMCME2 from clk, BUFG | 50 MHz | RMII rx/tx dibit logic, FCS, eth_refclk to PHY |

Deviation to approve: the spec says refclk is made by toggling a flop on clk. A register clocked by a flop output
is a derived clock and fails STD-CLK-01. This design generates refclk with an MMCM and a BUFG (clock-network
primitives) and forwards it to the pin with an ODDR, so the PHY sees the same 50 MHz.

Clock crossings: rx and tx bytes cross through xpm_fifo_async. eth_rxd, eth_crsdv and eth_rxerr are sampled in the
refclk domain (RMII), so the input delay is constrained to refclk. Reset crosses through reset_sync in each domain.

## Reset

CPU_RESETN is active low and asynchronous to clk. One reset_sync per domain (clk, refclk) asserts asynchronously and
releases synchronously. Inside the design the reset is active high and is never used in an asynchronous sensitivity
list outside the synchroniser. While the clk-domain reset is high, eth_rstn, eth_txen and led are driven low (REQ-16).

## Pin list

Ports are the spec's ports on ping_top. Pins are written by board_constraints from the master XDC; no pin number is
written here.

| Port | Dir | Width | Board resource | Notes |
|---|---|---|---|---|
| CLK100MHZ (clk_100mhz) | in | 1 | CLK100MHZ | 100 MHz clock, 10 ns |
| CPU_RESETN (cpu_resetn) | in | 1 | CPU_RESETN | active low |
| eth_refclk | out | 1 | Ethernet REF_CLK | 50 MHz from ODDR |
| eth_rstn | out | 1 | Ethernet reset | active low |
| eth_crsdv | in | 1 | RMII CRS_DV | refclk domain |
| eth_rxerr | in | 1 | RMII RX_ER | refclk domain |
| eth_rxd | in | 2 | RMII RXD[1:0] | refclk domain |
| eth_txen | out | 1 | RMII TX_EN | refclk domain |
| eth_txd | out | 2 | RMII TXD[1:0] | refclk domain |
| eth_mdc | out | 1 | MDC | driven 0 |
| led | out | 1 | LD0 | bit 0 of the LED bus in the master XDC |
| UART_TXD_IN | in | 1 | USB-UART RX (FPGA input) | shell, sync2 |
| UART_RXD_OUT | out | 1 | USB-UART TX (FPGA output) | shell |

The top also has parameter BUILD_STAMP (32'h0), passed to fpga_shell.

## Resources (predicted)

| Resource | Predicted | Basis |
|---|---|---|
| LUT | 1000 to 2500 (about 1500) | parser, CRC-32 x2, checksums, shell |
| FF | 600 to 2400 (about 1200) | FIFOs, counters, shell |
| BRAM tiles | 1 to 4 (2 RAMB36) | one-frame buffer 1518 B |
| DSP | 0 to 2 (0) | no multipliers |

## Assumptions

Carried from spec.yaml: RMII PHY with FPGA-supplied 50 MHz refclk, autonegotiation straps, MDIO unused, 100 Mb/s
only, MAC 02:00:00:00:00:50, TTL 64, CPU reset is the only reset source.
