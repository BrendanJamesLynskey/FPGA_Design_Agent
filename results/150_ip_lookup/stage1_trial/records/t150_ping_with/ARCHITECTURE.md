# ARCHITECTURE: ping_responder (Nexys A7-100T)

Status: proposed for owner approval. ARCHITECTURE.md and architecture.yaml are frozen once approved; no RTL is written before that.

## Summary

The board answers IPv4 ICMP echo requests (ping) addressed to 192.168.1.50 and ARP requests for the same address, using LOCAL_MAC 02:50:4E:47:50:01. Each reply is one Ethernet frame sent over RMII. The LED0 user LED (port `led`) pulses for 100 ms per reply. The design ID register reads "PING" through the USB-UART test shell (`fpga_shell`).

Packet handling is store-and-forward: the received frame goes into one RAMB36 frame buffer. The library RMII MAC removes preamble and FCS on receive and adds them on transmit. The responder checks the IPv4 and ICMP checksums and the EtherType/addresses while the bytes arrive, so the reply decision is ready at frame end. A reply is then streamed from the same buffer with the changed fields substituted.

## Block diagram

```text
                       +-------------------------- ping_top ---------------------------+
host PC               |                                                                |
  |  USB-UART         |  UART_TXD_IN -> fpga_shell (clk) -> win -> id_reg (clk)        |
  +-----------------> |  UART_RXD_OUT <-                 ADDR 0x80 = DESIGN_ID         |
                      |                                                                |
CLK100MHZ (clk) ----> |  clk_gen: MMCME2 100->50 MHz, BUFG -> clk_eth (50 MHz)         |
                      |     ODDR -> eth_refclk pin ------------------------------------+--> PHY
                      |                                                                |
cpu_resetn ---------> |  reset_sync(clk) -> rst_clk   reset_sync(clk_eth) -> rst_eth   |
                      |  phy_rst_seq (clk) -> eth_rst_n pin -------------------------- +--> PHY
                      |                                                                |
PHY eth_crsdv/rxd/ -> |  eth_mac_rmii (clk_eth): RMII, preamble/SFD, FCS, padding      |
        rxerr         |        | rx_axis (bytes, FCS stripped)                         |
                      |        v                                                       |
                      |  responder (clk_eth) -> frame_buf (RAMB36, clk_eth)            |
                      |                             |  read                            |
                      |  reply_tx (clk_eth) <-------+  substituted fields             |
                      |        | tx_axis                                               |
PHY eth_txen/txd <----+--------+---- eth_mac_rmii (FCS and preamble added)             |
                      |                                                                |
                      |  led_pulse (clk_eth): set on reply start, clear after          |
                      |     5 000 000 clk_eth cycles --------------------------------> LED0 pin
                       +----------------------------------------------------------------+
```

Blocks: see architecture.yaml `blocks`.

## Library entries considered

- eth_mac_rmii (taken): 10/100 Ethernet MAC for an RMII PHY with preamble/SFD, FCS (CRC-32) generate and check/strip, padding and inter-frame gap, byte-wide AXI-Stream user ports (rx_axis, tx_axis). It covers the CRC-32 and the RMII MAC, so neither is written fresh. Configuration: MIN_FRAME 64, MIN_DATA 60, IFG_BYTES 12, clk = clk_eth (50 MHz RMII reference). Costs: not yet measured on xc7a100tcsg324-1 (the entry's table is pending); the predicted LUT/FF ranges in architecture.yaml cover the MAC plus the responder and reply path. Caveats from the entry: the RX stream has no back-pressure (the frame buffer always accepts), and TX must not underrun once a frame has started (reply_tx reads a buffer at line rate).
- eth_mac_rgmii (not taken): tri-mode RGMII MAC. The board is RMII, so the RGMII pins and 125 MHz clock do not apply.
- Test shell fpga_shell (taken, reused as-is from the shell).

## Clock plan

| Domain | Source | Frequency | Used by |
|---|---|---|---|
| clk | CLK100MHZ board oscillator (port `clk`) | 100 MHz | fpga_shell, id_reg, phy_rst_seq, reset_sync (clk) |
| clk_eth | MMCME2 CLKOUT (50 MHz) through BUFG; drives the eth_refclk pin through ODDR | 50 MHz | eth_mac_rmii, responder, frame_buf, reply_tx, led_pulse, reset_sync (clk_eth) |

- The MMCM is the only clock generator. No divide-by-2 register is used, so STD-CLK-01 holds.
- The two domains are phase-aligned (same MMCM). The LED timer counts LED_PULSE_CYCLES/2 = 5 000 000 clk_eth cycles, which is exactly LED_PULSE_CYCLES clk cycles.
- The only crossings are the two reset synchronisers. Every data path stays inside one domain, so there is no data CDC.
- The XDC carries the board clock constraint on CLK100MHZ (already written by board_constraints), a virtual 50 MHz clock `eth_vclk` for the RMII I/O delays (the MMCM clock has no input port to constrain), and the RMII input and output delays relative to it (design.xdc, rules FDA-CON-5 and I/O timing).

## Reset plan

- cpu_resetn is active low at the top. It enters once through xpm_cdc_async_rst (asynchronous assert, synchronous release), one instance for clk and one for clk_eth. Both outputs are active high inside.
- The MMCM `locked` output is ANDed into the reset input so no logic runs before the 50 MHz clock is stable.
- Only control registers take a reset (phy_rst_seq, the responder state, the reply state, led). Datapath registers and the frame_buf RAM have no reset.
- All internal resets are synchronous: `if (rst) ...` inside clocked always blocks.
- eth_rst_n is held low while rst_clk is high, then released PHY_RST_RELEASE_CYCLES = 1000 clk cycles after reset release.

## Pin list (board resource -> top port)

Pins are assigned by board_constraints from the master XDC; no pin numbers are written by hand.

| Board resource | Top port | Direction | Note |
|---|---|---|---|
| CLK100MHZ | clk | in | 100 MHz oscillator |
| CPU_RESETN | cpu_resetn | in | CPU RESET button, active low |
| LED0 | led | out | user LED0; spec port is the scalar `led` (OQ-07) |
| PHY refclk pin | eth_refclk | out | 50 MHz RMII reference |
| PHY reset pin | eth_rst_n | out | active low |
| PHY CRS_DV pin | eth_crsdv | in | |
| PHY RX error pin | eth_rxerr | in | |
| PHY RXD pins | eth_rxd[1:0] | in | |
| PHY TX enable pin | eth_txen | out | |
| PHY TXD pins | eth_txd[1:0] | out | |
| UART TX from host (FPGA receives) | UART_TXD_IN | in | required with the test shell; the top declares and constrains both UART pins |
| UART RX to host (FPGA sends) | UART_RXD_OUT | out | |

The board is wired RMII at 50 MHz with the reference clock from the FPGA (spec assumption); the master XDC pins for these resources were listed by board_constraints and written to design.xdc.

## Test-shell register window

- Design offset 0x00 (ID, RO, reset 0x50494E47) is shell window address 0x80 (`win_addr` 0x00). The shell reserves 0x00-0x7F, so the design's offsets are 0x80-based.
- `fpga_shell` DESIGN_ID = 0x50494E47 (PING), so the shell's own ADDR 0x00 also reports PING.
- The window read data is registered in clk, valid the cycle after win_rd. Writes to 0x80 are ignored (read-only).

## Frame processing

1. eth_mac_rmii (receive): packs the RMII dibits into bytes, strips preamble, SFD and FCS, and drops runt and FCS-bad frames. Frames are streamed on rx_axis (tdata, tvalid, tlast, tuser). The responder writes each byte into frame_buf as it arrives. Frames longer than MAX_FRAME_BYTES (1518) are dropped by the responder (length counter).
2. responder, per byte: capture EtherType, IPv4 version/IHL, flags/fragment, total length, source and destination IP, ICMP type and checksum fields, ARP opcode and target IP. Accumulate the IPv4 header one's-complement sum (bytes 14-33) and the ICMP one's-complement sum over the ICMP message. At frame end it has the decision. A frame that arrives while reply_tx is busy is not written into frame_buf and gets no reply.
3. responder decision at frame end. Accept an IPv4 echo request when: EtherType 0x0800, version 4, IHL 5, MF=0 and offset=0, destination = LOCAL_IP, IP checksum good, ICMP type 8, ICMP checksum good. Accept an ARP request when: EtherType 0x0806, opcode 1, target IP = LOCAL_IP. Frames to other destinations, broadcast, or multicast are ignored (spec defaults). The reply checksums are recomputed over the reply fields (the request's checksum fields are not reused).
4. reply_tx: streams the reply on tx_axis from frame_buf. Echo reply: destination MAC = request source MAC, source MAC = LOCAL_MAC, IPv4 TTL 64, protocol 1, source = LOCAL_IP, destination = request source IP, IPv4 checksum and ICMP checksum recomputed, ICMP type 0, identifier, sequence and payload copied from the buffer. ARP reply: opcode 2, sender = LOCAL_MAC / LOCAL_IP, target = request sender. The MAC adds preamble, SFD, padding to 60 bytes and the FCS.
5. led_pulse: led goes high on the first clk_eth cycle of a reply and goes low after 5 000 000 clk_eth cycles; a new reply restarts the count.

Reply start latency: the decision comes at frame end, a few clk_eth cycles later. This is well inside the 2000-clk latency requirement.

## Predicted resources

| Resource | Predicted | Basis |
|---|---|---|
| LUT | 400-2000 | eth_mac_rmii (library, not yet measured), responder checksums and field capture, reply_tx mux, control |
| FF | 300-1800 | eth_mac_rmii state, header field capture registers, checksum accumulators, control |
| BRAM tiles | 1 (range 1-2) | frame_buf, 2 KB x 8 simple dual port, one RAMB36 |
| DSP | 0 | no multiply needed |

## Open items and risks

- OQ-07: LED port naming. The spec names the port `led` (scalar) and the board LED is LED0; the port stays scalar `led` and board_constraints maps LED0 to it.
- The PHY wiring (RMII, 50 MHz clock from the FPGA) comes from the master XDC pins listed by board_constraints. The PHY-side I/O timing values in design.xdc are budgets, to be confirmed against the PHY datasheet.
- The UART input is asynchronous. fpga_shell is reused as-is, and its internal synchronisation is taken from the shell.
- eth_mac_rmii has no cost measurement on this part yet and its verification label is unknown; the predicted ranges are wide for that reason.
- Spec REQ-22 (ping on the bench) needs a link; PHY auto-negotiation is at strap defaults (OQ-05).
- The check_constraints run reports that the rtl/ source glob matches no file. No RTL is written in stage 1 (the architecture is not yet approved), so this is expected until stage 2.
