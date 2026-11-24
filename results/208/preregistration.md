# Brief 208: plan and pre-registration (clock multiplexing)

Written 2026-11-24 17:31 GMT (`date`), before any run. Nothing below has been measured yet. Each expectation gets a
"what happened" entry in `README.md` after its run; this file is not edited after the first run except to append
dated amendments at the end.

Tools: Vivado 2026.1 (`/opt/Xilinx/2026.1`), xsim 2026.1 with the unisim library, Quartus Prime Lite 25.1std (if a
Cyclone V or MAX 10 probe is reached). Parts: `xc7a35tcpg236-1` (7 series) and `xck26-sfvc784-2LV-c` (UltraScale+).

## Sources read before planning (summary, own words)

| Id | Document | Version | Where | What it says that matters here |
|---|---|---|---|---|
| S1 | UG472 7 Series Clocking | v1.14, 2018-07-30 | ch. 2, "Global Clock Buffer Primitives" to "BUFGMUX_CTRL with a Clock Enable" (pp. 37 to 46) | Every global buffer primitive is a preset of BUFGCTRL. Selecting an input needs its S and CE both high. Switching on S is glitch-free whatever the timing of S (setup/hold of S only decides whether one extra pulse of the old clock passes; S is sampled on the falling edge); switching on CE is faster but a setup/hold violation on CE can glitch. **BUFGMUX drives the CE pins with its select**, so its select must meet setup; **BUFGMUX_CTRL drives the S pins** and cannot glitch. The glitch-free switch waits for the old clock to go low and then for the new clock to go low; if a clock is not toggling the switch never completes, and IGNORE0/1 bypass that edge detection (the "asynchronous MUX" use model, glitch protection off). BUFGCTRLs cascade through dedicated paths only to adjacent buffers in a ring of 16 per device half. CLK_SEL_TYPE SYNC/ASYNC attribute on BUFGMUX. |
| S2 | UG572 UltraScale Clocking | v1.11, 2025-05-29 | ch. 2, BUFGCTRL, BUFGMUX, BUFGCE_DIV, MMCM CLKINSEL | Same BUFGCTRL behaviour; cascade ring of eight; each clock region has 24 BUFGCE, 8 BUFGCTRL, 4 BUFGCE_DIV sharing 24 tracks. BUFGCE_DIV CE is synchronous for glitch-free gating. MMCM CLKINSEL switches the reference, but the MMCM must be held in reset during the switch. |
| S3 | UG903 Using Constraints | v2025.2, 2025-11-20 | ch. 3 "Exclusive Clock Groups" (pp. 96 to 97); ch. 2 "Logically Exclusive Clock Groups with/without Interaction" (pp. 43 to 44); ch. 5 `set_case_analysis` (pp. 135 to 138) | A combinational cell (BUFGMUX, BUFGCTRL or a LUT) propagates every input clock to its output; such clocks are exclusive and are constrained with `set_clock_groups -logically_exclusive` or `-physically_exclusive`, **which are equivalent on AMD FPGAs** (the labels are for ASIC crosstalk modes). Where the source clocks also meet outside the mux fanout, the wizard creates generated copies on the shared tree and groups only those. `set_case_analysis` on a select pin disables the arcs of the other input. |
| S4 | UG949 Methodology | v2025.2, 2025-11-20 | ch. 4 "Constraining Exclusive Clock Groups" (pp. 172 to 174); ch. 3 "Clock Multiplexing" (pp. 113 to 116); ch. 6 Tables 6 and 7 (pp. 215 to 216) | Use check_timing `multiple_clock` to find overlapping clocks. If the two clocks meet **only** in the mux fanout, group the source clocks directly; if any path joins a source clock and the muxed clock (paths A, B, C in Fig. 101), create generated clocks on the mux output (`-divide_by 1 -source mux/I0`, then `-add -master_clock clk1 -source mux/I1`) and group those. Build 3:1 and 4:1 muxes as balanced two-level BUFGCTRL trees on adjacent sites; 5:1 to 8:1 as a cascaded chain of 7 BUFGCTRLs; wide muxes cannot balance insertion delay, so they are for asynchronous clocks only. TIMING-14 (LUT on the clock tree, Critical Warning); TIMING-56 (missing exclusive clock groups, Warning). |
| S5 | UG906 Design Analysis | v2025.2, 2025-12-10 | App. A TIMING-14 (p. 357), TIMING-56 (p. 389) | TIMING-14: a LUT on a clock path uses fabric routing, adds skew and PVT sensitivity. TIMING-56: several clocks generated or auto-derived on one source pin with no exclusive group, so the timer times pairs that cannot coexist. |
| S6 | UG901 Synthesis | v2025.2 | `GATED_CLOCK`, `CLOCK_BUFFER_TYPE` | Describes gated-clock conversion to enables (attribute plus option) and choosing the input buffer type. **Says nothing about inferring BUFGMUX/BUFGCTRL from an RTL clock mux** (searched: no "clock mux", BUFGMUX or BUFGCTRL hit). What synthesis does is therefore measured, not cited. |
| S7 | Altera Quartus Prime Standard Edition Design Recommendations, UG-20175 | 18.1, 2018-09-24 (public mirror; via brief 204 study row L12, sections 1.2.2.4 and 2.6.2) | to be re-read in body | Clock muxing acceptable only on global clock resources and if one of four holds: the selection is fixed after configuration; it is used only for test; registers are reset on a switch; or a wrong response after a switch does no harm. Otherwise use a fully synchronous scheme or the dedicated clock-control block. |
| S8 | Quartus Lite 25.1std install | 25.1std | `quartus/libraries/megafunctions/altclkctrl.tdf`; `ip/altera/megafunctions/altclkctrl`; `da_golden_rule.xml` | `altclkctrl` (clock control block) takes up to 4 inputs, `clkselect`, `ena`, and a parameter `USE_GLITCH_FREE_SWITCH_OVER_IMPLEMENTATION` (default OFF). Design Assistant rules C101 (gated clock scheme), C104, C105 (clock should be global). |

## Experiments (pre-registered expectations)

Common bench: two clock inputs. Topology U (unrelated): `clk0` 100 MHz and `clk1` 75 MHz from two ports. Topology R
(related): one 100 MHz input to an MMCM giving `clk0` 100 MHz and `clk1` 150 MHz. Registers FD0 on `clk0`, FD1 on
`clk1`, FDM0 and FDM1 on the muxed clock, with the UG949 Fig. 101 paths A (FD0 to FDM), B (FD1 to FDM) and C (FDM to
FD0) switchable by a generic, so the "no interaction" and "interaction" cases come from the same source. In topology R,
path A carries a deliberately deep adder chain so that, when timed clk0 to the 150 MHz muxed clock, it fails setup.
Each arm: synthesis, `opt`, place, route, then `check_timing`, `report_clock_interaction`, `report_methodology`,
`report_cdc`, `report_timing_summary`, `report_clocks`, `report_exceptions -ignored`.

| Exp | Arm | Expectation (before the run) |
|---|---|---|
| a | U, BUFGMUX, only `create_clock` on the two ports, with A/B/C | E-a1: check_timing `multiple_clock` lists the FDM clock pins (both clocks reach them). E-a2: report_clock_interaction shows clk0 to clk1 and back as timed, "no common primary clock" (unsafe). E-a3: report_methodology gives no TIMING-56 (that rule is about generated or auto-derived clocks on one pin; these are primary clocks propagated through the mux): **uncertain, 60%**. E-a4: report_cdc lists the clk0/clk1 crossings as unsafe. E-a5: the flow's existing gates already fail this arm through `multiple_clock` (post-synth check_timing must be all zero). |
| b1 | U, groups on the source clocks, `-logically_exclusive`, with A/B/C | E-b1: `multiple_clock` empty; clock interaction shows clk0/clk1 as "Clock Group"; **report_cdc no longer lists path A or B**, although in hardware path A is a real crossing from clk0 into clk1 whenever clk1 is selected. Every existing gate passes: the hidden crossing is what our new check must catch. |
| b2 | as b1, `-physically_exclusive` | E-b2: every report identical to b1 apart from the option text (UG903: equivalent on AMD). |
| b3 | U, generated clocks on the mux output, `-physically_exclusive` between the two generated clocks | E-b3: `multiple_clock` empty; clk0 to clk1mux and clk1 to clk0mux still reported (as unsafe CDC in report_cdc, timed in clock interaction), so path A stays visible. |
| b4 | as b3, `-logically_exclusive` | E-b4: identical to b3. |
| b5 | U, `-asynchronous` groups on the source clocks | E-b5: same coverage loss as b1; the flow's existing advisory `async_clock_groups_review` fires (brief 105A), so the mistake is flagged but not failed. |
| b6 | U, generated clocks on the mux output, no clock groups | E-b6: TIMING-56 (Warning) fires on the mux output pin; clk0mux/clk1mux timed against each other. |
| b7 | U, `set_case_analysis` on the select | E-b7: only one clock propagates; the other mode is untimed and invisible in every report (clock interaction lists the case-disabled clock with no paths to the mux fanout). |
| b8 | R, groups on source clocks (b1 style) with path A | E-b8: report_timing_summary passes (WNS >= 0), because the failing clk0 to clk1 path through the mux is removed. |
| b9 | R, generated clocks on mux output (b3 style) with path A | E-b9: the same path A fails setup (WNS < 0) and is reported; this is what b8 hides. |
| b10 | U and R, no A/B/C paths, groups on source clocks | E-b10: identical coverage to b3 (UG949's "no interaction" case: grouping the sources is correct). Counter-case for the check: it must not flag this arm. |
| c1 | RTL `assign clkm = sel ? clk1 : clk0;` (registered `sel`), both parts | E-c1: synthesis maps the mux to a LUT (LUT3) and inserts a BUFG after it (no BUFGMUX is inferred: UG901 is silent). report_methodology gives TIMING-14 (Critical Warning); our post-synth gate fails on it already. On xc7a35t, place may stop with Place 30-574 (clock-capable input driving a LUT) unless `CLOCK_DEDICATED_ROUTE FALSE` is set: **uncertain, 50%**. |
| c2 | as c1 with `sel` tied constant | E-c2 (counter-case): the LUT is optimised away; no TIMING-14; this is Altera's condition 1 in its trivial form. |
| c3 | as c1, xsim behavioural (RTL) | E-c3: changing `sel` while the clocks are mid-cycle produces a runt pulse on `clkm` (a glitch), and FDM sees an extra edge. |
| d1 | 4:1 mux as UG949 Fig. 67 (two first-level BUFGCTRLs into one), both parts | E-d1: placer puts the three BUFGCTRLs on adjacent sites; four clocks propagate through; TIMING-56 does not fire without generated clocks; `multiple_clock` lists the fanout (four clocks). Insertion delay from each input to a load differs by less than 0.2 ns between inputs (balanced): **uncertain**. |
| d2 | 3:1 as Fig. 67's equivalent | E-d2: as d1. |
| d3 | linear chain of 9 BUFGCTRLs on xck26 (one more than the ring of eight) and 17 on xc7a35t (one more than the ring of 16) | E-d3: placement fails or falls back to non-dedicated routing between some stages with a CRITICAL WARNING or ERROR from place: **uncertain**; recorded as the cascade limit we can measure. |
| d4 | 8:1 as Fig. 69 (cascaded chain of 7) on xck26 | E-d4: places on adjacent sites; insertion delay rises along the chain (unbalanced, as UG949 warns). |
| e1 | xsim, unisim BUFGCTRL (and BUFGMUX_CTRL), switch from I0 to I1 with both running | E-e1: output goes low after I0 falls and resumes on I1 after I1 falls; no runt pulse. |
| e2 | xsim, I0 stopped (held low or high) when the select changes | E-e2: if I0 stops low the switch still completes (the "wait for old clock low" is already met); **if I0 stops high, the output is stuck high/low and never switches** (the lock-up); setting IGNORE0 high before the select change lets it switch at once. Safe-switch sequence to show: detect the stop (counter on the other clock), assert IGNORE for the dead input, switch S, deassert IGNORE once the new clock is running. |
| e3 | xsim, BUFGMUX (CE select) with select changing inside the CE setup window | E-e3: the unisim model reports a setup/hold timing-check violation or produces an X/glitch on O: **uncertain** (model may not carry the timing check at RTL sim). |
| f1 | BUFGCE gating one region's clock vs the same logic with a fabric clock enable, `report_power` vectorless with CE static probability 0.1, 0.5, 0.9 | E-f1: BUFGCE's clock-tree dynamic power falls in proportion to the enable duty; the fabric-CE version keeps full clock-tree power; difference visible at the ~mW level on xc7a35t for a few hundred registers. |
| f2 | is BUFGCE/CE and BUFGMUX/S timed? | E-f2: report_timing reports a path to BUFGCE/CE (setup against the buffer's input clock). For BUFGMUX/S a path is reported against one of the two input clocks: **uncertain** which. |

## Planned outputs

1. `results/208/` with `designs/`, `xdc/`, `run_*.tcl`, every report, and `README.md` (Records, Reproduce, Known gaps).
2. A check `flow/clock_mux_check.py` (not `standards_check.py`; not a duplicate of brief 204a's report gates), run on
   report and netlist fixtures recorded here, with `flow/tests/test_208_clock_mux.py`. Planned rules:
   - `CLKMUX-LUT`: a clock net whose driver is a LUT (from a netlist dump: clock pins' driver cells), including the
     case where a BUFG follows the LUT. Already a Critical Warning via TIMING-14; the check names the source clocks
     and gives the house-rule reason.
   - `CLKMUX-NO-GROUPS`: a BUFGMUX/BUFGCTRL (or LUT mux) output reached by two or more clocks with no exclusive group
     covering them (from `report_clocks` and the netlist dump of mux pins, plus check_timing `multiple_clock`).
   - `CLKMUX-SRC-GROUPED-WITH-INTERACTION`: exclusive or asynchronous groups set on the source clocks while a timing
     path joins a source clock and the muxed tree (the b1/b8 mistake): detected from a Tcl dump of paths between
     non-mux registers on a source clock and registers on the mux fanout.
   - `CLKMUX-CE-SELECT`: a BUFGMUX (CE-select) or a BUFGCTRL switched on CE whose select is not from the same clock
     domain or is unsynchronised (advisory: prefer BUFGMUX_CTRL/S-select).
   - `CLKMUX-CASCADE`: more than two BUFGCTRL levels for a mux of up to four inputs, or a chain longer than the
     measured limit (d3).
   - `CLKMUX-STOP`: a BUFGCTRL with IGNORE tied low whose inputs include a clock that can stop (a declared
     `may_stop` clock in architecture.yaml): advisory.
3. expertise.yaml `clocking`: checks and measured evidence entries.
4. KB PR: skill `techniques/clocking/clock-multiplexing` with the house rule, templates, protocol, cited and tied to
   the measured table.
5. Course note: lessons to change (list only).

## Stopping rules

- A Vivado run that fails for a reason outside the experiment (licence, part not installed) is recorded and the arm
  is moved to the other part if possible; never edited to pass.
- If usage reaches 90% weekly, stop with `BLOCKED:`.
- Each arm runs once (deterministic tool); a surprise is re-run once with a fresh build directory to confirm.

## Amendment 1, 2026-11-24 17:45 GMT (still before any run): Altera arms

Source added (read locally, body): the Quartus Lite 25.1std `altclkctrl` IP files
(`ip/altera/megafunctions/altclkctrl/parameters.csv`, `altclkctrl_hw.tcl`). The clock control block takes 1 to 4
inputs; `USE_GLITCH_FREE_SWITCH_OVER_IMPLEMENTATION` ("Ensure glitch-free switchover implementation") **defaults to
FALSE**, and the IP refuses it with one input; the supported families include Cyclone IV E, Cyclone V and MAX 10.
Snippet-only (web search, not body; Altera pages redirect): the switchover needs the currently selected clock running
before a switch; on Cyclone V the dynamically selectable inputs are PLL outputs plus a dedicated clock pin (a forum
post, unverified).

| Exp | Arm | Expectation (before the run) |
|---|---|---|
| q1 | Cyclone V (5CEBA4F23C7) and MAX 10 (10M50DAF484C7G): `altclkctrl`, 2 inputs, glitch-free OFF, `clkselect` from a register | E-q1: fits; no logic added on the select path besides the clock control block; Timing Analyzer shows both clocks on the fanout and times them against each other until `set_clock_groups -exclusive` is added. |
| q2 | as q1, glitch-free ON | E-q2: the generated clearbox adds registers (a per-clock enable handshake) between `clkselect` and the block: the logic count rises by a few registers. |
| q3 | RTL `assign clkm = sel ? clk1 : clk0;` | E-q3: Quartus places the mux in a LUT, promotes its output to a global clock, and warns; the Timing Analyzer's `report_clocks` shows both clocks propagate; Design Assistant (if it runs on the device) flags C101/C105 or similar: **uncertain**. |
