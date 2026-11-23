# AGENT b196_secure_demo (fda-handover/1)
source: designs/b196_secure_demo/handover.yaml; human view: README.md; refresh: python -m flow.handover fresh designs/b196_secure_demo

## identity
kind=demonstration produced_by=human part=xck26-sfvc784-2LV-c board=kr260 top=b196_top tool=Vivado 2026.1

## summary
A 25 MHz design for the Kria KR260 part that runs the brief-194 stream core and drives two LEDs, with a SYSMONE4 whose alarm thresholds come from the board's operating limits and feed a latched safe shutdown. It is built with the production_secure switch on, and the same design with one ILA added is built to show the check failing. Built only; never programmed and never on a board.
not: a held-out or benchmark task; it was written to demonstrate and measure the production_secure check; a statement that the part is secure against an attacker; nothing was measured against one and no certification or side-channel claim is made; a board design; it was never programmed and no hardware measurement exists; bitstream encryption or authentication, which on a Zynq MPSoC are boot-image steps that belong to the owner

## state
stage=built vivado=2026.1 kb_pin=5e2eab8 build_id=32f26e59
gates: security_profile_met=pass

## interface
clk clk_25 25MHz
rst por active-low: a 32-clock power-on counter from the configuration's register values; there is no reset pin; used synchronously everywhere
if led two user LEDs, LVCMOS18: led 0 follows the parity of the core's running checksum, led 1 lights on any core fault flag; both are driven low in the safe state doc=designs/b196_secure_demo/rtl/b196_top.sv
param ECC=1 legal=0 to 2 in the brief-194 core
param SAFE=1 legal=0 or 1

## files
designs/b196_secure_demo/rtl/b196_top.sv a5bba950b4: the top, the stream source, the core and the LEDs
designs/b196_secure_demo/rtl/b196_sysmon_guard.sv 66c9b9c679: SYSMONE4 with its INIT attributes and the latched shutdown behind it
designs/b196_secure_demo/rtl/b196_shutdown.sv 255676dc36: the latch that holds the design in reset after any alarm
designs/b196_secure_demo/rtl/b196_sysmon_pkg.sv 2188c6edcf: the SYSMONE4 INIT values, generated from the board file by flow.security
designs/b196_secure_demo/design.xdc 9286232be0: pins, clock and LED output delays
designs/b196_secure_demo/build.yaml 32fbdd54d4: the production build (the security request comes from the run's pin)
designs/b196_secure_demo/dbg/build.yaml da7bab7cf0: the debug build, the same design plus one ILA
designs/b196_secure_demo/tb/tb_shutdown.sv aacde628c5: bench of the safe shutdown in the top
designs/b196_secure_demo/tests/run_sysmon_sim.py 0c549936ec: the SYSMONE4 simulation model driven with readings inside and outside the limits

## commands
the safe-shutdown bench and the generated-package check under Icarus (~1min): python3 -m pytest -q designs/b196_secure_demo/tests/test_b196_rtl.py
sixteen readings through the SYSMONE4 simulation model (~5min): python3 designs/b196_secure_demo/tests/run_sysmon_sim.py --out results/b196/sysmon_sim.json
[heavy] the production build and the debug build (~15min): FDA_SECURITY='{"production_secure": true}' flow/run_vivado.sh designs/b196_secure_demo base; FDA_SECURITY='{"production_secure": true}' flow/run_vivado.sh designs/b196_secure_demo/dbg base

## records (path sha256-prefix; claims below cite R<n>)
R1 designs/b196_secure_demo/tests/test_b196_rtl.py 9dcfc8410a
R2 results/b196/sysmon_sim.json 2dd7ab3777
R3 results/b196/demo_builds.json 2d69e4fc63

## evidence
E1 simulation pass R1: one alarm clock latches the shutdown, holds the core in reset, drives the LEDs low and stays latched
E2 simulation pass R2: the Vivado simulation model of the system monitor, configured by the generated INIT values, raises the right alarm for each of sixteen readings
E3 build pass R3: the production_secure build of Vivado 2026.1 reads back the readback and JTAG settings, finds no debug core and the system monitor wired to the latch
E4 build fail R3: the same design with one ILA fails the strip_debug gate, as it must

## measured
M1 resources lut=334 LUT R3#builds.secure.utilization.lut: LUTs of the production_secure build | routed, Vivado 2026.1, xck26-sfvc784-2LV-c, 25 MHz clock, one run
M2 resources ff=287 FF R3#builds.secure.utilization.ff: flip-flops of the production_secure build | ditto
M3 timing wns_ns=33.254 ns R3#builds.secure.wns_ns: worst setup slack of the production_secure build | routed, clk_25 at a 40 ns period
M4 cost -=1357 LUT R3#builds.debug.utilization.lut: LUTs of the debug build (the production design plus one ILA and its debug hub) | routed, Vivado 2026.1, one run, one thread
M5 cost -=263.4 s R3#builds.secure.wall_s: wall time of the production_secure build | one run, two threads, this PC; the plain build of the same design took the same to the tenth of a second, so the switch costs no build time that this run could see

## security
production_secure=yes
on readback security Level1, JTAG access to the system monitor disabled, BSCAN access after configuration disabled: the three BITSTREAM properties are set before write_bitstream and read back from the design after it (gate security_readback_off), and the write_bitstream verbose log prints them
on no debug core, hub, bridge, BSCAN primitive, marked debug net, debug-class port or probe file: the inventory of the implemented design lists none of them (gate security_strip_debug); the debug build of the same design lists two cores, a BSCAN primitive and sixteen marked nets and fails it
on system-monitor alarm thresholds from the board's operating limits, wired to a latched safe shutdown: the SYSMONE4 attributes in the implemented design equal the values recomputed from boards/kr260/board.yaml, and each alarm output reaches the shutdown register (gate security_sysmon_shutdown)
off bitstream encryption and authentication: on a Zynq MPSoC they are boot-image steps; Vivado 2026.1 makes the encryption and authentication properties read-only for this part, so the record lists them as handed to the owner
off the user over-temperature limit and the automatic device shutdown: setting the limit also enables the automatic shutdown that de-configures the part, so the device keeps its default limit and the shutdown is a latch in the fabric
off a JTAG disable by eFUSE and any key programming: irreversible and the owner's; this design never programs anything
wrong? a passed gate shows that Vivado's output carries the setting, not that the part resists an attacker
wrong? the alarm thresholds were checked in the vendor simulation model, not on silicon, and the model uses another temperature transfer function than the data sheet
wrong? the limits are the 0.72 volt rows of the data sheet, because the K26 grade is not named there
wrong? with JTAG access to the system monitor disabled a reconfiguration over JTAG needs a power cycle first
wrong? the latch holds until power or a new configuration clears it, by design
keys: the flow never makes, reads, stores or programs a key; there is no key in this design; key files are git-ignored and never recorded; eFUSE and BBRAM are the owner's.

## gaps
[power] Not measured here; no power report was recorded for the production build.
[throughput] Not applicable beyond the brief-194 core; the design moves 16 words every 65536 clocks.
[latency] Not measured; the design has no latency requirement.
[board] Never programmed and never on a board; every statement about behaviour on the part is from Vivado's reports or its simulation model.
[E4] Evidence E4 is a build that fails its gate on purpose; the failure is the expected result.
[threshold] The temperature thresholds follow the data-sheet transfer function that this repository read back on the owner's board; the vendor model uses another one, about one degree apart at 85 degrees.
[bitstream] The bitstreams of the plain and the production build differ; the differing configuration words were not decoded for this family.
[spread] Resources and times are one run each; the spread between runs is unknown.

## next_actions
1. Run the debug build and the production build on a fresh Vivado release when the pin changes.
2. Decode the configuration-register difference between the plain and the production bitstream.
3. Give the owner the boot-image steps for encryption and authentication when a board run is planned.

## open_questions
- Whether the K26 grade has its own limits table that replaces the 0.72 volt rows.

## history
2026-11-23 196 pr=-: written with the production_secure measurements
