# Candidate tournaments (brief 178)

Run several variants of one block, keep the best, record why the rest were dropped. Two stages: synthesis candidates, then place-and-route candidates.
Tool: `python3 -m flow.tournament` ([flow/tournament.py](../flow/tournament.py)); tests: `flow/tests/test_178_tournament.py`; measured results:
[results/178_tournament/README.md](../results/178_tournament/README.md).

## Step 0: triage, before any candidate runs

`python3 -m flow.tournament triage <spec.yaml> [--default-wns <ns>]` decides `easy` (default flow only), `marginal` (synthesis tournament) or `hard`
(synthesis plus place-and-route tournament). Cheapest signal first; every decision is printed with its reasons.

| signal | when | rule (thresholds in `TRIAGE`, flow/tournament.py) |
|---|---|---|
| target clock against the nearest rows of the 177 dataset | before synthesis, free | target MHz / median routed Fmax (1000 / (clock - routed WNS)) of the same function and part: >= 1.00 `hard`, 0.85 to 1.00 `marginal`, below 0.85 `easy`; fewer than 3 rows: `unknown` |
| estimated WNS of ONE default synthesis | after one cheap run | >= +0.50 ns `easy`, below -0.30 ns `hard`, between `marginal`; it overrides the first signal; `unknown` if no constrained path |

Not yet used (no data to set a threshold): expected DSP/BRAM count, wide muxes, long carry chains, many clock domains. Thresholds change only with a
dated note and the measurement in results/178_tournament/README.md.

## Synthesis menu (all documented AMD options, UG901 / `synth_design -help`)

`default`, `perf` (-directive PerformanceOptimized), `area_high` (AreaOptimized_high), `altroute` (AlternateRoutability), `runtime` (RuntimeOptimized),
`carry` (FewerCarryChains), `flat_full`, `flat_none` (-flatten_hierarchy), `retime`, `perf_retime` (-retiming), `fsm_onehot` (-fsm_extraction one_hot),
`shreg5` (-shreg_min_size 5), `keep_eq` (-keep_equivalent_registers), `no_share` (-resource_sharing off), `dsp0` (-max_dsp 0), `fanout50` (-fanout_limit 50),
`fanout_nets` (MAX_FANOUT 50 on `spec.fanout_nets`; skipped, with the reason recorded, when the spec names none). `default` always runs: it is the reference.

## Implementation menu

`default`, `explore`, `extra_timing` (place ExtraTimingOpt, phys_opt AggressiveExplore), `extra_netdelay` (ExtraNetDelay_high, route NoTimingRelaxation),
`aggressive`, `congestion` (AltSpreadLogic_high, AlternateCLBRouting), plus AMD's own `-strategy` sets as `amd:<name>` entries. Those are **measured from
Vivado** by `python3 -m flow.tournament strategies` (every strategy's step directives, raw in results/178_tournament/strategies_raw.tsv), not recalled.

## Score (tie-broken, documented in `score_key`)

1. a failed or missing run ranks last; 2. WNS in 0.05 ns buckets, higher first (differences below that are inside the placement noise measured in the report);
3. fewer LUT+FF; 4. fewer logic levels on the worst path; 5. menu order, so on a complete tie the default wins and nothing changes without evidence.
The 177 predictor `rule_v0` is a step function of the same WNS, so it is recorded (`p_pass`) but adds no ordering. Every candidate is kept in
`tournament.json` with `rank`, `kept` and `dropped_because`; each prediction is appended to `build/tournament/tournament_log.jsonl` and `score` joins it with the routed outcome.

## Resource rules (owner decision 32, 2026-11-22)

* **Synthesis stage (light class):** the tournament takes ONE heavy slot whose text names it and its declared total peak (`178: tournament <design> synth, ... total peak <N>G`),
  then fans out up to 4 children under it. Each child: `systemd-run --user --scope -p MemoryMax=2G`, `nice -n 15`, one Vivado thread, declared peak 2 GiB or less.
  Before every launch `may_launch` checks fewer than 4 children and MemAvailable >= every running child's peak + this child's peak + 8 GiB.
* **Implementation stage:** normal rule (CLAUDE.md section 4): one slot, one Vivado at a time, never fanned out.
* No change to how any other job takes a slot; the slot is released only if its text is ours.

## Agent hook (shadow or opt-in only)

The agent runs `triage` first. `easy`: nothing more. `marginal` or `hard`: a tournament may be run **only** when the run is in shadow mode (results logged, the
default flow's result is the one used) or the owner or spec opts in (`tournament: true`). It never replaces the default result silently, never gates a build,
and the `p_pass` log feeds brief 177's shadow data. Nothing is wired into the gates.
