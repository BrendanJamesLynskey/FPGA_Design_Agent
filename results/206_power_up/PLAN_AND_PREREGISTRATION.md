# Brief 206: register power-up values, AMD against Altera: plan and pre-registration

Written 2026-11-24 17:34 GMT (stamped with `date`), before any run. Nothing in this file has been measured yet. Results
will go in `README.md` and `records/`; this file is not edited after the first run except for the dated
amendments section at the end.

Status at writing: planner hold (PC overloaded, load 9.7, swap full). Source reading and this plan only; no Vivado,
Quartus, simulator or test suite until the planner lifts the hold.

## The question

Owner: configuration presets registers for free on AMD; is Altera really different? Brief 204 (rows A45, L26) said:
AMD loads 0 or 1 for free through the GSR; Altera registers power up 0 and a 1 costs inverters (NOT-gate push-back).
Establish per family what is true, what it costs, and when the cost is non-zero in practice. Feeds decision 38's
`rtl.initial_values` setting (brief 205, branch `b205-initial-values`).

## 1. What the vendors say (source reading done 2026-11-24)

Tags: **B** body text read; **S** search-result snippet only (not body); page = PDF page.

### AMD

| # | Claim | Source |
|---|---|---|
| V1 | GSR sets every sequential cell to its initial value at the end of configuration; with no initial value, most primitives default to 0, FDSE and FDPE to 1; no need for a reset only to initialise | UG949 v2025.2 p.50, B |
| V2 | AMD highly recommends initialising all inferred registers, SRLs and memories; with no initial value synthesis may pick 0 or 1 (generally 0; one-hot FSM exceptions) | UG949 v2025.2 p.71, B |
| V3 | GSR release is followed by GWE release; if not synchronised to the clock, parts of a design can start in an unknown state | UG949 v2025.2 p.137, B |
| V4 | 7 series CLB: SRHIGH/SRLOW set what SR forces; INIT0/INIT1 set the configuration/GSR state; by default SRLOW implies INIT0 and SRHIGH implies INIT1, but 7 series can set INIT independently of SR | UG474 v1.9 p.20, B |
| V5 | UltraScale CLB: separate INIT attribute, default follows the SR sense, can be set independently of it; set/reset is per FF but SYNC/ASYNC per group of eight | UG574 v1.6 p.18, B |
| V6 | UltraScale: "minimise set/resets; flip-flops are initialised at every power-up" | UG574 v1.6 p.12, B |
| V7 | SRLs cannot be set or reset but can be initialised to any value | UG574 v1.6 p.34, B |
| V8 | Verilog initial value: constant, all bits; carried as INIT on the register; independent of any local reset | UG901 v2025.2 p.251, B |
| V9 | 7 series BRAM: GSR sets the output latches/registers to INIT_A/INIT_B; it does not touch the array; array contents from INIT_xx | UG473 v1.14 p.32-33, B |
| V10 | UltraScale BRAM: INIT_A/B are the port outputs after configuration; block RAMs used for RSA-authentication rolling keys (every twelfth BRAM36 from the bottom of a column) cannot take user initial values and come up 0 | UG573 v1.14 p.41 and the INIT section, B |
| V11 | UltraRAM: array is all 0 at power-up or device reset; no user INIT; output reset value 0 only (no settable SRVAL) | UG573 v1.14 p.90, B; UG901 v2025.2 p.122, B |
| V12 | 7 series ILOGIC/OLOGIC: SRVAL per element, SR type shared; ISERDES has INIT_Q1..Q4 and SRVAL_Q1..Q4 | UG471 v1.10, ILOGIC/ISERDES attribute tables, B |
| V13 | UltraScale IOB registers are ordinary FDRE/FDSE/FDCE/FDPE with IOB=TRUE; IS_D_INVERTED unsupported (must be 0) | UG571 v1.16 p.149, B |
| V14 | DSP48E1/E2: no INIT attribute appears for the pipeline registers in UG479/UG579 (absence found by search; the registers have reset pins only) | UG479, UG579, B (by absence; to be measured) |

### Altera

| # | Claim | Source |
|---|---|---|
| L1 | Core registers power up 0 on all Intel FPGA devices; a non-zero power-up is emulated; preset converted to clear plus NOT-gate push-back (inverter before and after); the register still powers up 0 | QPS Design Recommendations UG-20175 18.1 (2018-09-24) 2.5.1 p.67-68, B |
| L2 | Where aload exists, a reset of 1 can be built with aload, and then the register powers up 0 (no push-back) | same, p.68, B |
| L3 | Power-Up Level logic option (per register or per entity); Quartus reads HDL initial values into Power-Up Level; high on a large entity can degrade QoR (inverters, enable and secondary-control inference) | same 2.5.1.1 p.68, B |
| L4 | VHDL integer register with no initial value powers up at the left end of its range (most negative for signed): a hidden non-zero power-up | same p.69, B |
| L5 | If the architecture lacks two async controls (aclr and aload), power-up and reset cannot differ; synthesis ignores a conflicting power-up level | same p.69 note, B |
| L6 | Dedicated RAM block outputs power up 0, even with a .mif, until the first read; MLAB (registers) show the initial value at once | same 2.4.1.11 p.60, B |
| L7 | Cyclone IV LE: async clear only; no LAB-wide aload for preset; preset by NOT-gate push-back; either preset or clear, not both; chip-wide DEV_CLRn | Cyclone IV Handbook vol.1 CYIV-5V1-2.2 (March 2016) ch.2 PDF p.35, B |
| L8 | Cyclone IV M9K outputs power up cleared, registered or not; .mif contents appear only after the first read | same ch.3 PDF p.38 and p.54, B |
| L9 | **Cyclone IV IOE registers can be programmed to power up high or low** (high with async preset, low with async clear); one preset/clear source per IOE | same ch.6 PDF p.112, B |
| L10 | Cyclone V ALM register ports: data, clock, sync and async clear, sync load; the LAB-wide control set offers clock enable 0 *or* asyncload *or* labpreset | Cyclone V Handbook vol.1 CV-5V2 (2017-09-19) ch.1 p.1-5, B |
| L11 | Cyclone V DSP input and output registers are cleared at power-up; M10K outputs power up 0 (registered or bypassed), MLAB with output registers 0, MLAB bypassed shows contents | same ch.2 Table 2-4, DSP chapter, B |
| L12 | MAX 10 LE: same as Cyclone IV (no LAB-wide aload for preset; push-back; preset or clear; DEV_CLRn) | MAX 10 Device Architecture M10-ARCHITECTURE 2017.02.21, LAB control signals, B |
| L13 | MAX 10 GPIO Lite IP: "set registers to power up high" option (DDR, no aclr/aset) | MAX 10 GPIO User Guide 683751 22.1, parameter settings, **S** |
| L14 | Cyclone 10 GX guidelines: power-up high on a register reset low (or the reverse) blocks push-back; power-up may be ignored or undefined | 683703 17.1, **S** |
| L15 | Pro Edition (Hyperflex parts) recommends removing initial power-up conditions (retiming) | AN 919 683369, **S**; not our families |

Disagreement to test: AMD recommends initial values everywhere (V2); Altera says they cost logic (L1, L3) and, for
Hyperflex, recommends against them (L15). Altera documents a real power-up-high register in the Cyclone IV I/O element
(L9) and the MAX 10 GPIO (L13), so "every register powers up 0" (brief 204 row L26) is true of the **core** only.

## 2. Experiments

Tools: Vivado 2026.1, Quartus Prime Lite 25.1std (Cyclone IV E, Cyclone V, MAX 10), Questa FSE from that install, xsim.
Parts: AMD xc7a35tcpg236-1 and xck26-sfvc784-2LV-c; Altera EP4CE22F17C6, 5CEBA4F23C7, 10M50DAF484C7G (the DE10-Lite part).
All designs are tiny; synthesis out of context unless a row needs I/O or placement. One run per arm (Quartus and Vivado
are deterministic for a fixed input; noise not estimated).

Each arm is a pair: the same RTL with power-up 0 and power-up 1 (declaration initialiser, Verilog), so the difference is
the cost of the 1. Reported per arm: cells by type, LUT/LE/ALM count, inverters (LUT1 or LE used as NOT), the INIT
property read from the netlist (AMD: `get_property INIT`; Altera: the post-fit netlist written by the EDA netlist writer,
and the Power-Up Level rows of the synthesis report), the synthesis and fitter messages, and Fmax/WNS where timing applies.

### AMD arms

| Arm | RTL | Read |
|---|---|---|
| X1 | plain register, no reset | FDRE INIT |
| X2 | sync reset to 0, initial 1 | FDRE INIT=1? extra LUT? |
| X3 | sync set to 1, initial 0 | FDSE INIT=0? |
| X4 | async clear, initial 1 | FDCE INIT=1? |
| X5 | async preset, initial 0 | FDPE INIT=0? |
| X6 | 64-bit pipeline register to register, all bits initial 1 | INIT on all bits, LUTs |
| X7 | input register and output register packed into the IOB (IOB=TRUE, implementation), initial 1, with and without a reset | placed in ILOGIC/OLOGIC (7 series) or the IOB FF (US+)? INIT kept? warnings |
| X8 | registers before a multiplier (A/B) and after it (P), initial non-zero | absorbed into DSP48 or kept in fabric? warnings |
| X9 | block RAM read with output register, output register initial non-zero; array initialised | INIT_A/INIT_B, DOA_REG; array INIT_xx |
| X10 | LUTRAM and SRL with initial contents | INIT on RAM32M/RAM64X1D and SRL16E/SRLC32E |
| X11 | UltraRAM (`ram_style = "ultra"`, xck26) with initial contents and with an output register initial value | refused, warned, or silently 0? |
| X12 | VHDL `integer range -8 to 7` signal, no initialiser | INIT chosen by Vivado |
| X13 | GSR in simulation: post-synthesis functional netlist of X2 and X4 in xsim with `glbl` | Q after GSR = INIT; after reset = reset value |

### Altera arms (each family)

| Arm | RTL | Read |
|---|---|---|
| Q1 | plain register | LEs/ALMs, inverters, "power-up" messages |
| Q2 | sync reset to 0, power-up 1 | push-back conflicts with the reset? power-up honoured or ignored? |
| Q3 | async clear, power-up 1 | expected conflict (L5) |
| Q4 | async preset (no init) | push-back; powers up as 1? |
| Q5 | fast input and output register (FAST_INPUT_REGISTER / FAST_OUTPUT_REGISTER), power-up 1 | packed into the IOE? push-back moved out to an LE? |
| Q6 | register feeding a DSP / embedded multiplier input and M9K/M10K input, power-up 1 | absorbed into the hard block or left in fabric? |
| Q7 | 64-bit bus, all bits power-up 1, register to register with no logic between | LEs added; Fmax |
| Q8 | 64-bit bus, all bits power-up 1, with a 4-input function in front (inverter absorbable) | LEs added (expect none) |
| Q9 | VHDL integer signal, no initialiser | the hidden power-up (L4) |
| Q10 | power-up simulation: post-fit gate-level netlist in Questa FSE, Q1/Q2/Q3/Q4 | the value seen at the output before the first clock |

Also: the `NOT_GATE_PUSH_BACK` setting OFF for Q1 and Q7 (does Quartus then drop the power-up with a warning?).

MAX 10 configuration from internal flash: documentation only (no board runs in this brief): does user mode entry differ in
how registers start? Recorded as read, not measured.

## 3. Pre-registered expectations (before any run)

AMD:
- E1. X1 to X5 all give the INIT asked for with no extra LUT, on both parts, independent of the reset sense (V4, V5, V8).
  Confidence high.
- E2. X6: 64 FDRE INIT=1, no LUTs. High.
- E3. X7: IOB packing keeps INIT on both families; no warning. Medium (UG571 says IOB regs are ordinary FDxE; 7 series
  ILOGIC/OLOGIC may map INIT to INIT_Q/SRVAL). Strongest counter-case: 7 series OLOGIC with a reset of the opposite
  sense to the INIT.
- E4. X8: a non-zero initial value on a register next to a multiplier keeps it out of the DSP48 (kept in fabric, more FFs),
  with or without a message; Vivado does not silently drop the INIT. Medium-low; this is the arm most likely to surprise
  (V14).
- E5. X9: BRAM output register INIT is honoured via INIT_A/INIT_B on both families; array INIT honoured. High.
- E6. X10: LUTRAM and SRL INIT honoured. High.
- E7. X11: UltraRAM with non-zero contents is either not mapped to URAM (falls back to BRAM) with a message, or errors.
  Medium. Silent zero would be a dangerous finding.
- E8. X12: Vivado gives the integer register INIT for the leftmost value (-8, i.e. bits 1000) or 0. Unsure: 50/50.
- E9. X13: after GSR, Q equals INIT; the opposite-polarity reset then gives the reset value. High.

Altera:
- E10. Q1: power-up 1 costs **0 extra LEs/ALMs** when the register's LE has a free LUT (the inverters fold into its own
  LUT and the destination LUT) and the destination has logic; reported LE count may still rise by the inverter at the
  output if the destination is a port or another register. Medium.
- E11. Q2 (sync reset to 0, power-up 1): push-back still works (the sync clear becomes a sync set after inversion) on
  Cyclone IV/MAX 10 via synchronous load; power-up honoured. Medium-low; the vendor note (L14) is about async conflicts.
- E12. Q3 (async clear, power-up 1): power-up ignored with a warning, register powers up 0. High (L5, L14).
- E13. Q4 (async preset): push-back, powers up 1 in effect. High (L1, L7).
- E14. Q5: Cyclone IV and MAX 10 I/O registers power up high natively (no inverter); Cyclone V I/O registers: unknown,
  expect push-back moves the register out of the IOE or adds an LE. Medium.
- E15. Q6: a power-up-1 register is not absorbed into the DSP or RAM input register (those power up 0): it stays in the
  fabric (more LEs/ALMs) or the init is dropped with a warning. Medium.
- E16. Q7: register-to-register with no logic: the inverters cost LUT delay and possibly LEs; Fmax falls measurably
  (more than 5 %) on Cyclone IV/MAX 10; on Cyclone V the ALM may absorb the inverter in the 6-LUT feeding the register.
  Medium-low.
- E17. Q8: 0 extra LEs (inverters absorbed). High.
- E18. Q9: the integer register powers up at -8 (bit 3 set): one push-back on that bit. Medium.
- E19. Q10: gate-level simulation of Q1 shows 1 at the output from time 0; Q3 shows 0. Medium; Questa FSE may lack the
  post-fit libraries for some families, in which case the report says so.

Inference to test (both): "the cost is non-zero only where an inverter cannot be absorbed": register to register, a
register feeding a hard block or I/O, and a register with a conflicting reset.

## 4. Stopping rules and honesty

- One run per arm; if a number looks inconsistent with the netlist, re-run that arm once and record both.
- A family that cannot run an arm (licence, device support, simulator library) is reported as not run, with the reason.
- Every number in the README comes from a file under `records/`.

## 5. Deliverables (from the brief)

1. `results/206_power_up/` (this repo, branch `b206-power-up`): RTL, scripts, records, README with Records / Reproduce /
   Known gaps and limits.
2. KB PR in `FPGA_Design_Agent_Knowledge`: a technique skill on power-up values per vendor, cited and tied to the
   records, plus a `family_matrix/areas/rtl.yaml` row (7-series vs UltraScale+ columns).
3. Agent PR: a check where the finding is checkable. Plan: an advisory that reads the synthesis netlist/log for an initial
   value dropped (AMD: INIT lost on DSP/URAM/IOB, if E3/E4/E7 show a silent drop) or costing logic (Altera, when a Quartus
   flow exists), with tests on recorded fixtures and expertise.yaml evidence. Not in `flow/standards_check.py`
   (brief 205). Registering a check edits `flow/checks/__init__.py`, which brief 205 also edits: base on
   `b205-initial-values` once it is pushed, else on main with a note. No overlap with 204a's report gates.
4. The house rule (what `allow` means per vendor; reset vs initial value; the advisory).
5. Course note listing the Part 8 and other lessons on initial values or resets.

## Amendments

- 2026-11-24 18:53 GMT, after seeing X8 and X9 on xc7a35t (INITV=1): a non-zero initial value kept every register out of the
  DSP48E1 (AREG/BREG/MREG/PREG all 0, 108 FDRE in fabric, no warning) and kept the block-RAM output register out of the RAM
  (DOB_REG=0; the read register's value went to INIT_B; 32 FDRE in fabric). Added follow-up arms, expectations written before
  they run: **X8b** only the P register non-zero (expect A/B/M absorbed, P in fabric); **X8c** only A/B non-zero (expect M and
  P absorbed, A/B in fabric); **X9b** read register and output register given the *same* non-zero value (expect DOB_REG=1 with
  INIT_B = that value, nothing in fabric, since the primitive has one INIT per port); **X9c** only the output register
  non-zero (expect DOB_REG=1, INIT_B = its value, since with DOB_REG=1 INIT_B belongs to the output register). These run as a
  second batch (`tcl/arms_b.tcl`) on both parts.
- 2026-11-24 18:56 GMT, after X7 and X12 on xc7a35t: the IOB registers kept INIT=1 in ILOGICE2.IFF and OLOGICE2.OUTFF with
  a sync or async reset of the opposite sense; X12's integer register got INIT=1 on its top bit only (power-up -8). Added
  **X12b** (the same counter with an explicit `:= 0`; expect all INIT 0 and the same LUTs, so X12 costs nothing on AMD
  but starts at -8) and **X7 DRC** (report_drc after placement for the opposite-sense IOB arms; expect no violation that
  mentions INIT). Same batch as X8b to X9c.
