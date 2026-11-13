# b63d_nexys_net: a small network stack on the Nexys A7-100T

An FPGA design that answers ping and ARP, receives and sends UDP, joins an IGMP multicast group and counts frames, all
on the board's 10/100 Ethernet PHY (a LAN8720A on an RMII interface). Simulated and built with Vivado 2026.1;
**not yet run on a board**.

What is in it (the register map is in the header of [rtl/b63d_nexys_net_top.sv](rtl/b63d_nexys_net_top.sv)):

- the 10/100 MAC `eth_mac_rmii`, and the address filter and statistics counters of `eth_mac_rgmii`;
- `arp_responder` (address resolution), `icmp_echo` (ping), `ipv4_udp_rx` and `ipv4_udp_tx` (UDP), `igmp_join`
  (multicast membership) and `mdio_master` (PHY registers), all from [ip_lib](../../ip_lib/README.md);
- a UDP service on port 5000 that answers any datagram with "N63D" and the 21 counters;
- a frame injector and a frame capture, so the host can check the stack with the PHY looping frames back, no cable;
- the XADC's temperature and supply readings, with alarms latched between the host's polls.

Try it:

```
python3 -m pytest designs/b63d_nexys_net/tests            # simulation through the test shell, I/O constraint checks, host safety checks
flow/run_vivado.sh designs/b63d_nexys_net base            # build (Vivado 2026.1)
```

The build ([results/b63d](../../results/b63d/README.md)) passes every flow gate at 50 MHz, with the RMII receive and
transmit constraints timed against the 50 MHz clock the FPGA sends to the PHY. On the board: see [host/PLAN.md](host/PLAN.md),
which includes the isolated-cable check that must be confirmed first; the host script is
[host/board_run.py](host/board_run.py).
