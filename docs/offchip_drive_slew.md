# DRIVE, SLEW and series resistance on a 50 ohm line, with the KR260 carrier's own board data

Brief 162, 2026-11-22. Follows brief 155 ([docs/offchip_io.md](offchip_io.md)) and owner decision 29 (the signal-integrity design rules). Everything here is a **model result on AMD's
preliminary IBIS data, checked against a second simulator, not a scope measurement**. The numbers are in [results/162_kr260_si/README.md](../results/162_kr260_si/README.md)
and the CSV files beside it.

## 1. How to choose DRIVE and SLEW for a load (the answer first)

1. **Is the line electrically short?** If the round trip is under about a sixth of the edge time, the wire is just a capacitor and the defaults are fine (owner decision 29a).
   For a 1 ns edge that is about half an inch on FR-4. At 1 inch most DRIVE and SLEW combinations of every standard here pass with 22 ohm; the long case below is the one that needs thought.
2. **Otherwise it is a transmission line. Make the total source resistance, DRIVE's output resistance plus the series resistor, about the line impedance.** DRIVE does not
   set that resistance by itself (see section 2); the series resistor is the part you can choose.
3. **Read the pass table (section 4) for your standard and length**, pick a DRIVE with a series value that passes at all three IBIS corners, then pick SLEW for the edge you need.
4. **Never lean on clamp diodes** (decision 29d), and judge against the data sheet's limits (29e): the check used VCCO + 0.2 V and GND - 0.2 V (DS181 Table 2, DS925) as the recommended
   limit and the data sheet's duration tables above it.

## 2. What DRIVE and SLEW are, in plain words

- **DRIVE is a current rating, and through it the output resistance.** An LVCMOS output is a pair of transistors. DRIVE chooses how many of the output transistor's fingers
  are used, so it sets the **DC current** the pad can source or sink into a load at a valid logic level. A bigger DRIVE is more fingers in parallel, so a lower on-resistance, but
  the transistor is a current-limited source, not a resistor: the resistance depends on how far down its curve the load pulls it. Measured from AMD's curves (brief 155), 7-series HR
  LVCMOS33 launches into 50 ohm as 96 / 102 ohm (pull-up / pull-down) at 4 mA, 41 / 41 at 8, 22 / 17 at 12 and 15 / 13 at 16, with a 2 : 1 spread over the IBIS corners.
- **SLEW sequences the turn-on.** The pre-driver turns the output fingers on in a staggered order (SLOW) or all together (FAST). SLOW makes the current rise more gradually,
  so the edge is slower and the current step, and so the ground bounce and the overshoot it excites, are smaller. SLEW does not change the DC strength. It changes
  the edge by a lot, and by different amounts at different DRIVE: 7-series HR LVCMOS33 SLOW rises in 2.29 ns at 4 mA, 3.15 ns at 8 mA, 1.45 ns at 12 mA and 0.60 ns at 16 mA
  (IBIS 20-80 %, typical corner, brief 155), so SLOW at 16 mA is as fast as FAST at 4 mA.
- **The two interact on a line.** The edge time decides whether the wire behaves as a line at all; DRIVE with the series resistor decides how much of the first wave and how much
  reflection there is. A fast edge on a long line with too little source resistance overshoots, undershoots and rings; too much source resistance and the first wave
  is too small to cross the receiver threshold, so the receiver waits for the reflection (a staircase).

## 3. Why this is a simulator question, and the second simulator

The sweeps use brief 155's solver on AMD's IBIS curves. To check the solver, `tools/offchip_ngspice.py` rebuilds each case in **ngspice** (BSD-3-Clause, version 47, built user-local from
the release tarball): the same IBIS tables and the same calibrated switching ramp become a behavioural current source on the pad, with a lossless T element for the line. **No IBIS-to-SPICE
route was used**: none is installed here, and an IBIS pull-up/pull-down table is only the DC half of a model, so the two simulators share the driver data and differ in method.

Result (48 cases: 6 LVCMOS33/25 7-series HR and 2 UltraScale+ HP LVCMOS18 configurations, 3 corners, rising and falling edges):

- **With a series resistor (22 and 33 ohm, 24 cases): the two agree**: receiver-waveform differences at most 0.031 V (rms at most 4 mV), peak and trough within 3.5 mV.
- **Rising edge with no series resistor (12 cases):** at most 0.060 V (peak within 36 mV).
- **Falling edge with no series resistor (12 cases): they disagree**: up to 0.59 V in the waveform and 0.56 V in the ringback peak, ngspice higher. I did not find the cause. ngspice's receiver
  voltage already oscillates by about 0.2 V before the edge in the worst case, which points at its start-up (operating-point) handling of this netlist rather than at the solver, but I
  did not prove it. A falling edge with nothing in series is the case this page recommends against anyway; the sweep's `series_ohm = 0` falling-edge rows should be read with that doubt.
- ngspice took a long time on some of the long, fast cases and one case did not finish in 6 minutes (a transient with 15 ps steps over many line delays).

## 4. The sweep: DRIVE x SLEW x series R on a 50 ohm line, 1, 3, 6 and 10 inches, 5 pF

`results/162_kr260_si/drive_slew_sweep.csv` (868 rows: every DRIVE and SLEW of 7-series HR LVCMOS33 and LVCMOS25 and of UltraScale+ HP LVCMOS18; series 0, 10, 15, 22, 27, 33, 47 ohm; three IBIS corners
inside each row). Each row records overshoot, undershoot, first-incident margin, ringback margin, settling time, ringing, and the receiver 20-80 % time at the weak, typical and strong corners.
**Pass** = no `OFFCHIP-*` flag from brief 155's check (data-sheet overshoot and undershoot limits, first wave over the threshold at every corner, ringback, receiver edge at most a quarter of a
10 ns unit interval). Line `er_eff` 3.2.

**How many of the DRIVE and SLEW combinations pass with each series resistor** (of 8 for LVCMOS33 and LVCMOS25 on 7-series HR; of 15 for LVCMOS18 on UltraScale+ HP):

| standard | length | 0 | 10 | 15 | 22 | 27 | 33 | 47 ohm |
|---|---|---|---|---|---|---|---|---|
| LVCMOS33 | 1 in | 2 | 4 | 4 | 7 | 8 | 8 | 8 |
| LVCMOS33 | 3 in | 0 | 1 | 1 | 1 | 3 | 6 | 7 |
| LVCMOS33 | 6 in | 0 | 0 | 0 | 0 | 0 | 2 | 6 |
| LVCMOS33 | 10 in | 0 | 0 | 0 | 0 | 0 | 2 | 6 |
| LVCMOS25 | 1 in | 2 | 2 | 4 | 7 | 8 | 8 | 8 |
| LVCMOS25 | 3 in | 2 | 2 | 2 | 2 | 2 | 7 | 8 |
| LVCMOS25 | 6 in | 1 | 1 | 1 | 1 | 1 | 3 | 7 |
| LVCMOS25 | 10 in | 0 | 0 | 0 | 0 | 0 | 2 | 6 |
| LVCMOS18 HP | 1 in | 7 | 11 | 12 | 10 | 10 | 10 | 9 |
| LVCMOS18 HP | 3 in | 3 | 4 | 6 | 9 | 9 | 9 | 8 |
| LVCMOS18 HP | 6 in | 3 | 4 | 5 | 8 | 9 | 9 | 8 |
| LVCMOS18 HP | 10 in | 3 | 4 | 5 | 8 | 9 | 9 | 6 |

**22 ohm is the right default for 1.8 V HP and wrong for 3.3 V and 2.5 V HR.** On LVCMOS18 HP it passes for 8 to 9 of 15 combinations at 3 to 10 inches (the DRIVE 8 and 12 ones; 4 mA cannot drive the line
and 6 mA at 22 ohm passes only with SLOW or MEDIUM). On LVCMOS33 HR it passes for 1 of 8 at 3 inches and none at 6 or 10 inches: 33 ohm for short lines, 47 ohm for 6 inches and beyond, which
costs edge rate (weak-corner receiver 20-80 % of 1.2 ns at 12 mA with 47 ohm, against 0.85 ns with 33 ohm at 3 inches). LVCMOS25 HR sits between: 33 ohm for lines up to 3 inches, 47 ohm longer.

**The passing combination with the fastest receiver edge (weak corner), and the one with the softest, per standard and length** (full list in the CSV):

| standard | length | fastest passing | softest passing |
|---|---|---|---|
| LVCMOS33 HR | 3 in | 16 mA FAST + 47 ohm: 0.79 ns | 4 mA SLOW + 47: 3.08 ns |
| LVCMOS33 HR | 6 in | 16 mA FAST + 47: 0.79 ns | 8 mA SLOW + 47: 3.68 ns |
| LVCMOS33 HR | 10 in | 16 mA FAST + 47: 0.78 ns | 8 mA SLOW + 47: 4.25 ns |
| LVCMOS25 HR | 6 in | 16 mA FAST + 47: 0.93 ns | 4 mA SLOW + 47: 3.86 ns |
| LVCMOS18 HP | 3 in | 12 mA FAST + 22: 0.36 ns (0.17 V over, 0.13 V under) | 6 mA SLOW + 47: 1.68 ns |
| LVCMOS18 HP | 6 in | 12 mA FAST + 27: 0.41 ns (0.08 V, 0.05 V) | 6 mA SLOW + 47: 2.59 ns |
| LVCMOS18 HP | 10 in | 12 mA FAST + 27: 0.41 ns | 8 mA FAST + 47: 3.55 ns |

Read these as "what is possible", not "what to do": a design should take the softest edge its timing allows (less EMI, less ground bounce), and the SSO report of Vivado decides the rest (decision 29h).

## 5. The KR260 carrier's own board data (task 1)

**Source and method.** AMD's KR260 files (xtp756 Allegro board source, xtp743 schematic PDF, xtp757 BOM; AMD's copyright, **not committed**). The `.brd` is a binary Allegro 17.4 file; no
free tool here opens it. KiCad 10's importer source (GPL-3, `pcbnew/pcb_io/allegro/convert/`) was compiled stand-alone with shim headers and a dumper in a scratch folder outside every repository; the
owner ran it. It produced one row per net and layer (straight-segment plus arc copper length, width), via counts, the layer lists and the stack-up text. The committed result is only the derived
per-net numbers: `results/162_kr260_si/kr260_net_lengths.csv` (`tools/kr260_nets_summary.py`). The parser and the dump are not in the repository (GPL code in an MIT repository, AMD data).

**Sanity checks.** 933 nets parsed; units mils, divisor 10000; the 14-layer stack-up in the board file matches the chart (signal layers TOP, L03, L05, L10, L12, BOTTOM). The RGMII nets of one PHY agree with
each other to about 3 %: that clustering is what a length-matched routing looks like and is unlikely if the parse were wrong.

**Stack-up (from the board file's own text).** 14 layers, 64.02 mil total; TOP 1.9 mil copper plated; prepreg 1080 3.21 mil between TOP and the first plane (an assumed placement: the file lists the
dielectrics out of order); 2113 / 2116 prepregs and cores 4.0, 4.77, 3.72, 2.5 mil; laminate EM-828G. The fab drawing's table 2 asks for **50 ohm single-ended: 5.2 mil on TOP, 4 mil on layers 3, 5 and 12 (tolerance
10 %)**, and a 90 ohm differential table. The file gives no Dk.

**Z0 and delay** (`tools/kr260_z0.py`, `results/162_kr260_si/z0.json`). Because no Dk is stated, Dk is the one calibrated quantity: the value for which the fab table's 5.2 mil over 3.21 mil is 50 ohm.
Hammerstad-Jensen microstrip (with a thickness correction) gives Dk 3.21 (microstrip effective permittivity 2.56, 135 ps/in); the owner's 2-D field solver `Matrix_Articles/si_models/fdm2d.py` gives 58.5 ohm
for the same Dk and needs Dk 5.1 for 50 ohm (stripline 192 ps/in). **The two solvers disagree by 17 % at the same inputs, so I do not trust Dk from this calibration to better than "between 3.2 and 5.1"**.
Taking the chart's dielectric heights for a stripline layer (4.0 + 4.77 mil) and the fab table's 4 mil / 50 ohm gives a Dk of about 3.5 and 158 to 164 ps/in. **The routed nets are mostly stripline
(layers 3, 5, 12), so the delay is 150 to 190 ps/in and the check's `er_eff` 3.2 (151 ps/in) is at the fast end of that**; Z0 is 50 ohm by the board designer's own table (10 % tolerance), not by my solver.

**Series resistors on the carrier** (xtp743 pages 20 and 21, the board file's nets, and the BOM xtp757). **None on any PL RGMII net**: each signal is one net from the SOM connector to the TI DP83867 PHY
(one net name each side, `HPA01N` and so on). The only series-type values in the BOM are 0 ohm (43), 10 (1), 20 (8, on the Pmod sheets, pages 10 and 11), 30 (7: six on the SD card sheet, page 22; one
on the 26 MHz clock sheet, page 16), 49.9 (2). No 22, 27, 33 or 47 ohm part appears in the BOM. What the K26 SOM has between the FPGA balls and its connector is not in these files.

**Lengths** (carrier copper only, SOM and package excluded; `kr260_net_lengths.csv`):

| group | nets | length | layers |
|---|---|---|---|
| PHY2 / port A, HPA0x nets (RGMII) | 18 | 7.07 to 7.34 in for the 14 RGMII-length nets (HPA04 6.6 to 7.1, HPA05 2.8 to 5.3) | L03 + L12, 3 vias (4 on HPA04) |
| PHY3 / port B, HPB0x nets | 18 | 2.34 to 2.87 in for 14 nets (HPB04 5.9 to 6.1, HPB05 0.5 to 3.9) | TOP, L03, L10, 3 vias |
| Pmod IO, SOM side (HDA / HDB) | 45 | median 0.23 in | to the series resistor |
| Pmod IO, connector side | 32 | 2.64 to 3.96 in, median 2.89 | L05 and TOP |
| FTDI UART | 2 | 1.19 to 1.22 in | |
| SFP rate select | 2 | 0.12 in | lumped |

Port A's RGMII nets are about two and a half times longer than port B's. **The Pmod nets show a series part on every line**: each has a SOM-side net (median 0.23 in) and a connector-side net (median 2.9 in), so the part sits
near the SOM end and drives 2.6 to 4 inches of line. The BOM says the parts are 0 ohm (43 on the carrier) or 20 ohm (8); I did not map which Pmod line has which.

**Receiver.** TI DP83867CS (the part on the PL Ethernet sheets): input capacitance **5 pF max** (SNLS504G, electrical characteristics, CIN). Package and pad stub not included.

**The check with real data against the assumed run** (`kr260_b58a_trigger_*.check.json`, with `--family zynquplus --part xck26-sfvc784-2LV-c --bank-type HP`; `designs/b58a_trigger/design.xdc`, DRIVE 12 FAST):

| | assumed (brief 155): 4 in, 4 pF | carrier data: port A 7.2 in, port B 2.8 in, 5 pF |
|---|---|---|
| overshoot / undershoot at the receiver, nothing in series | 1.06 V / 0.97 V on both ports, 1.35 ns of the 4 ns UI beyond 0.2 V | port A 1.06 V / 0.97 V, 2.38 ns (59 % of the UI) beyond 0.2 V; port B 1.00 V / 0.91 V, 1.04 ns (26 %) |
| proposal (DRIVE 12 FAST) | + 27 ohm, 7 passing combinations (both ports) | port A + 27 ohm, 7 passing; port B + 22 ohm, 10 passing |

So the real data changes the answer a little (port B can take 22 ohm, port A still wants 27) and confirms the finding that matters: **both ports, unterminated, exceed the data sheet's limit by about 1 V**; the peak does not
grow with length, the time spent over the limit does (a 7.2 in line rings for 59 % of a unit interval). The carrier has no series resistor on these nets, and the check's fix is one at the SOM end. In the FPGA design the alternative is a weaker
output: in the sweep DRIVE 4 mA on UltraScale+ HP LVCMOS18 passes with no resistor at 3 in (weak-corner receiver edge 0.86 ns with FAST, 1.6 ns with SLOW or MEDIUM), at the price of only 4 mA of DC drive. DRIVE 12 FAST, the XDC's choice, needs the resistor.

## 6. Series-resistor survey (decision 29b): partial

What was counted: the KR260 carrier (section 5): 8 x 20 ohm, 7 x 30 ohm, none at 22 ohm; its Ethernet has none. Digilent's schematic downloads refuse automated requests and I did not obtain a second board;
the knowledge library holds no other schematic text. **The belief "22 ohm is the commonest" is therefore neither confirmed nor refuted** by this survey. The plan for a real count: the Digilent Arty A7, Nexys A7, Zybo Z7 and
AMD KC705 / ZCU102 schematics (the owner can download them in a browser) and TI's DP83867 reference design, counting resistors in series with FPGA outputs. The section 4 result is the better evidence: the
right value depends on the standard (22 for 1.8 V, 33 to 47 for 3.3 V), so "22 everywhere" would be the wrong default.

## 7. Non-preliminary IBIS (decision 29c)

`tools/ibis_rev_compare.py` (`ibis_revision_check.csv`). The files brief 155 uses (`artix7.ibs`, `zynq.ibs`, `zynquplus.ibs`) are byte-identical in the earlier Vivado install brief 155 read and in 2026.1 (same SHA-256), and all
still say "All models are preliminary". The only newer file is Vivado 2026.1's `kintexuplus.ibs` (File Rev 2.15, 25-OCT-2025; it carries no "preliminary" note).
It is for Kintex/Artix UltraScale+, not the K26's Zynq UltraScale+, but its HP LVCMOS18 models (45 model-corner rows) have **identical** pull-up and pull-down resistance, edge times and die capacitance to `zynquplus.ibs`
(largest difference 0.0 %). **Nothing in brief 155's extraction changes.** I did not find AMD's web page listing IBIS downloads (the page needs a browser); a user-facing "non-preliminary" release outside Vivado may exist.

## 8. SSO (decision 29h)

A `report_ssn` run on `b58a_trigger` and `b63d_nexys_net` is queued in `_handoff/fpga_agent/vivado_later_queue.md` (peak 4 G). Not run: no Vivado in this brief.

## 9. Limits

- Model results on preliminary IBIS; not compared with a scope. The pad clamps are the IBIS table's, and the receiver's clamps are not modelled (conservative).
- ngspice and brief 155's solver share the driver data; agreement tests the solver, not the data. They disagree for a falling edge with no series resistor (section 3).
- The `.brd` lengths are carrier copper only. The SOM's routing and the FPGA package are missing, so the real lines are longer.
- Z0 is the fab drawing's value; Dk is calibrated from it and the two solvers disagree (section 5).
- The sweep is a 50 ohm, `er_eff` 3.2, 5 pF line; the real stripline is slower (shorter lines look electrically longer than modelled).
- Not covered: the 7-series HP banks, UltraScale+ HD LVCMOS33 (brief 155's tables have it), SSTL/DCI (calibrated outputs, decision 29g).
