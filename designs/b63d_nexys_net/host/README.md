# b63d_nexys_net: host side (not yet run on the board)

`board_run.py` drives the board run from the PC: it reads the operating conditions (XADC) at the start, during and at
the end, checks the PHY over MDIO, then, on an isolated link only, pings the board, checks its ARP reply, asks the UDP
statistics service for the counters, joins an IGMP group and checks the report, and compares every counter it reads
with what it sent. The plan and the cabling it needs are in `PLAN.md`.
