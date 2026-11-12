# b63d_nexys_net: the brief 63D network blocks on the Nexys A7-100T

The library's network blocks behind the board's RMII PHY (LAN8720A) and the 10/100 MAC `eth_mac_rmii`:
`arp_responder`, `icmp_echo`, `ipv4_udp_rx`, `ipv4_udp_tx`, `igmp_join`, the address filter (`eth_rx_classify`) and the
statistics counters (`eth_mac_stats`) of `eth_mac_rgmii` 0.2, and `mdio_master`, with a UDP statistics service on
port 5000, a host frame injector and a frame capture for checking the stack in PHY loopback without a cable. The
register map is in the header of [rtl/b63d_nexys_net_top.sv](rtl/b63d_nexys_net_top.sv).

- Simulation: [tests/test_b63d_nexys_net_rtl.py](tests/test_b63d_nexys_net_rtl.py) (cocotb, Icarus Verilog 12): a model
  RMII PHY sends an ARP request, an echo request, a frame for another station, a UDP datagram and a frame to capture;
  the shell joins an IGMP group and sends an injected frame; every frame the design sends is compared with the library
  models, and the counters are read back.
- Build: Vivado 2026.1, `flow/run_vivado.sh designs/b63d_nexys_net base`; results in [results/b63d](../../results/b63d/README.md).
- Board: not yet run. The plan, including the cabling the owner must confirm before the link phase, is in
  [host/PLAN.md](host/PLAN.md); the host script is [host/board_run.py](host/board_run.py).
