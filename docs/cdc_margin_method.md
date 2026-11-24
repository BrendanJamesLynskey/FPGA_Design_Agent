# Clock-crossing margins: one method for AMD and Altera

Brief 207, 2026-11-24. The owner asked: "Clock-crossing margins: can we develop our own method that combines the two?" Altera's
Design Recommendations suggest adding clock uncertainty of 10 to 15 % of the clock delay. AMD removes the sources of uncertainty and
bounds each crossing with `set_max_delay -datapath_only`, `set_bus_skew` and the XPM synchroniser constraints. This document is the
method we use instead of either. The measurements behind it are in [results/207_cdc_margin](../results/207_cdc_margin/README.md),
and the check that enforces it is `flow/cdc_margin.py` (check `cdc_margin`, gate `post_route_bus_skew_met`, rule HDL-CDC-03).

Each section keeps three things apart: what the vendor says (cited), what we measured (from `results.md`), and what we infer. The
house rule comes last and is built from all three.

## 1. What each vendor's crossing check guarantees (vendor text)

Tags: **B** = body text read; **S** = a search snippet only. Full table with all sources: [results/207_cdc_margin/README.md](../results/207_cdc_margin/README.md) section 1.

| | AMD (Vivado 2026.1) | Altera (Quartus Prime Standard 25.1std) |
|---|---|---|
| Latency bound | `set_max_delay -datapath_only`: the data path alone, no clock skew, the hold check becomes a false path (UG903 v2025.2 pp. 129-131, B). A clock group overrides it. | `set_max_delay` includes clock skew; `set_net_delay -max` bounds the net only (Quartus help, B). `set_data_delay` (the datapath-only form) is Pro-only in practice: **25.1std accepts the command but its Timing Analyzer rejects it** (measured, section 2). |
| Skew bound | `set_bus_skew`: the spread of capture times across the bits of one constraint, **clock uncertainty excluded** (UG906 v2025.2 p. 163, B), slow and fast corners, optimised only by `route_design` (UG903 p. 143, B). Not in `report_timing_summary`: run `report_bus_skew`. | `set_max_skew`: data and clock arrival, micro-parameters, **clock uncertainty included**, on-die variation (Quartus help `set_max_skew`, B). **Cut by `set_false_path` and `set_clock_groups`**, not by `set_max_delay`/`set_min_delay`. Reported by `report_max_skew`. |
| Recommended values | Gray bus: max delay at the source period, bus skew at min(source, destination); handshake (up to 100 bits): both at destination period x the request's sync stages; single bit and reset synchronisers: a false path to stage 0, so **no latency bound** (the XPM constraint files shipped with 2026.1, B). Bus skew should be more than half the smaller period (UG903 p. 144, B). | Pro guide: keep crossings short with `set_net_delay` and put `set_max_skew` on buses (S). |
| Margin | No percentage for crossings. User uncertainty is for overconstraining a failing clock before routing: setup only, removed before routing, never above 0.5 ns (UG949 v2025.2 p. 283, B; TIMING-44/45, UG906 App. A, B). | Setup and hold uncertainty of 10 to 15 % of the clock delay, in "Optimizing Clocking Schemes" (Design Recommendations 18.1 body via brief 204's study, B; that its scope is timed paths between clock domains, not asynchronous crossings, is S). |
| MTBF | `report_synchronizer_mtbf`, UltraScale only; chains found only through `ASYNC_REG`; settling time = the positive slack after the stages; UNDEFINED on a violation, an unconstrained clock or a zero toggle rate (UG835 v2025.2 pp. 1528-1530, B). 7 series: take the default `DEST_SYNC_FF` (UG949 p. 144, B). | `report_metastability`: typical and worst-case design MTBF; per-chain MTBF needs "Forced If Asynchronous" identification; default toggle rate 12.5 % of the source clock (Quartus help, B). Values are capped at "Greater than 1 Billion" years. |

## 2. What we measured

The rig is one design (`flow/tests/fixtures/cdc_margin_207/rtl/cdc207_top.v`) with every crossing type: a level and a toggle-pulse
synchroniser, a 128-deep FIFO with 8-bit Gray pointers, a 16-bit req/ack handshake (3-stage request), a 16-bit CE-captured
configuration bus and a reset release. The clocks are clk_a 100 MHz and clk_b 156.25 MHz, and each domain has a multiply-accumulate
filler. Seeded faults: B1, binary pointers crossed bit by bit; B2, a one-stage level synchroniser; B3, Gray first stages pulled to
opposite corners with clk_b at 400 MHz. Constraint variants:
- **N:** clock groups only.
- **U:** Altera-style, N plus 12.5 % of the destination period as setup and hold uncertainty.
- **D:** AMD-style per-crossing bounds.
- **DU:** D plus U's uncertainty.
- **M:** this method, D with the bounds reduced by the measured U_pair.

Every number below is in [results.md](../results/207_cdc_margin/results.md) (generated from the raw reports). Vivado 2026.1:
out-of-context implementation on xc7a35ticsg324-1L and xck26-sfvc784-2LV-c. Quartus Prime Lite 25.1std: Cyclone V 5CSEMA5F31C6
and MAX 10 10M50DAF484C7G, slow 85 C corner unless named.

**2.1 A clock-uncertainty margin is not crossing margin.**

| Effect of U's 12.5 % uncertainty | Artix-7 | K26 | Cyclone V | MAX 10 |
|---|---|---|---|---|
| on a datapath-only (Vivado) / max-delay (Quartus) crossing bound, same crossing, D against DU | none: level crossing slack 5.340 and 5.340 ns, no Clock Uncertainty line in the path | none: 6.028 and 6.028 | slack falls by the added 0.8 ns (Gray bus 7.760 to 6.960): Quartus `set_max_delay` includes uncertainty | the same, 8.651 to 7.851 |
| on the crossings themselves under clock groups (N against U) | untimed either way; under U the unbounded Gray bus routed to 3.642 ns latency and 3.227 ns skew (N: 0.915 and 0.819) | untimed; the FIFO memory read routed to 2.995 ns (N: 1.030) | untimed; `report_max_skew` analyses 0 paths with a clock group over the pair | 0 paths |
| on the rest of the design (filler) | setup WNS 4.600 to 0.746 (clk_a) and 1.530 to 0.208 (clk_b); **hold fails**: WHS -0.692 and -0.242; TIMING-44/45 raised | WNS 7.539 to 0.346 and 4.605 to 0.329; **hold fails**: WHS -1.106 and -0.656; TIMING-44/45 | WNS falls by exactly the added amount (clk_b 1.804 to 1.004) | clk_b 0.760 to **-0.040: the design now fails** |
| on MTBF (settling time) | 7-series has no report; settling slack after the Gray pointer's second stage 2.065 to 0.480 ns | overall MTBF 7.73e+79 to 1.22e+32 years (N to U); 3.77e+79 to 1.2e+34 (D to DU) | settling 7.490 to 5.890 ns; MTBF capped at 1 billion years both ways | settling 6.977 to 5.377 ns; worst-case MTBF **1e+06 to 69.1 years** |

So the Altera percentage, applied to AMD parts, fails hold on the filler of both AMD parts and adds nothing to any crossing
check. Applied in Quartus, it tightens the crossing checks, but by an amount (0.8 ns setup, 1.6 ns of skew and of settling
time) that bears no relation to what the crossing's protocol tolerates. It also fails timing and an MTBF target on MAX 10.

**2.2 The AMD-style bounds are cheap and the tool's own uncertainty is small.**
- **Cost on the rest of the design.** D against N: Artix-7 filler WNS 4.669 against 4.600 ns (clk_a), 1.530 against 1.530 (clk_b);
  K26 7.638 against 7.539 and 4.642 against 4.605. No measurable cost.
- **U_pair.** Vivado's own clock uncertainty on these crossings, two unrelated port clocks, is **0.035 ns** on both AMD families.
  M (bounds reduced by U_pair) gave the same routing as D, with every slack 0.035 ns smaller.
- **Routed skew against its bound.** Gray bus, D: 0.946 ns against 6.4 on Artix-7, 0.431 against 6.4 on the K26. Cyclone V 1.555
  to 1.945 ns over three seeds; MAX 10 0.586 to 1.379. The protocol tolerance, not a percentage, is what bounds the margin. At these
  clock rates it leaves several nanoseconds.
- **Who optimises skew.** Vivado's router does: B3 Gray bus at 400 MHz, 2.078 ns under N, 1.459 ns with the bound. The Quartus
  Standard fitter does not: fits made without `set_max_skew` routed with the same skew as fits made with it, within the seed spread
  (Cyclone V 1.200 and 1.260 ns without, 1.555 to 1.945 with).
- **Seed spread (Vivado).** The three placement directives gave identical results on this small design. No seed spread was measured
  on Vivado, so the margin figure is not supported by Vivado seed data.

**2.3 What catches the seeded faults.**

| Fault | report_cdc | cdc_structure | bus-skew / max-skew | MTBF report | injected simulation |
|---|---|---|---|---|---|
| B1 binary bus (D constraints) | CDC-6 Warning only (same as Gray) | pass ("coding unchecked") | met | every chain listed and fine | caught only with a pointer-safety check: the write pointer was seen ahead 22 to 40 cycles per seed (5 of 5); the end-to-end data check missed it in 5 of 5 |
| B2 one stage (D constraints) | **CDC-1 Critical** (gate `cdc_no_critical` fails) | passed before this brief: the datapath-only bound made the lone ASYNC_REG flop look like a handshake data path. **Fixed**: U2 now | n/a | Quartus: MTBF still over 1 billion years; "Shortest Synchronizer Chain: 1" is the signal | not caught (the counter still counts) |
| B3 bus pulled apart, 400 MHz | - | - | Artix-7: skew 1.459 against 2.5, met, **no violation could be produced** (die too small); brief 105 M3's recorded violation is the gate's negative case | - | - |

No timing check sees a bus's coding. The method leaves coding to the structural check and the injected simulation. That
simulation needs a property that observes the fault: a data check alone did not catch a pointer seen ahead for one cycle.
<!-- K26-BAD -->

**2.4 The flow's own XPM handshake rule.** A non-project build does not apply AMD's scoped XPM constraints, so `flow/xpm_cdc.tcl`
applies its own. Measured on a 16-bit `xpm_cdc_handshake` (3 sync stages) and an 8-bit `xpm_cdc_gray`, 100 to 156.25 MHz, on both
AMD parts (`raw/xpm_a7`, `raw/xpm_k26`):
- **handshake:** the flow applied `max_dpo` 10 ns (the source period) and no bus skew. AMD's 2026.1 template gives 19.2 ns for both,
  3 x 6.4 ns.
- **Gray:** max delay 10 ns and bus skew 6.4 ns, matching AMD's template.

The handshake rule now follows AMD: the destination period x the src-to-dest stages, for both, up to 100 bits; the smaller period
and no bus skew above 100 bits. That is also this method's handshake bound. After the fix: <!-- XPM-AFTER -->

## 3. The method (house rule)

**3.1 One crossing record.** Each asynchronous crossing is declared once (architecture.yaml `crossings:`, optional: the check
works without it, with the defaults below): `to` (the capture register), `type` (level, pulse, gray, handshake, ce, fifo,
reset, static), the clocks, the width and, for a handshake or CE capture, `sync_stages`. Three intents follow from the type:

| Type | Latency bound L | Skew bound S | MTBF |
|---|---|---|---|
| level, pulse (toggle) | one destination period: not needed for correctness, keeps stage 0 near its source | - | the chain counts |
| gray (FIFO pointers, counters) | source period: at most one increment in flight | min(source, destination period) | each bit's chain counts |
| handshake, ce (data held, a synchronised request enables capture) | `sync_stages` x destination period | as L | the request chain counts |
| fifo memory read | write period (Vivado distributed or block RAM); none in Quartus, which does not time through the memory array | - | the pointers' chains count |
| reset (release) | - (assertion is asynchronous) | - | the release chain counts |
| static (written before use) | - | - | a waiver with its reason |

**3.2 Mapping.**

| Intent | Vivado | Quartus Prime Standard |
|---|---|---|
| L | `set_max_delay -datapath_only L -from <src> -to <dst>` | `set_max_delay L`, `set_min_delay -L` and `set_net_delay -max L` on the same `-from/-to` (no datapath-only form works in Standard: `set_data_delay` is rejected) |
| S | `set_bus_skew S` (same `-from/-to`) | `set_max_skew S` (same `-from/-to`) |
| MTBF | `ASYNC_REG` on every stage; `report_synchronizer_mtbf` (UltraScale+); 7-series: the default `DEST_SYNC_FF` and the settling slack after each stage, recorded | "Forced If Asynchronous" synchroniser identification on each first stage; `report_metastability` (typical and worst case) |
| never | `set_clock_groups -asynchronous` or `set_false_path` over a pair that has an L or S bound (overrides `-datapath_only`, UG903 p. 131) | the same: a clock group or false path removes `set_max_skew` from analysis (measured: 0 paths) |

**3.3 Where margin goes.** Not into a clock uncertainty. Static timing already covers corners and on-chip variation. The
bounds are protocol tolerances, so the margin is the gap between the routed value and the bound, and the router or analysis
proves it after routing. The only correction is for what a tool leaves out of the check:

- **Vivado bus skew excludes clock uncertainty** (UG906 p. 163). Set S = protocol tolerance - U_pair, where U_pair is the
  clock uncertainty Vivado computes for that clock pair (the Clock Uncertainty line of `report_timing` on a crossing path).
- **Quartus `set_max_skew` includes it** (help text; measured in section 2: skew rose by twice the added uncertainty). Set
  S = protocol tolerance. Subtracting again would count it twice.
- **L** is used the same way: L = protocol tolerance (- U_pair in Vivado).
- A `set_clock_uncertainty` is used for one thing only, AMD's pre-route overconstraint of a failing clock (setup only,
  removed before routing, at most 0.5 ns: UG949 p. 283). On a crossing it is never counted as margin.

**3.4 MTBF target.** 1e9 years for the design by default (`mtbf_target_years` in architecture.yaml), judged on the
worst-case figure where the tool gives one (Quartus) and on the overall figure on UltraScale+. Below it, add a stage
(`DEST_SYNC_FF`, or a third flop) before anything else. Settling slack after the first stage is the lever. Both Vivado and
Quartus derive MTBF from it, so an uncertainty added to the destination clock lowers the reported MTBF (section 2).

## 4. How the agent checks "present and met"

`flow/build.tcl` writes `bus_skew_route.rpt` (`report_bus_skew`, every build) and `mtbf_route.rpt` (`report_synchronizer_mtbf`,
UltraScale+ parts) after routing. `flow/cdc_margin.py` reads them with `exceptions_route.rpt`, `methodology.rpt` and the
structural CDC check's inputs (`cdc_paths_synth.rpt`, `cdc_synth.rpt`):

| Code | Level | Finding | Source |
|---|---|---|---|
| CDCM-SKEW-VIOL | gate (`post_route_bus_skew_met`) | a `set_bus_skew` with negative slack after routing | UG906 p. 162: no bus-skew violation may remain |
| CDCM-SKEW-MISSING | advisory | a hand-built multi-bit crossing (structural class gray, handshake or fifo; not an XPM) that no `set_bus_skew` names | survey rank 1; UG903 pp. 142-144 |
| CDCM-DPO-LOOSE | advisory | a `max_dpo` value above the crossing's L (source period; `sync_stages` x destination period for a declared handshake or CE) | survey rank 2; AMD's XPM templates |
| CDCM-MTBF-MISSING | advisory | UltraScale+: no MTBF report, or a structural synchroniser chain missing from it | survey rank 4; UG835 |
| CDCM-MTBF-LOW | advisory | a chain or the overall MTBF below the target, or UNDEFINED | UG835 p. 1529 |
| CDCM-UNC-HIGH | advisory | TIMING-44/45: user uncertainty above what Vivado calls reasonable | UG949 p. 283 |

Only the bus-skew violation is a gate, because only it is a vendor requirement. The others are advisories until the owner
promotes them. The check runs as `cdc_margin` in the check suite (route scope) and as rule HDL-CDC-03. A build made before
brief 207 has no `bus_skew_route.rpt` and is reported as not evaluated.

For Quartus records (the agent has no Quartus flow yet) `cdc_margin.evaluate_quartus(<dir>, <corner>)` applies the same step
to `report_max_skew` and `report_metastability` text:
- QCDCM-SKEW-VIOL (gate): a `set_max_skew` with negative slack;
- QCDCM-SKEW-NONE: no skew path was analysed, so a clock group or false path cut the check;
- QCDCM-CHAIN-SHORT: a synchroniser chain shorter than 2 registers;
- QCDCM-MTBF-LOW: the worst-case design MTBF is below the target.

What no timing check can see: the coding of a bus (binary or Gray), a pulse into a level synchroniser, reconvergence. These
stay with the structural check (`flow/cdc_structure.py`) and the injected simulation (`flow/cdc_inject.py`). Section 2 shows a
binary bus passing every timing check on all four parts.

## 5. Limits and what is not yet known

- **One small design at two modest clock rates** (100 and 156.25 MHz), out of context. At these rates every bound had several
  nanoseconds of slack, so the margin question is decided by the protocol tolerance. The method's U_pair correction (35 ps here)
  matters only near the tolerance, which these runs did not reach. B3 could not produce a real bus-skew violation on the xc7a35t.
- **Seed spread** was measured on Quartus (three seeds, up to 0.8 ns of routed skew on MAX 10) but not on Vivado: the three place
  directives routed this small design identically.
- **The 10 to 15 % Altera advice was tested as applied to asynchronous crossings.** Its stated scope (snippet-level) is clocking
  schemes, which suggests timed paths between related clocks. We did not test it on related clocks, where AMD's own advice is to
  remove the source of uncertainty (UG949 pp. 259-262).
- **Quartus is analysed from records only.** The agent has no Quartus flow, so `evaluate_quartus` is a library function with tests,
  not a gate. B3 was not run on Quartus.
- **The injected simulation is pessimistic for fast-to-slow Gray buses.** On the good design the read pointer (156.25 to 100 MHz)
  was seen ahead for 1 cycle in 2 of 5 seeds. The model holds each changing bit for a whole destination cycle, independently. That
  can mix two increments, and hardware with skew below one source period cannot. A follow-up for `flow/cdc_inject.py`.
- **MTBF** default target 1e9 years is our assumption, not a vendor figure. Quartus caps its report at 1 billion years. The MAX 10
  worst-case design MTBF on the good design was 1e+06 years, which is below that target with no margin added. Whether the target
  should be stated as typical or worst case is the owner's decision.
- Not measured here: `xpm_cdc_pulse` and `xpm_fifo_async` bounds, SSI parts, UltraScale+ BUFGCE_DIV clocking.
