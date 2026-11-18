# results/b97: latency as an agent skill, phase 1 (brief 97)

Records of brief 97 on the 10G design `designs/b96_kr260_10g`: the eight paired agent runs (two rounds, with and without the latency tools), the pre-registration, the four latency variants with their post-route builds and report_cdc results, and the scripts that produced them. Method and limits: [docs/latency_reduction.md](../../docs/latency_reduction.md); phase 2 plan: [docs/latency_phase2_plan.md](../../docs/latency_phase2_plan.md).

## Records
- `preregistration.md`: protocol and the round-2 addendum (written after round 1; the addendum is not strictly pre-registered, see Known gaps).
- `paired/<run>/`: `history.jsonl`, `summary.json`, per-visit diffs and kept RTL of runs A0_1, A0_2, A1_1, A1_2; `ab_summary.md`/`.json` the table. Transcripts are private (knowledge bank repo, `runs_b97/`).
- `round2_start.patch`: the round-2 start state (the 9-clock RTL plus the updated stage file). Round 2 starts from the round-1 result (9 clocks).
- `board_session.txt`, variants `designs/b96_kr260_10g/lat_*`: bitstreams to measure in one board session (built; the `.bit` files are local, git-ignored).
- `builds/<variant>/`: digest.json (timing, utilisation, power, gates), slack.json (per-stage post-route slack), run.json; `postroute.md`/`.json` the table; `cdc/`: report_cdc, clock interaction and pulse-path timing per variant and the 96 baseline.
- `build_variant.sh`, `cdc_all.sh`, `queue.sh`, `vivado_probes.sh`, `phase2_probe.tcl`, `gt_bypass_probe.tcl`: heavy-slot Vivado jobs; `phase2_probe.txt` is Vivado's help and property tables (the GT bypass probe failed, see the plan).

## Measured
Simulation clocks (GT word holding the price to GT word holding the order start block), baseline 11: all four round-1 runs ended at 9 with bench and twin passing, using the same two edits. Round 2 (start 9): both A0 runs reached 8 (the order-only early MAC start); both A1 runs stayed at 9. Post-route: all four variants meet timing, see `postroute.md`; report_cdc is identical to the baseline's.
Cost per run: see the usd column of ab_summary.md (provider-reported, openai/gpt-6-luna).

## Reproduce
`python -m agent latency <frozen worktree> --arm A1|A0` (needs the access key and the private prompts); `python3 results/b97/summarise_runs.py`. No heavy slot for the loop (simulation only); the builds need one.

## Known gaps and limits
No board result (needs a board session). The arms are indistinguishable on the outcome (k = 2, same edits). Simulation is in-phase; the changed crossing has no MTBF or injection evidence. See the limits section of docs/latency_reduction.md.
