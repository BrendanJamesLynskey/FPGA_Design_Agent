# results/b97: latency as an agent skill, phase 1 (brief 97)

Records of brief 97 on the 10G design `designs/b96_kr260_10g`: the four paired agent runs (with and without the latency tools), the pre-registration, the latency variants prepared for a board session, and the scripts for the post-route builds that were queued but not finished when this was written. Method and limits: [docs/latency_reduction.md](../../docs/latency_reduction.md); phase 2 plan: [docs/latency_phase2_plan.md](../../docs/latency_phase2_plan.md).

## Records
- `preregistration.md`: protocol and the round-2 addendum (written after round 1; the addendum is not strictly pre-registered, see Known gaps).
- `paired/<run>/`: `history.jsonl`, `summary.json`, per-visit diffs and kept RTL of runs A0_1, A0_2, A1_1, A1_2; `ab_summary.md`/`.json` the table. Transcripts are private (knowledge bank repo, `runs_b97/`).
- `round2_start.patch`: the round-2 start state (the 9-clock RTL plus the updated stage file). Round-2 results are not committed (runs were unfinished).
- `board_session.txt`, variants `designs/b96_kr260_10g/lat_*`: bitstreams to measure in one board session (not built yet).
- `build_variant.sh`, `vivado_probes.sh`, `queue.sh`, `phase2_probe.tcl`, `gt_bypass_probe.tcl`: heavy-slot Vivado jobs (not run: both slots were held by other sessions).

## Measured
Simulation clocks (GT word holding the price to GT word holding the order start block), baseline 11: all four paired runs ended at 9 with bench and twin passing, using the same two edits.
Cost per run 0.015 to 0.024 USD (provider-reported, openai/gpt-6-luna).

## Reproduce
`python -m agent latency <frozen worktree> --arm A1|A0` (needs the access key and the private prompts); `python3 results/b97/summarise_runs.py`. No heavy slot for the loop (simulation only); the builds need one.

## Known gaps and limits
No post-route result, no board result. The arms are indistinguishable on the outcome (k = 2, same edits). Simulation is in-phase; the changed crossing has no MTBF or injection evidence. See the limits section of docs/latency_reduction.md.
