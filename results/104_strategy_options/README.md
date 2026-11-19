# results/104_strategy_options: back-tests of the strategy options generator (brief 104)

`python -m agent improve <design> "<request>"` analyses a loaded design (read-only) and offers two to four strategies; nothing changes until `--choose N`.
This folder holds the two designs on which the answer was already known, the pre-registration, the runs and their scores. Concept, schema and limits:
[docs/strategy_options.md](../../docs/strategy_options.md); report: `reports/104_strategy_options_report.md` in the planner's hand-off folder.

## Records

- `preregistration.md`: the question, the arms, the scoring rules and the stopping rule, written before any scored run.
- `backtest/b96_10g_pre97/`: the KR260 10G design as it was at the start of brief 97 (RTL copied from `designs/b96_kr260_10g/pre96c/rtl`, a component split written for this
  fixture, the 97-era stage file, the recorded simulation clocks, post-route reports of the 96 build). No result of brief 97 is in it (the CDC summary file's banner names the path it was first written to, which is under `results/b97/cdc`; its contents are the baseline's).
- `backtest/c16_montgomery_200mhz/`: the course task c16 (bit-serial Montgomery multiplier) at 200 MHz, with the failing build's digest only.
- `backtest/truth/`: what the earlier measurements showed. The analysis never reads this folder.
- `backtest/runs/<case>__<arm>__<k>/`: one run each: `strategy.json` (the record: request, analysis hash and sources, options offered, rejected options with reasons, model identity,
  prompt hashes), `model_calls.jsonl` (one row per model call), `stdout.json`, `meta.json`.
- `backtest/results.json` and `backtest/RESULTS.md`: the scores, computed by `flow/options/backtest.py`. Arms A, B and the c16 arm are pre-registered; A2 and B2 are the exploratory re-run with a revised prompt.
- `dev_run/`: the one development run (request "reach a higher clock rate" on `designs/b102_managed_fcs`) used to shape the prompts before the pre-registration.

## Reproduce

Needs the access key (`.env`), the private prompts (`FDA_PROMPTS_DIR` at the commit pinned in `agent/core/prompts_pin.json`) and the `claude` CLI at 2.1.321 on the plan.
No Vivado, no board, no heavy slot.

```
python3 results/104_strategy_options/run_backtest.py run     # nine live runs, sequential (skips runs already recorded); add --explore for the A2/B2 arms
python3 results/104_strategy_options/run_backtest.py score   # score the records (no model call)
python -m agent improve results/104_strategy_options/backtest/b96_10g_pre97 "lower latency" --build-dir results/104_strategy_options/backtest/b96_10g_pre97/evidence --out /tmp/x
```

Model replies differ between runs, so a rerun gives its own options; the committed scores are of the committed runs, and `agent/tests/test_104_options.py` re-scores them and re-checks each option.

## Known gaps and limits

- The stage file's `why` and `remove_risk` texts name mechanisms (for example that fewer synchroniser flops cost metastability margin), in the blind arm too; the blind arm withholds only the `technique` and `removable` fields.
- Combinations of changes (hand_ref, agent_both, all3) were never offered in any of 12 runs, with the original or the revised prompt. Three runs per arm: counts, not rates. One model (Claude Sonnet 5.5). The 97 agents were a different model (luna).
- The component split of the fixtures is this brief's own; the real design has one owned component.
- The development run (`dev_run/`) is on a different design and a different request, and is not scored.
- `in_range` is a weak test: the checker caps a gain at the stage's removable clocks, which for `cross_go` equals the measured cut, and four of the six agent_cdc ranges start at 0. The width of the
  range above the measurement is reported beside it (`RESULTS.md`).
- The c16 match is by scope (`montgomery_core` is where the worst path is, so it is nearly forced); two of three found options were guesses and one did not name carry-save.
- The run records (`backtest/runs/`) are committed with `git add -f` (the folder name is git-ignored elsewhere). The analysis hash definition gained component file hashes after the runs; the test compares the input files instead.
