# b63d_nexys_net: host side (not yet run on the board)

`board_run.py` drives the board run from the PC. It reads the operating conditions (the XADC's temperature and supply
voltages, and the alarms the design latches between reads) at the start, between steps and at the end. The loopback
phase checks the PHY over MDIO and the stack with the PHY looping frames back. The link phase first checks that the PC
interface is isolated (no default route, only 192.168.63.1/24, nothing but the board answering), binds every socket to
that interface (it also refuses a stacked or enslaved interface, any route but the subnet, a global IPv6 address and a board address answered by another MAC; it cannot see past the cable), then pings the board, reads its ARP entry, asks the UDP service for the counters and checks the
multicast filter. The plan and what each phase is expected to show are in `PLAN.md`.
