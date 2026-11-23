# results/195_repro_examples: reference runs of the reproducible examples (brief 195)

Four development tasks, each run three times with the pinned setup of `agent/repro/examples.yaml` on 2026-11-23, plus what was measured about which results repeat.
How to use the examples: [docs/reproducible_examples.md](../../docs/reproducible_examples.md). Every number below is produced from the committed records by
`python results/195_repro_examples/summarise.py`; nothing is typed in by hand and no model produced a score.

## Pinned setup (all 12 runs)

`claude-sonnet-5-5` (effort medium) for clarify, model, tests and RTL; `claude-haiku-5-5` for the interview oracle; Claude Code 2.1.321 from a pinned copy (SHA-256 `426c33815ca6...`),
auto-update off; harness arm H1, verification level V2, docs off, stopped after stage 6 (timing closure); Vivado 2026.1; knowledge repository and prompt manifest at commit
`5e2eab87048b` (manifest SHA-256 `bd02d116f4f7`); hidden bench scored by Icarus Verilog and cocotb, seed 1. No seed or temperature exists to pin for Claude Code on a subscription.
Cost is the plan's estimate, not a bill. Gray stepper run 1 was a trial of the same command with run name `ex_trial_gray`, made before the `example` command existed in its final
form and finished afterwards with `example finish`; its agent code differs from the others only in files outside the agent run itself.

## Reference runs

| example | runs | hidden tests passed | agent's own gates passed | distinct RTL | LUT min/med/max | worst setup slack ns | repair loops | wall min | cost USD |
|---|---|---|---|---|---|---|---|---|---|
| elevator_fsm | 3 | 0/3 | 2/3 | 3 | 460 / 470 / 479 | 2.440 / 3.019 / 3.599 | 3 / 5 / 15 | 24 / 37 / 40 | 2.47 / 3.75 / 4.21 |
| gray_stepper | 3 | 3/3 | 3/3 | 3 | 431 / 452 / 466 | 2.485 / 2.651 / 3.275 | 2 / 2 / 3 | 27 / 33 / 41 | 2.62 / 2.75 / 3.22 |
| median3x3 | 3 | 1/3 | 2/3 | 3 | 1034 / 1071 / 1108 | 3.091 / 3.168 / 3.244 | 1 / 3 / 7 | 22 / 44 / 47 | 1.99 / 2.42 / 4.37 |
| pattern_sequencer | 3 | 0/3 | 0/3 | 3 | 664 / 670 / 676 | 1.062 / 2.092 / 3.122 | 7 / 8 / 15 | 24 / 45 / 49 | 3.56 / 4.82 / 5.11 |

| example | run | hidden tests | own gates | stop | RTL hash | LUT | FF | setup slack ns | build stamp | loops | turns | tokens | cost USD | wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| elevator_fsm | ref_1 (20261123-140256-2143) | 3/9 | yes | done | cec900fb | 479 | 334 | 3.599 | 27e1c35f | 3 | 96 | 2077831 | 2.4693 | 1428.0 |
| elevator_fsm | ref_2 (20261123-144401-0a84) | 4/9 | yes | done | b347a3d2 | 460 | 335 | 2.44 | 12dcb743 | 5 | 135 | 3332902 | 3.7538 | 2239.4 |
| elevator_fsm | ref_3 (20261123-154810-6c81) | 1/9 | no | stage 2 visited more than 6 times | e707d8cf | None | None | None | 4c77fdb2 | 15 | 220 | 5062770 | 4.2068 | 2415.7 |
| gray_stepper | ref_1 (20261123-125129-47ee) | 9/9 | yes | done | 0736b834 | 452 | 378 | 2.485 | a36da003 | 3 | 102 | 1936434 | 2.6239 | 2436.6 |
| gray_stepper | ref_2 (20261123-141646-71e5) | 9/9 | yes | done | 01ff922a | 431 | 370 | 3.275 | 61d5e982 | 2 | 102 | 2680530 | 2.7522 | 1613.4 |
| gray_stepper | ref_3 (20261123-151451-66e3) | 9/9 | yes | done | 3e344b83 | 466 | 377 | 2.651 | cd25019c | 2 | 122 | 3507833 | 3.2168 | 1977.4 |
| median3x3 | ref_1 (20261123-133255-b7e6) | 2/4 | yes | done | 5171392d | 1108 | 1091 | 3.244 | 920877ac | 3 | 116 | 2108830 | 2.4176 | 2622.5 |
| median3x3 | ref_2 (20261123-142655-eb0e) | 4/4 | yes | done | a6f74fe4 | 1034 | 1084 | 3.091 | 5502baa9 | 1 | 109 | 2169819 | 1.9948 | 2811.3 |
| median3x3 | ref_3 (20261123-152133-5ca0) | 0/4 | no | stage 2 visited more than 6 times | 56fec020 | None | None | None | None | 7 | 179 | 4531353 | 4.3654 | 1338.5 |
| pattern_sequencer | ref_1 (20261123-163230-0bb7) | 9/11 | no | done | 024b7649 | 664 | 748 | 3.122 | ff65c615 | 7 | 129 | 3133097 | 3.5613 | 2708.6 |
| pattern_sequencer | ref_2 (20261123-171801-da63) | 9/11 | no | done | 1eadd379 | 676 | 754 | 1.062 | 74478eb1 | 15 | 255 | 6059750 | 5.1133 | 2948.3 |
| pattern_sequencer | ref_3 (20261123-180733-7d83) | 9/11 | no | stage 2 visited more than 6 times | d9211b38 | None | None | None | None | 8 | 175 | 4103903 | 4.8166 | 1451.1 |

Hidden tests passed is the verdict that matters. "Own gates" is the agent's own stage gates: a run that stopped at stage 2 after six visits, or whose post-route build had a failing gate,
does not pass them. Wall time and cost are per run (two runs were often in progress at once on this PC, which lengthens wall time).

### What repeated and what did not

- **The outcome repeated for three of the four examples and varied for one.** Gray stepper: 3/3 pass. Elevator: 0/3 pass, and the same five bench tests (`test_scan_keeps_direction`,
  `test_call_on_the_way_and_behind`, `test_call_at_current_floor`, `test_shell_calls_and_register_rules`, `test_random_calls`) failed in all three runs. Pattern sequencer: 0/3 pass, the same
  two tests (`test_one_shot_holds_last`, `test_start_is_from_entry_zero`) failed in all three runs. Median filter: 1/3 pass (2/4 and 0/4 in the other two). A reproducible *failure* is a result too: in
  the elevator, the failing assertions are cycle-exact timing the request does not fix (for example "took 1 clocks, model 0"); it is the agent's gates passing while the hidden bench fails (an escape,
  `tools/run_record.py`) in two of three elevator runs.
- **The RTL never repeated:** 12 runs, 12 different RTL hashes. Lines of RTL, repair loops, tokens, cost and wall time spread widely (table above): a model-dependent quantity, as expected.
- **Resources and slack are close but not equal:** within an example, LUTs vary by about 5 % (gray 431 to 466) and worst setup slack by about 0.8 ns, because the RTL differs.
- **The bench is deterministic:** `bench_recheck.py` re-scored every stored RTL, with every verdict equal to the record in 12 of 12 references (`bench_recheck.json`), including the failing ones.
- **Vivado repeats for the same sources at the same path, and not at another path** (`vivado_rebuild.py`, `vivado_rebuilds.json`; no build cache, to post-route, Vivado 2026.1):

| rebuild | path | result |
|---|---|---|
| gray_stepper ref 2 | the original relative path | build stamp, LUT, FF, DSP, BRAM, setup and hold slack all equal to the record |
| elevator_fsm ref 1 | the original relative path | all equal |
| median3x3 ref 2 | the original relative path | all equal |
| pattern_sequencer ref 1 | the original relative path | all equal |
| gray_stepper ref 2 | another path (`runs/_tools/...`) | stamp `61d5e982` to `b7153688`; LUT 431 to 425; setup slack 3.275 to 3.835 ns |
| median3x3 ref 2 | another path | stamp `5502baa9` to `e58a02c8`; setup slack 3.091 to 3.055 ns; hold slack 0.131 to 0.049 ns |

  The cause: `flow/prepare.py` hashes the **relative paths** and contents of the sources into the build stamp, and the stamp is compiled into the design as the `BUILD_STAMP` constant, so the same RTL in
  another directory is a different netlist constant and a slightly different build. So the comparison judges Vivado numbers only against a reference with the same RTL hash **and** the same
  stamp, which a re-run in a new run directory never has: for a re-run the deterministic part is the bench verdicts, and `python -m agent example tools <name> --vivado` shows the Vivado repeat.

## Reproduce

```
python results/195_repro_examples/summarise.py                   # the tables above, from the records (no tool, no model)
python results/195_repro_examples/bench_recheck.py              # re-score every stored RTL with its hidden bench (Icarus + cocotb, no model, no Vivado)
python -m agent example tools <example> --ref N --vivado        # rebuild one stored RTL at its original path (a heavy job: takes a slot)
python results/195_repro_examples/vivado_rebuild.py gray_stepper 2 same gray_stepper 2 other   # the rows of the rebuild table
python -m agent example run <example>                           # a new run with the pinned setup, compared with these references
```

The runs themselves cannot be regenerated exactly: the model's output differs from run to run (that is what this folder measures). Re-running needs the pinned CLI copy, the knowledge-bank checkout at the pinned commit, Vivado 2026.1 and a heavy slot.

## Files

| Path | What |
|---|---|
| `<example>/ref_<n>.json` | one reference run: pinned setup, outcome, tool results, what varies (schema `fda-example-result/1`; numbers, names and hashes only) |
| `<example>/ref_<n>_rtl/`, `ref_<n>_design.json`, `ref_<n>_design.xdc` | the run's RTL and what `example tools` needs to rebuild it |
| `summarise.py` | the tables above, from the records |
| `bench_recheck.py`, `bench_recheck.json` | the bench re-score of every stored RTL |
| `vivado_rebuild.py`, `vivado_rebuilds.json` | the Vivado rebuilds |
| `screenshots/` | the Examples page at 1280 and 390 px, and `check.json`: zero page errors, no overflow at 390 px, no request outside the service |

## Known gaps and limits

- Three runs per example: spreads are weak evidence ("outside the range" means not seen before). Single model (`claude-sonnet-5-5`), one date, one PC, runs overlapping in time.
- No AXI-Stream example: no development task asks for one. Two of the four examples fail their hidden tests every time; they show a reproducible failure, not a capability.
- The screenshots use real reference results copied into a scratch run directory (each is one of the references), with a fake spawner; no re-run was started from the page. The phone layout wraps the wide tables tightly but does not overflow.
- A first-time user must set up the pinned CLI copy and a knowledge-bank checkout at the pinned commit; the pre-flight says what is missing.
- The agent commit is recorded per run but not pinned (`agent_commit` in each record: two commits of this branch were in use).
