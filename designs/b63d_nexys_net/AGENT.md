# AGENT b63d_nexys_net (fda-handover/1)
source: designs/b63d_nexys_net/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b63d_nexys_net

## identity
kind=demonstration produced_by=agent part=xc7a100tcsg324-1 board=Nexys A7-100T top=b63d_nexys_net_top tool=Vivado 2026.1

## summary
Answers ARP and ping, receives and sends UDP, joins IGMP multicast groups and counts frames on the Nexys A7's 10/100 Ethernet PHY (LAN8720A, RMII). A UDP service on port 5000 replies with the tag N63D and 21 statistics counters. A frame injector and capture let the host check the stack through the PHY's loopback with no cable. Built and simulated; it has not been run on a board.
not: a gigabit design; the RGMII MAC in ip_lib cannot run on this board, whose PHY is RMII; a board-verified design; no board run exists

## state
stage=built vivado=2026.1 kb_pin=1fc7ed8 build_id=5d855695
gates: build_2026_1=pass board_run=not-run

## interface
clk CLK100MHZ 100MHz
rst CPU_RESETN active-low: the reset button; the PHY has its own reset (ETH_RSTN), held low by CTRL bit 3
if UART register window test shell, 8N1 UART at 115200 baud (CLKS_PER_BIT 434 at 50 MHz): control, own MAC and IP, MDIO, IGMP groups, 21 statistics counters, event counters, XADC codes and latched alarms, frame injector and capture; the map is in the header of rtl/b63d_nexys_net_top.sv; unlisted offsets read 0 doc=shell/PROTOCOL.md
if RMII PHY LAN8720A on ETH_CRSDV, ETH_RXERR, ETH_RXD[1:0], ETH_TXEN, ETH_TXD[1:0], ETH_REFCLK, MDC and MDIO (LVCMOS33): REF_CLK-in mode, 10/100 only; pin timing is constrained against the forwarded eth_refclk with the RMII rev 1.2 figures doc=designs/b63d_nexys_net/host/PLAN.md
if UDP statistics service UDP, port 5000 (UDP_PORT register, reset 5000): any good datagram is answered with N63D and the counters, big-endian, to the sender's address and port; on an ARP cache miss it sends an ARP request and drops the datagram, so the sender must retry doc=designs/b63d_nexys_net/rtl/b63d_nexys_net_top.sv
if LEDs LED[3:0] (LVCMOS33): LED0 heartbeat, LED1 receive activity, LED2 transmit activity, LED3 on once any echo reply has been sent
param own MAC=02:00:00:00:00:63 legal=any; registers MAC_HI and MAC_LO
param own IPv4=192.168.63.2 legal=any; register IP
param IGMP groups=239.63.0.1 and 239.63.0.2 legal=registers GROUP0, GROUP1; enabled by GROUP_EN, reset 0
param CLKS_PER_BIT=434 legal=positive integer

## files
designs/b63d_nexys_net/rtl/b63d_nexys_net_top.sv a980785544: top; register map in its header
designs/b63d_nexys_net/design.xdc 82fd75943a: pins, clocks and the RMII timing constraints
designs/b63d_nexys_net/build.yaml ab1aff8c91: sources, and the RMII io_interfaces checked by the flow
designs/b63d_nexys_net/tests/test_b63d_nexys_net_rtl.py 60427e5970: simulation through the shell against the library models
designs/b63d_nexys_net/host/board_run.py 2dfebc9062: board run script (loopback and link phases) with the isolation checks
designs/b63d_nexys_net/host/PLAN.md cebc366a8d: board-run plan and expected results

## commands
simulate through the shell, check the I/O constraints and the host safety checks (~3min): python3 -m pytest -q designs/b63d_nexys_net/tests
[heavy] build the design (~5min): flow/run_vivado.sh designs/b63d_nexys_net base
board run phase 1, PHY loopback, no cable: python3 designs/b63d_nexys_net/host/board_run.py --port <shell UART> --phase loopback --out board_loopback.json

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b63d_nexys_net/tests/test_b63d_nexys_net_rtl.py 60427e5970
R2 designs/b63d_nexys_net/tests/test_b63d_host_safety.py a7a4d91805
R3 results/b63d/nexys_build/b63d_nexys_net_base.json 0e12f4f40d
R4 results/b63d/faults.json 3d7e1c4f74
R5 results/b63d/formal.json 3c1e137a05

## evidence
E1 simulation pass R1 ci: cocotb through the shell; frames sent by the design equal the library models, counters read back
E2 simulation pass R2 ci: host-side network safety checks against stand-in command outputs; no traffic is sent
E3 build pass R3: whole-board build on Vivado 2026.1; every gate passes at 50 MHz, including the I/O timing against the forwarded clock
E4 faults pass R4: seeded faults in the library blocks and the MAC this design uses, each caught by its bench
E5 formal pass R5: SymbiYosys jobs on the library blocks (one k-induction proof, the rest bounded)

## measured
M1 resources lut=4188 LUT R3#gates.utilization.lut: LUTs, whole board design | routed whole-board build, Vivado 2026.1, including the test shell
M2 resources ff=4344 FF R3#gates.utilization.ff: flip-flops, whole board design | as M1
M3 resources bram_tile=2 tiles R3#gates.utilization.bram_tile: block RAM tiles, whole board design | ditto
M4 timing wns_ns=1.569 ns R3#gates.timing.wns_ns: worst setup slack | routed, 50 MHz logic clock
M5 timing whs_ns=0.035 ns R3#gates.timing.whs_ns: worst hold slack | routed, 50 MHz logic clock; an internal path in arp_responder
M6 timing rmii_setup_ns=1.569 ns R3#gates.stages.post_route.io_timing.worst.setup.slack: worst RMII setup slack at the pins | ETH_RXERR into the logic clock, measured from the forwarded eth_refclk with the RMII rev 1.2 figures, slow corner
M7 power power_w=0.251 W R3#gates.power.total_w: total on-chip power estimate | report_power after routing, vectorless, confidence Low
M8 verification -=56 faults R4#caught: seeded faults caught | of 56, in the library blocks and MAC

## gaps
[board_run] No board run exists. The PHY loopback phase needs no cable but must not start with a cable in J4. The link phase needs one cable from J4 to an isolated PC interface at 192.168.63.1/24, and the owner's confirmation of the cabling (host/PLAN.md). Everything about the PHY, the pin timing in practice and the stack against a real host is unobserved.
[latency] Not measured on the design. The block benches declare latencies (ARP 3, ICMP 4, UDP transmit 4 clocks) but no record times the design end to end.
[throughput] Not measured; the design counts frames, and no record gives a frame rate or a bit rate.
[timing] The pin timing uses RMII rev 1.2 figures (output change 2 to 14 ns after the clock, input setup 4 ns and hold 2 ns), not the LAN8720A data sheet's REF_CLK-in table, which is not in the knowledge bank and must be checked before the board run. Board traces are ignored. The forwarded clock phase (335.25 degrees) was chosen from the tool's timing, not from a measurement.
[power] Power is vectorless with confidence Low, and the junction temperature in the build record is a prediction; no XADC reading exists.
[E2] The host safety checks use stand-in command outputs; the script cannot see past the cable, so a quiet network on the far side is not detected and the cabling still needs confirming by a person.
[E4] The faults and formal records cover the library blocks the design uses, not this top. Only the MDIO frame is proved (k-induction); the other jobs are bounded model checks to 12 to 64 clocks, and the ICMP property checks one copied byte, not every byte.
[library] No half duplex, no PFC, one VLAN tag, ARP entries do not age, one ICMP or UDP-transmit frame held at a time, IGMPv3 reports not implemented, UDP receive has no reassembly. The 125 MHz target of the RGMII MAC is not met by several blocks, but this design runs at 50 MHz.
[behaviour] A UDP datagram to the service on an ARP cache miss is dropped and an ARP request goes out, so the first datagram after boot is unanswered; IGMP reports start only after GROUP_EN is set (reset 0); the idle board sends nothing unsolicited; event counters are 16 bits and wrap; offsets of the register window not in the map read 0.

## next_actions
1. Check the LAN8720A REF_CLK-in input timing against its data sheet, and cite it in build.yaml and design.xdc.
2. With the owner's cabling confirmation, run phase 1 (loopback) and then phase 2 (isolated link) and add the records under results/.
3. Pipeline ipv4_udp_rx, ipv4_udp_tx, igmp_join and icmp_echo toward 125 MHz before they sit behind an RGMII MAC on another board.

## open_questions
- Does the LAN8720A accept the REF_CLK phase chosen from tool timing, with real board traces?

## history
2026-11-12 63D pr=-: library network blocks and the Nexys A7 design simulated through the shell and built on Vivado 2026.1; not run on a board
2026-11-13 63D pr=-: review rounds fixed the RMII timing reference, the host isolation checks and the seeded-fault coverage
2026-11-13 68 pr=-: handover written to the documentation standard
