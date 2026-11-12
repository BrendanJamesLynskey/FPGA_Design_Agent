# b63d_nexys_net: board-run plan (Nexys A7-100T)

Status: the design is simulated (`tests/test_b63d_nexys_net_rtl.py`) and built with Vivado 2026.1
([results/b63d](../../../results/b63d/README.md)); it has not been run on the board yet.

## What it shows

The brief 63D library blocks (ARP, ICMP echo, IPv4/UDP receive and transmit, IGMPv2 join, the address filter and the
statistics counters of `eth_mac_rgmii` 0.2, and the MDIO master) working behind the board's 10/100 MAC
(`eth_mac_rmii`) and its LAN8720A PHY. The RGMII MAC itself cannot run on this board (its PHY is RMII); it waits for
the KR260.

## Phase 1: no cable (PHY loopback)

`python3 designs/b63d_nexys_net/host/board_run.py --port <shell UART> --phase loopback --out results/b63d/board_loopback.json`

1. Program the SRAM over JTAG with `flow/run_vivado.sh designs/b63d_nexys_net program` (the owner's board, selected by
   its serial; volatile only; never the flash). Take `_handoff/board.lock`.
2. Read the operating conditions (XADC Tj, VCCINT, VCCAUX, VCCBRAM) at the start, between steps and at the end.
3. Read the PHY's identifier registers (2 and 3) and status (1) over MDIO; set near-end loopback (BMCR 0x6100).
4. Inject an ARP request, an echo request and a UDP datagram to port 5000 from an invented PC address; capture the
   design's answers after the loopback and compare them with the library models.
5. Turn loopback off (BMCR 0x3100).

No frame leaves the board in loopback. This phase needs no network cable.

## Phase 2: an isolated link to a PC (needs the owner's confirmation first)

`python3 designs/b63d_nexys_net/host/board_run.py --port <shell UART> --phase link --iface <PC interface>
--isolated-link-confirmed --out results/b63d/board_link.json`

Cabling the owner must confirm before this runs:

- one Ethernet cable from the Nexys A7's RJ-45 (J4) straight to a PC network interface that is **not** connected to
  the home network (a spare USB Ethernet adapter, or a built-in port with no other link);
- no switch, router or other host on that cable;
- the PC interface set to 192.168.63.1/24, with no gateway and no DHCP on it (the board is 192.168.63.2, MAC
  02:00:00:00:00:63, both locally administered examples).

Then: `ping` the board (ICMP echo and the ARP exchange before it), read the PC's neighbour entry for the board, ask the
UDP statistics service on port 5000 for the counters, and send a datagram to 239.63.0.1:5000 before and after the board
joins that group (the filter must drop it before and pass it after; the board's IGMP report is counted in its event
registers).
