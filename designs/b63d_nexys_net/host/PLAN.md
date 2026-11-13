# b63d_nexys_net: board-run plan (Nexys A7-100T)

This plan is meant to show the network blocks working on real hardware in two steps: first with no cable (the PHY
looping frames back), then over one cable to a PC that is isolated from every other network.

Status: simulated (`tests/test_b63d_nexys_net_rtl.py`) and built with Vivado 2026.1
([results/b63d](../../../results/b63d/README.md)); not run on the board yet.

The RGMII MAC itself cannot run on this board (its PHY is RMII); it waits for a board with an RGMII PHY.

Terms: **near-end loopback** is a PHY mode (BMCR bit 14, set over MDIO) that sends the MAC's transmit data straight
back to its receive side; **XADC** is the FPGA's on-chip monitor of die temperature (**Tj**) and supply voltages; a
PC's **neighbour entry** is its ARP cache line for an address.

## Phase 1: no cable (PHY loopback)

Before starting: no cable in the board's Ethernet jack (J4).

`python3 designs/b63d_nexys_net/host/board_run.py --port <shell UART> --phase loopback --out board_loopback.json`

1. Program the FPGA over JTAG with `flow/run_vivado.sh designs/b63d_nexys_net program` (the board is selected by its
   serial number; this loads the volatile SRAM only, never the flash).
2. Read the operating conditions at the start, between steps and at the end.
3. Read the PHY's identifier registers (2 and 3) and status (1) over MDIO; set near-end loopback (BMCR 0x6100).
4. Inject an ARP request, an echo request and a UDP datagram to port 5000 from an invented PC address; capture the
   design's answers after the loopback and compare them with the library models.
5. Turn loopback off (BMCR 0x3100).

In near-end loopback the PHY is expected to keep the frames on the board; this has not been observed yet.

Expected result: registers 2 and 3 read the LAN8720A's identifier (0x0007, then 0xC0Fx), the three captured answers
equal the models' frames byte for byte (ARP reply, echo reply, a UDP datagram that starts with "N63D"), the counters
show the injected and answered frames, every condition sample is inside the recommended operating conditions and no
alarm is latched. A pass would show the stack's logic working on the device through the real PHY, not the cable side.

## Phase 2: an isolated link to a PC (needs a cable check first)

`python3 designs/b63d_nexys_net/host/board_run.py --port <shell UART> --phase link --iface <PC interface>
--isolated-link-confirmed --out board_link.json`

The cabling to confirm before this runs:

- one Ethernet cable from the Nexys A7's RJ-45 (J4) straight to a PC network interface that is **not** connected to
  any other network (a spare USB Ethernet adapter, or a built-in port with no other link);
- no switch, router or other host on that cable;
- the PC interface set to 192.168.63.1/24, with no gateway and no DHCP on it (the board is 192.168.63.2, MAC
  02:00:00:00:00:63, both locally administered examples);
- IPv4 forwarding and proxy ARP off on that interface (Docker turns forwarding on for every new interface):
  `sudo sysctl -w net.ipv4.conf.<interface>.forwarding=0 net.ipv4.conf.<interface>.proxy_arp=0`;
- the cable plugged in before the run (the check needs carrier).

The script checks what it can see before sending anything, and again before each step that sends. It refuses if the
interface is not a physical PCI or USB network device with carrier, is stacked on or enslaved to another interface (a
VLAN, macvlan, bridge port or bond member, for example), has any IPv4 address but 192.168.63.1/24 or any IPv6 address
but a link-local one, has any route but 192.168.63.0/24 in any routing table (a default or a split default, multipath
included) or an IPv6 default route, has IPv4 forwarding or proxy ARP on, carries the route to the home gateway, would
not carry the board's or the group's traffic, or if any host other than the board (at its expected MAC) appears on the
subnet, IPv6 neighbours included. A query that fails stops the run. It then listens for 10 seconds and refuses if any
frame arrives: the idle board sends nothing unsolicited (by the design's RTL: IGMP reports only after a join, ARP
requests only after a UDP request), while a home network delivers broadcasts every few seconds. That is the one check
that sees past the cable; it would not notice a quiet network, so the cabling confirmation is still needed. Every
socket is bound to the interface, and multicast leaves through it with TTL 1.

Then: `ping` the board (ICMP echo and the ARP exchange before it), read the PC's neighbour entry for the board, ask the
UDP service on port 5000 for the counters, and send a datagram to 239.63.0.1:5000 before and after the board joins that
group.

Expected result: 5 of 5 pings answered, the neighbour entry shows 02:00:00:00:00:63, the UDP reply starts with "N63D"
and its counters match the frames exchanged, the multicast datagram is not answered before the join and is answered
after it, and every condition sample is inside the recommended operating conditions with no alarm latched. A pass
would show the blocks interoperating with a real host's network stack at 100 Mb/s.
