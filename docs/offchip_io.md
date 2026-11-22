# Choosing the I/O buffer for off-chip signals

Brief 155, 2026-11-22. Owner, 2026-11-21: "when signals go off chip, depending on the load, the IOB type must be chosen: logic standard, voltage, and sometimes
drive strength (eg to come closer to an impedance match with a transmission line)", and: "Some IO drivers are built for a given Z0, but where CMOS is used,
you can only approximate. It is worth researching which drive strength is best when (say) a 50 ohm line is being driven, for a given termination, such as series
termination (often around 22 ohms external)."

This page is the study, the model, the spec section and the check. The numbers are in [results/155_offchip/README.md](../results/155_offchip/README.md) (generated from
the CSV files beside it); the code is `flow/offchip_model.py` and `flow/offchip_check.py`; the tests are `flow/tests/test_155_offchip.py`. The check is **advisory**
until the owner approves it. It is not a build gate, and the model has never been compared with a scope trace (a board measurement is planned in section 11, not done).

Sources, in our own words: UG471 (7 series SelectIO) v1.10, UG571 (UltraScale SelectIO) v1.16, UG912 (properties) 2025.2, UG899 (I/O planning) 2025.2, DS181 v1.27.1,
DS187, DS925 v1.30, and AMD's IBIS output models shipped with Vivado 2025.2 (`artix7.ibs` file revision 2.8, IBIS 4.2, dated 28-AUG-2017; `zynq.ibs` revision 2.8,
27-JAN-2016; `zynquplus.ibs` revision 2.11, IBIS 5.1, 10-FEB-2022). The IBIS files carry AMD's copyright and are not committed: `tools/ibis_extract.py` reads them
from the local install and writes our own compact summary (`flow/offchip_data/driver_models.json`: the pull-up and pull-down curves sampled at 21 voltages per corner,
die capacitance, receiver thresholds and the 20-80 % edge time; 157 models).

## 1. The two kinds of output

| | Impedance-controlled | Plain LVCMOS / LVTTL |
|---|---|---|
| Which | DCI outputs and the UltraScale+ calibrated drivers: `LVDCI_*`, `HSLVDCI_*`, `SSTL*_DCI`, `HSTL*_DCI`, `POD*_DCI` with `OUTPUT_IMPEDANCE` `RDRV_40_40`, `RDRV_48_48`, `RDRV_60_60` (UG471 DCI chapter, 7 series HP banks only; UG571 for UltraScale and UltraScale+ HP banks) | `LVCMOS12/15/18/25/33`, `LVTTL`; 7-series HR and HP, UltraScale+ HP and HD |
| What sets the output resistance | a state machine calibrates it against an external reference resistor (VRP and VRN pins) and follows temperature and supply while running | the `DRIVE` setting selects how many legs of a fixed driver are on; the resistance is whatever those legs give at that process, VCCO and temperature |
| Matches Z0? | yes, by design: 40, 48 or 60 ohm | only approximately, and not the same in both directions |

**What `DRIVE` is.** UG571 describes the attribute as the load the driver can safely drive to valid logic levels, in mA. It is a current rating, not an impedance. A user
who reads "DRIVE 8" as "8 mA, so the output is weak" or "DRIVE 12 means about 50 ohm" guesses wrong in two ways: the LVCMOS output is a current-limited source, so its
effective resistance depends on how far down its V-I curve the load pulls it; and the pull-up and pull-down legs are different transistors.

**Measured (our model run on AMD's IBIS curves; tables in the results folder).** On 7-series HR, LVCMOS33, the resistance a wave sees when the driver launches into
50 ohm (the chord, voltage over current at the launch point), pull-up / pull-down, and the resistance of the same half near the rail it pulls to (0.1 V from it):

| DRIVE | launch, typical | launch, strong corner (IBIS max) | launch, weak corner (IBIS min) | near the rail, typical |
|---|---|---|---|---|
| 4 mA | 96 / 102 ohm | 79 / 76 | 123 / 146 | 34 / 25 |
| 8 mA | 41 / 41 | 30 / 26 | 59 / 68 | 25 / 14 |
| 12 mA | 22 / 17 | 17 / 12 | 32 / 32 | 15 / 10 |
| 16 mA | 15 / 13 | 12 / 9 | 20 / 22 | 13 / 9 |

(IBIS `LVCMOS33_F_{4,8,12,16}_HR`, `artix7.ibs` rev 2.8; FAST and SLOW have the same curves, SLOW only changes the edge. The weak and strong corners are the IBIS min
and max columns: slow process, 3.135 V, 85 C against fast process, 3.465 V, 0 C. The sampled curves and the numbers for every standard are in `r_out.csv`.) Four things follow:

- no DRIVE gives 50 ohm in both directions at every corner; the spread over corners is about 2 : 1 (59 to 30 ohm at 8 mA, pull-up);
- **the output is not linear**: a low DRIVE is a current limit. At 4 mA the pull-up launches as 96 ohm but is 34 ohm near the rail, a 3 : 1 change inside one edge. The first wave sees the launch
  resistance; the reflections that come back later find the driver near its rail, in its linear region, at a much lower resistance, and are damped less. A series resistor sized from the
  launch resistance alone therefore rings more than a linear model predicts (this is why 8 mA with 22 ohm fails on undershoot in the sweep although 41 + 22 looks fine);
- the pull-up and pull-down differ by up to 30 % at the typical corner (12 mA: 22 and 17 ohm), so "series R plus R_out equals Z0" holds for one direction at a time;
- the resistance falls roughly as 1 / DRIVE, but not exactly, and not the same way for each standard (7-series HR LVCMOS18 at 8 mA and 12 mA have identical IBIS curves, so
  choosing 12 instead of 8 there changes nothing; UltraScale+ HD LVCMOS33 at 8 mA is 54 / 59 ohm typical, not 41 / 41 as in HR: the same number on a different bank type is a different driver).

The impedance-controlled outputs (HP SSTL15 DCI in `zynquplus.ibs`, slope resistance at VCCO / 2): `OUT40` gives 39.8 / 40.5 ohm typical and 38.4 to 41.6 over the
three corners, `OUT48` 47.5 / 48.3 and 46.1 to 49.4, `OUT60` 58.9 / 60.0 and 57.6 to 61.2: within 4 % of the nominal value at every corner, against the 2 : 1 spread of
LVCMOS. For a line of Z0 that is 40 to 60 ohm the calibrated driver is the match and the series resistor is not needed.

## 2. Standard and VCCO

- One supply per bank. All VCCO pins of a bank connect to one rail, so every I/O in the bank shares that VCCO (UG471, I/O bank section). The standard must agree with it: an
  output standard needs its own VCCO (LVCMOS33 needs 3.3 V, LVCMOS18 1.8 V, SSTL15 1.5 V).
- Combining standards in a bank (UG471, "Rules for Combining I/O Standards in the Same Bank"): output standards combine if they need the same VCCO; input standards if they
  need the same VCCO and the same VREF; an input and an output combine if their VCCO matches; DCI standards additionally need one target resistance per bank, and a DCI
  master and slave banks share VCCO and VREF. `OFFCHIP-VCCO` checks the first and third rules when groups name their bank.
- Bank types decide what exists: LVCMOS33 and LVCMOS25 outputs exist in 7-series HR banks and in UltraScale+ HD banks, not in HP banks (UG471 Table 1-8, UG571 Tables 1-12
  and 3-2). 7-series DCI is HP only. `IN_TERM` (uncalibrated 40/50/60 ohm split termination) is HR only (UG912). On UltraScale and UltraScale+ the property is `ODT` (UG912 says
  `IN_TERM` is not used there) and `DIFF_TERM_ADV` replaces `DIFF_TERM`.
- A receiver at a lower VCCO than the driver is not protected by its clamp: the absolute maximum input voltage is VCCO + 0.55 V (DS181 Table 1 for HR; DS925 Table 1 for HP and HD),
  so a 3.3 V output into a 1.8 V receiver (limit 2.35 V) needs a level translator. `OFFCHIP-VCCO` flags it as contradicting the data sheet.
- Allowed `DRIVE` values depend on bank type (UG471 Table 1-8; UG571 Table 1-12 for UltraScale HR and HP, Table 3-2 for UltraScale+ HD): 7-series HR LVCMOS33 4/8/12/16 mA,
  LVCMOS18 4/8/12/16/24; 7-series HP LVCMOS18 2/4/6/8/12/16; UltraScale+ HP LVCMOS18 2/4/6/8/12; UltraScale+ HD LVCMOS33 4/8/12/16. Allowed `SLEW`: SLOW and FAST everywhere, plus
  MEDIUM in UltraScale+ HP banks (UG571). `OFFCHIP-DRIVE-ILLEGAL` checks these; the Vivado DRC also does, later.
- UltraScale+ HD banks are rated 250 Mb/s DDR, and 125 Mb/s at 4 mA (UG571 Table 3-2 notes 1 and 2): an HD LVCMOS interface faster than that is a bank-type choice, not a DRIVE choice.

## 3. DRIVE, SLEW and the edge

`SLEW` selects the edge rate; `DRIVE` the current. They interact, and the interaction is not what the names suggest (IBIS 20-80 % times into AMD's 50 ohm fixture, typical corner,
7-series HR LVCMOS33, rise / fall):

| DRIVE | SLOW | FAST | weak corner, SLOW rise | strong corner, FAST rise |
|---|---|---|---|---|
| 4 mA | 2.29 / 0.86 ns | 0.62 / 0.41 ns | 3.24 ns | 0.52 ns |
| 8 mA | 3.15 / 1.09 ns | 0.69 / 0.62 ns | 4.51 ns | 0.59 ns |
| 12 mA | 1.45 / 0.84 ns | 0.53 / 0.47 ns | 2.99 ns | 0.44 ns |
| 16 mA | 0.60 / 1.20 ns | 0.39 / 0.40 ns | 1.14 ns | 0.29 ns |

- SLOW is not one edge: at 16 mA the SLOW rise (0.60 ns) is faster than the SLOW rise at 4 mA (2.29 ns) and about as fast as FAST at 4 mA (0.62 ns). A user who sets DRIVE 16 SLEW SLOW to
  "be gentle" has chosen a hard, fast edge on the rising direction.
- SLOW rise and fall differ (8 mA: 3.15 and 1.09 ns): a duty-cycle and a timing asymmetry that the I/O timing numbers include and a user does not expect.
- Over the corners the edge changes by about 1.5 : 1 (weak to strong).
- Choice rule used by the check: SLOW unless the interface needs the edge (setup and hold at the receiver, or `priority: edge_rate`); then the lowest DRIVE that meets the edge. The reasons
  for SLOW are simultaneous switching noise and EMI: the current step is proportional to the edge rate, and ground bounce (the SSN that `report_ssn` estimates, UG899) grows with the number
  of outputs switching together. Not simulated here (one output only); the `report_ssn` run is queued in `_handoff/fpga_agent/vivado_later_queue.md`.

## 4. When the line is electrically long

A line behaves as a transmission line when the round trip is not short against the edge. The usual lumped rule (the owner's `si_models/tline.py`): the round trip is under a sixth
of the rise time, i.e. a critical length of v x t_r / 12. With `er_eff` 3.2 (microstrip on FR-4, about 150 ps per inch) and t_r the 0-100 % equivalent of the 20-80 % time (20-80 time / 0.6):

| 20-80 % edge | critical length (er_eff 3.2) |
|---|---|
| 0.4 ns (FAST, strong corner) | 0.37 in |
| 0.6 ns | 0.55 in |
| 1.0 ns | 0.92 in |
| 2.0 ns | 1.8 in |
| 3.0 ns (SLOW 8 mA) | 2.7 in |

A FAST edge on a few-inch board trace is therefore a transmission line, and the receiver sees reflections: the unterminated open end doubles the incident wave, and the source reflects it again.
The model's first-incident level (what a staircase would dwell at) and the "visible" flag (edge shorter than the round trip) separate the two regimes. Section 7 of the results has the
length sweep: on a 50 ohm line the overshoot of an unmatched driver saturates beyond about 6 in (the line is long against every edge), and the settling time keeps growing with length.

## 5. Termination

| Termination | What it does | Where it lives |
|---|---|---|
| none | open end: doubles the incident wave | - |
| series R at the source | R_out + R = Z0 absorbs the reflection that returns; the receiver sees one clean step | external 0402 resistor at the pad; or the driver's own R_out (DCI, `OUTPUT_IMPEDANCE`) |
| parallel to ground or VTT at the receiver | matched end: no reflection; DC current flows (V / R) | external, or on-chip `ODT` / `IN_TERM` / DCI |
| Thevenin (split) | R to VCCO and R to ground, equal to 2 Z0 each; VTT is VCCO / 2 | DCI split, `ODT RTT_48` (96 + 96), `IN_TERM UNTUNED_SPLIT_40/50/60` |
| AC (R + C) | matched at the edge, no DC current | external |
| differential | 100 ohm across the pair at the receiver | `DIFF_TERM TRUE` (7 series; LVDS_25 at VCCO 2.5 V, LVDS at 1.8 V in HP) or `DIFF_TERM_ADV TERM_100` (UltraScale+) |

On-chip input termination: 7-series DCI split termination is calibrated and HP banks only; `IN_TERM` is an uncalibrated split termination in HR banks (target Thevenin 40, 50 or 60 ohm) with no
compensation for temperature, process or voltage: DS181 gives the Thevenin resistance of `UNTUNED_SPLIT_50` as 35 to 65 ohm over process, voltage and temperature (UG912, UG471 "Uncalibrated Split Termination in High-Range I/O Banks"). UltraScale+ HP banks use calibrated DCI and ODT; HD banks have uncalibrated ODT
(`RTT_48`, a 96 ohm pull-up and 96 ohm pull-down, UG571 chapter 3). The Nexys A7's DDR2 bank is the vendor convention in use on one of our boards: the reference manual says the traces are 50 ohm
controlled single-ended, with 50 ohm internal terminations in the FPGA and on-die termination in the memory.

**Fanout and capacitive load.** Every receiver adds its pin capacitance (DS181 Table 3: die input capacitance at the pad 8 pF at most, package not included; the model uses 5 pF per receiver and stub as an illustrative default) and a stub. A
capacitive load slows the edge by about 2.2 R C (R the source resistance as seen by the load: 17 ohm and 5 pF give about 0.2 ns) and detunes the match. A multi-drop line (one driver, several receivers) is not
modelled: the sum of the pin capacitances goes in `load.c_pf`, which is right only when the stubs are short against the edge.

## 6. The best DRIVE and series resistor on a 50 ohm line

Setup of the study (all in the results folder): Z0 50 ohm, 10 in of lossless line (1.52 ns one way, er_eff 3.2), 5 pF at the receiver, the IBIS thresholds, no clamp. Every DRIVE and SLEW the bank allows, every E-series resistor from 0 to 47 ohm, three corners, both directions. A combination **passes** when the receiver stays within VCCO + 0.2 V and GND - 0.2 V (the recommended limit), does not ring back through VIH/VIL, has at least 0.10 V of first-incident-wave margin at every corner, and has a weak-corner 20-80 % time of at most a quarter of a 10 ns unit interval.

**The answer, with the reason.** Pick the series resistor so that R_out + R_series is about Z0 *at the strong corner*, accept that it is higher at the weak corner, and make the external resistor the larger share of the total. The reasons:

- The two failure directions are not symmetrical. A total below Z0 overshoots (an open receiver doubles a wave that is larger than half the swing); a total above Z0 only slows the first step, and fails only when the first incident wave stops reaching VIH (rising) or VIL (falling). So the window is one-sided: strong-corner total at or just above Z0, weak-corner total up to roughly 1.5 Z0. In the sweep a strong-corner total (the smaller of the pull-up and pull-down totals) of 44 ohm or less overshoots, and the passing combinations start at 42 to 43 ohm on 1.8 V, 45 ohm on 2.5 V and 49 to 50 ohm on 3.3 V (the ranges overlap a little at 1.8 V because the result also depends on the corner's supply and edge). The weak-corner totals of the passing ones are at most 69 to 78 ohm.
- The 3.3 V falling edge limits first: VIL is 0.8 V, only 24 % of VCCO from ground, while VIH is 39 % of VCCO from VCCO, so a weak-corner total above about 80 ohm leaves the first falling wave above VIL.
- A bigger series resistor shrinks the corner spread because it is a 1 % part: LVCMOS33 16 mA with 47 ohm has a total of 55 to 64 ohm over all corners and both directions (spread 1.16 : 1), where 8 mA with 33 ohm has 49 to 73 ohm (1.5 : 1) and 8 mA alone 26 to 68 ohm (2.6 : 1).
- Use the resistance near the rail for the strong corner: later reflections meet the driver in its linear region (section 1), so a resistor sized from the launch resistance alone is too small. This is why 22 ohm fails on LVCMOS33.

**What passes (50 ohm, results section 6).** The first choice by the smallest worst-corner mismatch, then the fastest and the gentlest passing choice:

| Standard (bank) | Passing | Smallest mismatch | Fastest receiver edge | Gentlest edge |
|---|---|---|---|---|
| LVCMOS33 (7-series HR) | 4 of 56 | 16 mA + 47 ohm (SLOW 0.58 / 1.24 ns strong / weak, FAST 0.50 / 0.78 ns) | 16 mA FAST + 47 | 8 mA FAST + 33 (0.70 / 1.52 ns) |
| LVCMOS25 (7-series HR) | 8 of 56 | 16 mA FAST + 47 | 16 mA FAST + 47 | 12 mA SLOW + 47 |
| LVCMOS18 (7-series HR) | 10 of 70 | 16 mA + 33 | 24 mA FAST + 47 | 8 mA SLOW + 33 |
| LVCMOS33 (UltraScale+ HD) | 4 of 56 | 16 mA FAST + 47 | 12 mA FAST + 33 | 16 mA SLOW + 47 |
| LVCMOS18 (UltraScale+ HP) | 30 of 105 | 12 mA SLOW + 22 ohm | 12 mA FAST + 27 | 12 mA MEDIUM + 47 |

- **The common 22 ohm part** is right for the 1.8 V UltraScale+ HP outputs (12 mA SLOW or MEDIUM, 8 mA, or 6 mA, with 22 ohm all pass) and **wrong for 3.3 V**: on 7-series HR LVCMOS33 no DRIVE passes with 22 ohm (the receiver goes 0.07 V (4 mA), 0.42 V (8 mA), 0.75 V (12 mA) and 0.86 V (16 mA) beyond the rail; 4 mA also fails the first wave). With a 22 ohm part already on a 3.3 V board the model asks for no change of DRIVE: it says the resistor is too small and wants 33 ohm (8 mA FAST) or 47 ohm (16 mA).
- **Pull-up against pull-down.** The asymmetry is accepted: the pass criteria are applied to both directions, and the worst direction decides. On LVCMOS33 it is the falling edge (undershoot and the VIL margin).
- **The lowest DRIVE (4 mA; 2 mA in HP banks) never passes** a 50 ohm line in this sweep: the first wave fails (LVCMOS33: launch resistance 96 ohm, first-incident margin -0.72 V with no resistor) or, on 1.8 V HR, the weak-corner edge is too slow. A low DRIVE is a good choice for lumped loads and a bad one for transmission lines.
- **Other terminations (3.3 V, FAST, results section 3).** 50 ohm to ground at the receiver fails the first wave for 4, 8 and 12 mA, because the driver and the termination form a DC divider; 50 ohm to VCCO/2 or Thevenin 100/100 pass from 8 mA with +0.23 V margin but burn static current (about VCCO/100 ohm = 33 mA per pin for 100/100, arithmetic not a model output); AC (50 ohm + 100 pF) leaves 0.19 V (12 mA) and 0.50 V (16 mA) of overshoot. A series resistor is the only termination that costs no static current and passes.
- **Sensitivity to corners.** A typical-corner design is not safe: of the 294 combinations of DRIVE, SLEW and no or one series resistor in the matrix, 184 stay within 0.2 V of the rails at the typical corner, and 25 of those exceed it at the weak or strong corner (8 mA FAST + 22 ohm on LVCMOS33: typical totals 52 and 48 ohm, which looks matched; strong corner 46 and 39 ohm and 0.42 V of undershoot). Design to the strong corner for overshoot and to the weak corner for the first wave.
- **Line length.** The overshoot of an unmatched driver saturates beyond about 6 in (the line is longer than every edge); the settling time keeps growing. A matched choice (8 mA FAST + 33 ohm) stays within 0.05 V at every length from 1 to 15 in. At 1 in a FAST edge is still a lumped load (the "staircase visible" column of the length sweep is false), which is why short stubs do not need the resistor and long ones do.
- **Impedance-controlled outputs.** The DCI outputs (section 1) are the choice when the line is 40 to 60 ohm and a calibration resistor and the extra pins are acceptable: no series resistor, no corner spread (4 %). LVCMOS plus a resistor costs no pins but needs the resistor tuned to the standard, as above. The two were not compared in the time domain.

The sweep is for one line (10 in, 5 pF) and one set of limits; results section 7 (length) and the check's parameters (`line`, `load`, `ui_ns`, `max_rise_ns`) say how the answer moves.

## 7. The spec section: `off_chip:`

One entry per port group. A group is a set of ports with the same driver choice, line and receiver.

```yaml
off_chip:
  - name: rgmii_a_tx
    ports: [a_txd[*], a_tx_ctl, a_txc]    # names or globs
    direction: output                     # output | input | inout
    iostandard: LVCMOS18
    vcco: 1.8                             # the bank supply (V); defaults to the standard's
    bank: 66                              # optional: groups naming the same bank must agree on VCCO
    bank_type: HP                         # HR | HP | HD (defaults from the board)
    line: {z0_ohm: 50, length_in: 3.0}    # or  line: short   (a lumped load)
    load: {c_pf: 5.0, receiver_std: LVCMOS18, vil_v: 0.63, vih_v: 1.17}
    external: {series_ohm: 22}            # parts already on the board: series_ohm, parallel_gnd_ohm, thevenin_ohm, ac_ohm
    priority: edge_rate                   # edge_rate | emi | balanced
    ui_ns: 8.0                            # unit interval, for the overshoot-duration limit (default 10 ns, assumed)
```

`agent/graph/spec_schema.validate` rejects unknown keys, a missing `load.c_pf` on an output, a non-positive length, a bad priority and duplicate names (`flow/offchip_check.off_chip_errors`).
What a user could guess wrong:

- `line: short` means "a lumped load": the model uses a 0.3 in line and the first-incident test does not apply. It does not mean "no capacitance": `load.c_pf` is still the load.
- `load.c_pf` is the capacitance at the receiver pin and its stub, not the whole trace (the trace is the line). A multi-drop net sums its pin capacitances there, which is right only for short stubs.
- `external.series_ohm` fixes the series resistor: the proposal then chooses only DRIVE and SLEW. Leave it out and the proposal may add one (it never adds a termination at the receiver).
- A missing `DRIVE` or `SLEW` in the XDC is read as the tool default (12 mA, SLOW; UG471 and UG571 both say so). We have not yet read the default back from Vivado: the run is queued (the measure-the-vendor-first rule), so a different measured default would change those findings.
- The recommended receiver limit is VCCO + 0.2 V and GND - 0.2 V (DS181 Table 2, DS925 Table 2); the duration tables (DS181 Table 4 for HR banks, DS925 Table 6 for HD and Table 7 for HP) allow more for a share of the unit interval. The check uses the tables, so a peak between 0.2 V and the table's first row only warns (`advisory`), and a peak the table does not allow for that share of the UI is `contradicts-model`.
- Overshoot is computed without the receiver's clamp diodes. A real receiver clamps (at most 10 mA per pin, DS181 Table 2 note 8, 200 mA per bank, DS181 Table 4 note 1), which limits the peak and puts the energy in the supply. The unclamped figure is the safe reading, not the measured one.

## 8. The check and the proposal rule

`python3 flow/offchip_check.py --spec spec.yaml --xdc design.xdc --family artix7 --bank-type HR [--propose]`. Every finding is advisory; `contradicts-model` marks an XDC value that the model says breaks a data-sheet limit, with the model's numbers and the driver's source (IBIS file, revision, model name) in the finding.

| Code | Raised when |
|---|---|
| `OFFCHIP-OVERSHOOT` | the receiver goes above VCCO + 0.2 V or below GND - 0.2 V at any IBIS corner; `contradicts-model` when it exceeds the duration table |
| `OFFCHIP-FIRST-WAVE` | on a line whose round trip exceeds the edge, the first incident wave misses VIH (rising) or VIL (falling) at some corner |
| `OFFCHIP-RINGBACK` | the edge crosses the threshold and rings back through it |
| `OFFCHIP-DRIVE-MATCH` | R_out + R_series is more than 50 % from Z0 at the typical corner on a long line |
| `OFFCHIP-NO-TERM` | an unterminated long line whose ringing exceeds VCCO / 4 |
| `OFFCHIP-VCCO` | standard against group VCCO, against another group of the bank, against the receiver (absolute maximum), or the standard does not exist in that bank type |
| `OFFCHIP-DRIVE-ILLEGAL` | a DRIVE or SLEW the bank type does not allow |
| `OFFCHIP-NO-LOAD-DATA` | an XDC port that sets DRIVE or SLEW and no group names it |
| `OFFCHIP-DIFF-TERM` | a differential input with neither the family's termination property nor a declared external one |

**The proposal.** For one output group, among the allowed DRIVE and SLEW values and the E-series resistors 0, 10, 15, 22, 27, 33 and 47 ohm (or the one the spec fixes): shortlist by the
static match (the largest relative distance of R_out + R_series from Z0 over corners and both directions), simulate the best fourteen at all three corners, keep the combinations with no flag and a
non-negative first-incident margin, and rank by priority: `edge_rate` the fastest receiver edge, `emi` the slowest edge, `balanced` the smallest mismatch; ties go to no resistor, then the lower DRIVE.

**Reading the rule (what it proposes).**

- *With a fixed series resistor on the board* (`external: {series_ohm: 22}`), 50 ohm line, 10 in, 5 pF (`proposals_fixed_series.json`):
  - 7-series HR **LVCMOS33 + 22 ohm: no DRIVE passes.** The proposal is empty and says why; with 33 ohm it proposes DRIVE 8 SLEW FAST, with 47 ohm DRIVE 16 SLEW SLOW (DRIVE 16 FAST and 12 FAST also pass);
  - 7-series HR LVCMOS25: none at 22 ohm; 33 ohm DRIVE 8 SLOW; 47 ohm DRIVE 16 FAST;
  - 7-series HR LVCMOS18: none at 22 ohm; 33 ohm DRIVE 16 SLOW; 47 ohm DRIVE 24 SLOW;
  - UltraScale+ HD LVCMOS33: none at 22 ohm; 33 ohm DRIVE 12 SLOW; 47 ohm DRIVE 16 FAST;
  - UltraScale+ HP **LVCMOS18 + 22 ohm: DRIVE 12, SLEW SLOW** (first-incident margin +0.54 V, worst overshoot 0.16 V); MEDIUM, FAST and DRIVE 8 and 6 also work with 22 ohm.
- *Lumped loads* (`line: short`): there is no line to match, so no series resistor is offered; the proposal is the gentlest passing output (SLOW, the lowest DRIVE at or above `min_drive_ma`).
- *No allowed combination passes*: the proposal is empty and the reason says to terminate the line, shorten it or change the standard.

## 9. Measured on our boards

`tools/offchip_board_report.py` runs the check on our designs (`results/155_offchip/boards_report.json`; the groups and their loads are in `results/155_offchip/boards/*.spec.yaml`). No board XDC was changed; the differences below are proposals.

**What the master XDCs set.** None of the three boards' master XDCs sets `DRIVE`, `SLEW`, `IN_TERM`, `ODT` or `DIFF_TERM` (Nexys A7 master: 161 port lines, all with `IOSTANDARD` only, LVCMOS33 except two LVCMOS18; the KR260 and ZedBoard files are our own listings of pin facts, 39 and 54 lines, standard only). So a design that does not set them gets the tool default, 12 mA and SLOW (UG471; UG571). The only places a `DRIVE` or `SLEW` value is chosen are the design XDCs: six of them (`b56a_gth_serdes`, `b58a_trigger`, `b96_kr260_10g`, `b102_managed_ext`, `b102_managed_fcs`, `b102_managed_pr`). The Nexys A7's DDR2 bank is the vendor convention in use on one board: the reference manual says 50 ohm controlled single-ended traces with 50 ohm internal terminations in the FPGA (the memory controller IP sets that, not the master XDC).

| Design (board) | Group | XDC now | The model says (assumed load) | The check proposes | Why they differ |
|---|---|---|---|---|---|
| `b58a_trigger` (KR260, UltraScale+ HP, LVCMOS18) | RGMII transmit, both ports | DRIVE 12, SLEW FAST, written in the XDC | on a 4 in 50 ohm line with 4 pF and nothing in series: 1.06 V over the rail and 0.97 V under it at the worst corner, `OFFCHIP-OVERSHOOT` (contradicts the data-sheet table), `OFFCHIP-NO-TERM`, `OFFCHIP-DRIVE-MATCH` (output plus series about 25 ohm against 50) | DRIVE 12, SLEW FAST **with 27 ohm in series** (overshoot 0.08 V, first-wave margin +0.46 V; 7 combinations pass); with 22 ohm already on the board, overshoot is 0.21 V (flag), with 33 ohm 0.00 V | the DRIVE and SLEW are right for an RGMII edge; what the model asks for is a resistor, or the carrier already having one. Neither the carrier nor the SOM schematic is in the repository |
| `b58a_trigger` | user LEDs | DRIVE 8, SLOW | lumped; no overshoot | DRIVE 4, SLOW | no signal-integrity difference; a lower DRIVE only reduces switching current. The LED current (about 4 mA) sits at the 4 mA rating, so the proposal is a lower bound, not an engineering margin |
| `b96_kr260_10g` (KR260, HD, LVCMOS33) | SFP+ control and I2C | DRIVE 8, SLOW | lumped; clean | DRIVE 4, SLOW | same: lower is gentler; I2C is open-drain-like and slow, either is fine. `led[*]` in the same XDC has no group: `OFFCHIP-NO-LOAD-DATA` |
| `b63d_nexys_net` (Nexys A7, HR, LVCMOS33) | RMII to the LAN8720A: TXD, TXEN, REFCLK, MDC | none set: the tool default 12 mA SLOW | on an assumed 2.5 in 50 ohm line with 6 pF: 1.16 V over, 1.29 V under at the worst corner, and ringback through the threshold by 0.07 V, `OFFCHIP-OVERSHOOT` and `OFFCHIP-RINGBACK` (the REFCLK pin is a clock: ringback matters) | DRIVE 12, SLEW SLOW **with 33 ohm in series** (0.01 V over, 0.08 V under); with 22 ohm on the board, 0.28 V over and 0.41 V under (flag) | the default is a strong driver for a 50 ohm line: the model wants a resistor (or the real nets being short enough, shorter than assumed). The board's series resistors and trace lengths are not in the repository |
| `b63d_nexys_net`, `b2_*`, ZedBoard smoke | LEDs and UART TX to the FTDI chip | tool default 12 mA SLOW | lumped; overshoot 0.03 V and undershoot 0.09 to 0.13 V: within 0.2 V | DRIVE 4, SLEW SLOW | none that matters: the defaults are fine; the proposal is the gentlest |

**Missing data, per port** (the report cannot say more without it): for every group, the trace length and characteristic impedance (none is in `board.yaml` or the master XDC), the receiver's pin capacitance, and whether the board already has a series resistor or a termination. The Nexys A7 reference manual gives only that the switches and push buttons have series resistors, that LEDs have 330 ohm, and the DDR2 bank's 50 ohm traces; the KR260's RGMII lines carry a 125 MHz DDR clock to a PHY on the carrier and the layout is not in the repository. The loads in the spec files are marked ASSUMED; a different load changes the numbers (the length sweep shows how: a 1 in stub of the same driver does not overshoot).

**Reading it.** The strongest finding is the Nexys RMII and KR260 RGMII outputs: at tool default or at DRIVE 12 FAST, with nothing in series, the model predicts overshoot well past the data sheet's recommended 0.2 V. Whether the real boards do that depends on the missing data; if they have a 22 to 33 ohm resistor near the FPGA the XDC is right, and the report is a reason to look at the schematic, not a defect. Nothing was measured on a board. Every number is a model run.

## 10. What the model does not cover

- The package: IBIS package inductance and capacitance (a few nH and pF) are not in the model; they add a little delay and some ringing at the edges that matter here. The die capacitance is included.
- The receiver's clamp diodes (above) and its input threshold hysteresis; the thresholds are the IBIS Vinl and Vinh of the standard.
- Loss and dispersion (a lossless line); crosstalk; multi-drop lines and stubs; the DC level shift that parallel terminations cause (the model handles the terminations, the proposal never suggests one).
- Simultaneous switching noise: one output at a time. `report_ssn` is queued.
- Differential pairs: only the termination property is checked.
- Impedance-controlled outputs: reported (section 1), not simulated in the time domain; the proposal does not choose `OUTPUT_IMPEDANCE`.
- IBIS data is "preliminary" in AMD's own file header (the 7-series files are revisions from 2016 and 2017). The corners are the file's min and max columns, not a statistical spread.
- Nothing here has been compared with a scope trace.

## 11. Planned board measurement (not run; no commands now)

A later board visit could measure the model: probe an LVCMOS33 output (a Nexys A7 Pmod pin) through a known 50 ohm cable or a short stub with a 1 GHz scope and a low-capacitance probe at the far end, with DRIVE 4, 8, 12 and 16 mA, SLEW SLOW and FAST, and with and without a 22 ohm series resistor, and compare overshoot, first-incident level and 20-80 % time with the model's numbers. Pre-registered pass criteria: overshoot within 0.3 V and edge times within 25 % of the model's typical corner at every setting; failures would be reported, not tuned away. It needs the owner's approval for the board run (board lock) and RF-free cabling only.

## 12. Questions for the owner

1. How long a trace do you still treat as lumped for a 3.3 V LVCMOS output at 12 mA FAST? The model uses the sixth rule (round trip under a sixth of the edge); does that match what you see on boards, or is it too strict?
2. Do you put a series resistor on every LVCMOS output that leaves the board by default, and which value for a 50 ohm line and for a 60 ohm one? Do you pick the resistor first and then the DRIVE, as the proposal does, or the reverse?
3. How far do you trust AMD's IBIS output corners for the resistance of a DRIVE setting? The 7-series files are from 2016 and 2017 and marked preliminary: have you seen a measured output behave differently from them?
4. Do you include package inductance when overshoot matters, and do you rely on the receiver clamp diodes at all (the model reports overshoot unclamped)?
5. Which receiver limit do you design to: VCCO + 0.2 V as recommended, or the data sheet's overshoot duration table?
6. When is FAST right for you: only source-synchronous or clock outputs? Have you seen `SLEW SLOW` at 16 mA surprise someone (the IBIS rise of 0.6 ns is as fast as FAST at 4 mA)?
7. On 1.8 V HP banks, do you prefer a calibrated driver (`OUTPUT_IMPEDANCE RDRV_48_48` with ODT at the receiver) to an LVCMOS driver with a 22 ohm resistor? What made you choose, and do you give up the pin count that DCI's reference pins cost?
8. What rule of thumb do you use for simultaneous switching: how many outputs per bank or per VCCO pair at DRIVE 12 FAST before you slow them down?
