# results/207_cdc_margin: one clock-crossing timing method for AMD and Altera (brief 207)

Owner's question (2026-11-24): "Clock-crossing margins: can we develop our own method that combines the two?"
Altera's Design Recommendations suggest clock uncertainty of 10 to 15 % of the clock delay. AMD removes the sources of
uncertainty and constrains each crossing with `set_max_delay -datapath_only`, `set_bus_skew` and the XPM synchroniser
constraints. This folder holds the plan, the pre-registration, the scripts and the measured records for a method that
keeps what is sound in both.

Status: **plan and pre-registration only** (2026-11-24 17:35 GMT). The planner has paused all compiles while the PC is
overloaded (load 9, swap full), so no run has been made yet. Every "expected" line below was written before any run.

## Records

None yet. Each run will write `raw/<tool>_<family>_<design>_<variant>/` with its reports, and `results.md` will be
generated from those files by `summarise.py`. No number goes into the method doc, the KB or the agent unless it is in
`results.md`.

## 1. What each vendor says (sources read so far)

Tags: **B** = from body text I read; **S** = from a search snippet only; **T** = from a section title only.

| # | Vendor claim | Source | Tag |
|---|---|---|---|
| V1 | `set_bus_skew` bounds the spread of capture times across the paths of one constraint. It is an assertion, not an exception, so it does not change exception precedence. Only `route_design` optimises for it, and `report_timing_summary` does not report it. | UG903 v2025.2 ch. 6, pp. 142-143 | B |
| V2 | The bus-skew value should be realistic: larger than half the smaller of the two clock periods. For a Gray bus, use the destination period (example: 5 ns source, 2.5 ns destination gives 2.5 ns). For a CE or handshake capture, use the number of stages times the destination period (example: 4 x 2.5 = 10 ns). Each constraint covers at least two startpoints and two endpoints, with fan-out 1. | UG903 v2025.2 ch. 6, pp. 143-144 | B |
| V3 | `-datapath_only` drops clock skew from the slack, makes the hold check a false path, and needs `-from`. A `set_clock_groups` overrides it, so a crossing with a delay bound cannot sit inside an asynchronous clock group. | UG903 v2025.2 ch. 5, pp. 129-131 | B |
| V4 | `report_bus_skew` leaves clock uncertainty out of the skew, because both paths are analysed on the same clock edge. The header shows the worst uncertainty. The check runs at the slow and fast corners, but not across corners. | UG906 v2025.2 ch. 5, pp. 161-163; UG903 p. 142 | B |
| V5 | Extra margin goes in through `set_clock_uncertainty`, which adds to the jitter the tool computes. Apply it in both directions between two clocks. Overconstrain only the clocks that fail, use `-setup` only, remove it before routing, and never go beyond 0.5 ns. TIMING-44 and TIMING-45 warn when user uncertainty is too high. | UG949 v2025.2 pp. 159-160, 282-283; UG906 App. A pp. 376-377 | B |
| V6 | MTBF depends on the number of crossings, the stages per crossing, the destination frequency and the source toggle rate. On 7-series, take the default `DEST_SYNC_FF` and analyse further only for critical designs. On UltraScale, iterate with `report_synchronizer_mtbf`. | UG949 v2025.2 pp. 141-145 | B |
| V7 | `report_synchronizer_mtbf` works on UltraScale only, not 7-series. It finds a chain only through `ASYNC_REG`. Settling time is the total positive slack on the paths out of the synchroniser registers. MTBF is UNDEFINED when a clock is unconstrained, when a chain register has a timing violation, or when the toggle rate is zero. The default warning threshold is 1e+12. | UG835 v2025.2 pp. 1528-1530 | B |
| V8 | AMD's shipped XPM constraints (Vivado 2026.1, `data/ip/xpm/xpm_cdc/tcl/`). `single`, `array_single` and `sync_rst`: false path to stage 0, so the latency has no bound. `async_rst`: false path through `src_arst`. `gray`: max delay datapath-only at the source period, plus bus skew at min(source, destination). `handshake` and `low_latency_handshake`, up to 100 bits: max delay and bus skew both set to destination period x the number of src-to-dest sync stages; above 100 bits, max delay at min(periods) and no bus skew. `xpm_cdc_pulse` ships no file. | read from the installed files (not copied) | B |
| L1 | Altera's Design Recommendations suggest setup and hold clock uncertainty of 10 to 15 % of the clock delay. The surrounding text is about variable delay between clock domains, in the "Optimizing Clocking Schemes" section, which also says to use a FIFO for transfers between clocks. **The text seems to address timed paths between related clocks, not asynchronous crossings. Unconfirmed.** | QPS Design Recommendations 18.1 to Pro 25.1, "Optimizing Clocking Schemes"; brief 204 study L08 read 18.1 in body | B (18.1 via 204), S (scope) |
| L2 | `set_max_skew` analysis includes data arrival, clock arrival, register micro-parameters, **clock uncertainty**, on-die variation and CCPP removal. `set_false_path` and `set_clock_groups` affect it; `set_max_delay`, `set_min_delay` and `set_multicycle_path` do not. Options: `-get_skew_value_from_clock_period {src,dst,min}_clock_period` and `-skew_value_multiplier`. Reported by `report_max_skew`. Whether the fitter optimises for it is not stated. | Quartus help 20.2, `::quartus::sdc_ext set_max_skew` | B |
| L3 | `set_net_delay` bounds net delay only (`-max`/`-min`). Its value can come from `-get_value_from_clock_period` with `-value_multiplier`. Reported by `report_net_delay`. | Quartus help 20.2, `set_net_delay` | B |
| L4 | Pro guide, "Constraining CDC paths": keep CDC paths short with `set_net_delay` and add `set_max_skew` on buses. `set_max_skew` does not constrain the fitter. `set_data_delay` constrains whole paths through logic, while `set_net_delay` does not apply across combinational logic. Asynchronous clock groups do not override data delay. False paths stop overriding it from 21.3. | Pro Timing Analyzer 683243 (22.1 to 25.3) | S |
| L5 | `report_metastability` lists synchroniser chains. Per-chain MTBF needs "Synchronizer Identification" set to Forced If Asynchronous or Forced. The design MTBF needs timing met. The default toggle rate is 12.5 % of the source clock. It gives typical and worst-case MTBF. "Synchronization Register Chain Length" defaults to 2. | Quartus help 18.1, `::quartus::sta report_metastability` | B |
| L6 | Synchroniser Toggle Rate assignment: set on the first register of a chain, in transitions per second; 0 excludes the chain. | Quartus help 25.1; Settings File Reference | S |

Not yet found in body text: whether `set_data_delay` exists in Quartus Standard 25.1std (the 20.2 help has no page for it),
which Lite families `report_metastability` characterises, and whether the Standard fitter optimises for `set_max_skew`.
The experiments settle all three.

## 2. The method to be tested (draft; the final version goes in `docs/cdc_margin_method.md`)

Each crossing gets one vendor-neutral record (planned home: `architecture.yaml` `crossings:`): type, source and
destination clocks, width, protocol, sync stages, and three intents:

- **latency bound** `L`: the largest source-to-first-stage delay the protocol tolerates;
- **skew bound** `S`: the largest spread of capture times across the bits that the protocol tolerates;
- **MTBF target** `M`: per design, default 1e9 years at the destination's worst corner, stated as an assumption.

The protocol tolerance per type, before margin:

| Type | Latency `L` | Skew `S` | MTBF | Vivado | Quartus |
|---|---|---|---|---|---|
| single-bit level | none needed for correctness; bound at one destination period so the placer keeps stage 0 near | n/a | the chain counts | `set_max_delay -datapath_only` to stage 0 (not a false path), or XPM single | `set_net_delay -max` to stage 0 (+ a cut of the timed check) |
| pulse (toggle) | as level | n/a | the chain counts | as level | as level |
| multi-bit Gray (FIFO pointers) | source period (at most one increment in flight) | min(src, dst) period | each bit's chain counts | `set_max_delay -datapath_only` + `set_bus_skew` | `set_net_delay`/`set_max_delay` + `set_max_skew` (**no clock group over it**) |
| multi-bit handshake | N_sync x dst period (data held while the request crosses) | as `L` | the request chain counts | as Gray, AMD 2026.1 values | as Gray |
| reset release | n/a (assertion asynchronous) | n/a | the release chain counts | false path through the reset input, recovery/removal timed on the release | same |
| quasi-static | none (data must be proven stable: a written-before-use rule) | none | none | waiver with a stated reason | waiver |

**Where margin goes (hypothesis to be tested, not yet a rule).** Static timing already covers process, voltage and
temperature corners and on-chip variation. It leaves two things out:

1. Vivado's bus skew excludes clock uncertainty (V4), so destination jitter is not in the skew check.
2. Neither tool's latency or skew check includes the resolution time of the first stage.

The draft rule is to take margin from the measured, tool-computed uncertainty of the clock pair (`Clock Uncertainty`
in the path header), not from a percentage:

- Vivado: `S_set = S - U_pair`, where `U_pair` is the computed inter-clock uncertainty Vivado reports for that crossing.
- Quartus, where `set_max_skew` already includes uncertainty (L2): `S_set = S`. Subtracting it again would count it twice.

A user `set_clock_uncertainty` is never used as CDC margin. On a crossing that is cut it has no effect, and on a
`-datapath_only` path it may have none. Experiments E1 to E4 test both.

## 3. Pre-registration (written 2026-11-24 17:35 GMT, before any run)

### Designs (small, hand-written, our own RTL; no benchmark or held-out material)

One top per family with four crossings between two asynchronous clocks (`clk_a` 100 MHz, `clk_b` 156.25 MHz), plus
filler logic in each domain (a pipelined 32-bit multiply-accumulate chain, sized to sit within about 0.5 ns of each
clock's period on the device), so that the timing cost on the rest of the design can be seen:

- **C1** a 2-FF level synchroniser (`ASYNC_REG`) and a toggle pulse synchroniser;
- **C2** an 8-bit Gray pointer pair (a hand-built asynchronous FIFO, 16 deep);
- **C3** a 16-bit req/ack handshake (3-stage request sync);
- **C4** a 16-bit configuration bus with a skew bound (a CE-captured bus).

Seeded bad variants:

- **B1** C2 with binary pointers crossed bit by bit;
- **B2** C1 with one synchroniser stage;
- **B3** C4 with the endpoints pulled apart (pblock or LOC) so the routed skew exceeds the bound.

Parts: `xc7a35ticsg324-1L` and `xck26-sfvc784-2LV-c` (Vivado 2026.1, out of context, one thread); `5CSEMA5F31C6`
(Cyclone V) and `10M50DAF484C7G` (MAX 10) in Quartus Prime Lite 25.1std. Cyclone IV E (`EP4CE22F17C6`) is the fallback
if a part is not in the Lite install.

### Constraint variants per design

- **N**, no margin: a crossing-shaped baseline. Vivado: `set_clock_groups -asynchronous` only. Quartus: the same.
- **U**, Altera-style: N plus `set_clock_uncertainty` (setup and hold) of 12.5 % (the middle of 10-15 %) of the
  destination period on both clocks and between them.
- **D**, AMD-style: per crossing `set_max_delay -datapath_only` (or `set_net_delay` in Quartus) at `L`, plus
  `set_bus_skew` (or `set_max_skew`) at `S` on C2, C3 and C4; a false path or net bound to stage 0 on C1; no clock group.
- **D+U**: D plus U's uncertainty.
- **M**, the draft method: D with `S` reduced by the measured `U_pair` (Vivado only; Quartus M = D).

Three placer seeds (Vivado `place_design` directive variation, or Quartus `SEED` 1-3) for D and M on each family, to
measure the spread that any margin has to cover. One seed for the other variants.

### Measures

Per crossing: worst routed latency (max datapath delay to stage 0), worst bus skew (`report_bus_skew` / `report_max_skew`),
MTBF (`report_synchronizer_mtbf` on K26; `report_metastability` typical and worst on Altera; a hand estimate from
settling slack on Artix-7), and the methodology/CDC findings. Per design: WNS and TNS of the filler logic in each domain.
Run time and peak memory.

### Expectations (each to be marked held / failed in `results.md`)

- **E1 (Vivado, datapath-only and uncertainty).** A user `set_clock_uncertainty` between the two clocks does **not**
  change the slack of a `set_max_delay -datapath_only` path (D against D+U: same slack within 1 ps). Confidence moderate;
  UG903 does not say either way.
- **E2 (Vivado, bus skew and uncertainty).** `report_bus_skew` actual and slack are the same in D and D+U (V4).
- **E3 (Vivado, MTBF and uncertainty).** On K26, D+U lowers the reported MTBF of every chain against D, because the
  settling slack out of the stages shrinks by the added destination uncertainty (V7). The overall MTBF falls by at least
  one decade.
- **E4 (Quartus, skew and uncertainty).** In Quartus, U's uncertainty **does** reduce `report_max_skew` slack by about
  the added uncertainty (L2: clock uncertainty is included). This is the asymmetry the method has to handle.
- **E5 (Quartus, clock groups hide skew).** With `set_clock_groups -asynchronous` over the pair, `report_max_skew`
  reports no paths for C2/C4 (L2: clock groups affect it), so a Quartus flow that cuts with clock groups loses its skew
  check silently.
- **E6 (Quartus, fitter and skew).** In Quartus Standard the fitter does not optimise for `set_max_skew`: routed skew is
  the same with and without it, within seed noise.
- **E7 (Altera MTBF support).** `report_metastability` gives per-chain MTBF on Cyclone V with Forced If Asynchronous.
  MAX 10: unknown; I expect chains listed, MTBF possibly missing.
- **E8 (cost of U).** U costs filler WNS: each domain's WNS falls by about the added uncertainty (12.5 % of the period:
  about 1.25 ns at 100 MHz, 0.8 ns at 156.25 MHz). Above 0.5 ns, U triggers TIMING-44/45 in Vivado. D costs the filler
  nothing measurable (within 50 ps).
- **E9 (U hides nothing new and catches nothing new).** U does not flag B1, B2 or B3 in any tool: with clock groups the
  crossings are not timed. D catches B3 (negative bus-skew slack) but not B1 (constraints cannot see coding). B1 is caught
  only by the structural check (`cdc_structure`: "gray, coding unchecked" is a pass, so I expect it **not** caught there
  either) and by `cdc_inject` simulation. B2 is caught by `cdc_structure` U2 and by the K26 MTBF report, where the chain
  is missing.
- **E10 (latency).** Under N, routed latency is unbounded by any check. Its worst value is still small (under 2 ns)
  because the design is small, so N looks fine on a small design. This is the strongest counter-case to "bounds matter",
  and B3 exists to break it.
- **E11 (margin size).** On D, the seed-to-seed spread of the routed bus skew is under 0.2 ns. The computed inter-clock
  uncertainty `U_pair` is 0.1 to 0.3 ns on both AMD families. So the measured margin the method needs is a few hundred
  picoseconds, far below the 1.25 ns that 12.5 % of a 100 MHz period gives.

Stopping rules: each variant runs once per seed. A tool error is fixed and rerun once. A part missing from the install
is replaced by the fallback and recorded. No variant is dropped because its result is inconvenient.

## 4. Agent output planned

- `docs/cdc_margin_method.md`: the method (vendor said / measured / inferred / house rule).
- A new check module `flow/cdc_margin.py` (not `flow/standards_check.py`, which brief 205 is changing; not brief 204a's
  checks, whose scope is study ranks 1, 2, 5 and 11-14 and whose branch has no commits yet). It covers survey ranks 1, 2
  and 4 (bus-skew present and met, datapath-only value within the crossing's bound, MTBF present and over target on US+),
  plus a user-uncertainty rule (a `set_clock_uncertainty` on a CDC clock pair is never counted as CDC margin, and is at
  most 0.5 ns). It will have parsers for Quartus `report_max_skew` and `report_metastability` text and tests on the
  recorded fixtures. `flow/build.tcl` will gain `report_bus_skew` and, on US+, `report_synchronizer_mtbf`.
- Expertise.yaml `cdc` evidence; a KB skill PR; family-matrix rows (AMD against Altera; 7-series against US+).

## Reproduce

To be written with the scripts (`run_vivado.sh`, `run_quartus.sh`, `summarise.py`) once the compile pause is lifted.
Each compile takes a heavy slot through `_handoff/take_heavy_slot.sh` (light synthesis class does not apply: these runs
place and route).

## Known gaps and limits

- No run has been made yet; everything above is a plan.
- The Altera documentation site redirects to a script viewer and its PDFs return 403. The Altera text comes from the
  Quartus Tcl help pages (resources.altera.com, 18.1 and 20.2) and from search snippets of the Standard 18.1 and Pro
  guides. Claims tagged S are not body text.
- Out-of-context Vivado runs have no I/O timing. The crossings are internal, so this does not affect them, but filler
  WNS is internal paths only.
