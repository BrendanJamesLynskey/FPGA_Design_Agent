# eth_mac_rgmii changelog

## 0.2.0 (2026-11-12)

- All new features are off by default, so existing users are unaffected: at the defaults the entry behaves as 0.1.0
  (0.1.0's three test points pass unchanged; designs/b58a_trigger's tests pass; an independent clock-by-clock
  comparison with 0.1.0 found no difference).
- Receive address filter (FILTER): own unicast, broadcast, promiscuous, multicast by an exact table (MC_EXACT
  entries) and a 64-bin CRC hash (eth_rx_classify).
- VLAN tag report (VLAN = 1) and strip from the store-and-forward output (VLAN = 2), TCI beside the frame.
- IEEE 802.3x pause (PAUSE): received pause frames hold new transmit frames for quanta x 512 bit times; pause_req
  sends a pause frame ahead of waiting data; MAC control frames are consumed.
- Statistics counters (STATS, eth_mac_stats): 21 wrapping counters of STAT_W bits.
- Jumbo frames: MAX_FRAME up to 9216, lengths widen to 14 bits (mac_rx and mac_tx take LEN_W, default 11, so their
  ports are unchanged), the buffer sized by the SF_DEPTH guard.
- Implementation variants (RX_RAM): the buffer in block RAM or LUT RAM; characterised out of context on xc7a100t.
- IO_FAMILY: 7-series IDDR/ODDR beside the UltraScale primitives.

## 0.1.0 (2026-11-12)

- Initial version: tri-mode RGMII MAC with cut-through receive and an optional store-and-forward
  buffer; simulated at three parameter points and three speeds; see README.md.
