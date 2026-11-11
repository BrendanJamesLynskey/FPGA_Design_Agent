# Brief 36 end to end (written by e2e.py table)

Development tasks, deepagents, every role on openai/gpt-6-luna (OpenRouter, data_collection deny), interview and review off, `--stop-after 2 --verif-level V1`, cap USD 0.60 a run. Pass = every hidden-bench test passes on the run's rtl/ (benchmark/tools/run_task.py). Tokens and cost are provider-reported (summary.json). Each row is one run.

| Task | Seed | Arm | Run | Stage-2 gates | Hidden bench | Tokens | Cost USD | Stop |
|---|---|---|---|---|---|---|---|---|
| t1_debounce_bank | 1 | off | 20261110-232026-aeee | fail | fail 0/9 | 6198833 | 0.166313 | stage 2 visited more than 6 times |
| t1_debounce_bank | 1 | router | 20261110-234534-1d2b | fail | fail 0/9 | 16909644 | 0.343831 | stage 2 visited more than 6 times |
| t2_spi_master_modes | 1 | off | 20261111-003031-eec1 | pass | fail 0/10 | 3922265 | 0.098171 | done |
| t2_spi_master_modes | 1 | router | 20261111-005441-0382 | fail | fail 0/0 | 6180436 | 0.183949 | stage 2 visited more than 6 times |
| c11_nco_mixer | 1 | off | 20261111-013229-7eb2 | fail | fail 1/4 | 13150612 | 0.339773 | stage 2 visited more than 6 times |
| c11_nco_mixer | 1 | router | 20261111-031923-e05b | fail | fail 1/4 | 9926327 | 0.26425 | budget: run turns limit 300 reached (300) |

| Arm | Runs | Hidden-bench passes | Stage-2 gate passes | Mean tokens | Total cost USD |
|---|---|---|---|---|---|
| off | 3 | 0 | 1 | 7757237 | 0.6043 |
| router | 3 | 0 | 0 | 11005469 | 0.792 |

Tokens per stage (mean over the arm's runs that reached the stage):

| Arm | clarify | board-and-device-planning | rtl-design-creation |
|---|---|---|---|
| off | 59077 (n=3) | 755573 (n=3) | 6942586 (n=3) |
| router | 223176 (n=3) | 458484 (n=3) | 10323809 (n=3) |

Notes (from the runs' audit logs and score files):

- Nulls first: no run in either arm passed its hidden bench; one run (off, t2_spi_master_modes) passed the stage-2 gates
  and still scored 0/10. Three pairs cannot show a difference in pass rate, and none is claimed.
- The router arm's roles hardly used the new tools: one `skill_index` call and three `load_skill(name=...)` calls in
  three runs; `skill_excerpt` was never called. They kept calling `load_skill(sections)`.
- The off arm also called `load_skill(name=...)` once (t2_spi_master_modes): the registry change is visible with the flag
  off, as the golden-request commit says.
- Token totals are dominated by long RTL repair visits (one 80-turn visit alone used 6.6 M tokens); with one run per arm
  and task they say nothing about the shortlist's own cost, which is about 1,750 characters per role prompt.
- t2_spi_master_modes, router: the hidden bench could not build: the agent named a file `reset_sync.sv`, the name of a
  test-shell file (scored as a fail).
- t1_debounce_bank: both runs were recorded after the run (`e2e.py adopt`) because the first driver's scorer had two bugs
  (missing scores folder, then the scorer's JSON shape); the runs themselves were not repeated.
