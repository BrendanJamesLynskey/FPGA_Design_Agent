# Strategy options: analyse a loaded design, offer ways to improve it, change nothing until one is chosen (brief 104)

A request such as "lower latency" or "close timing" on a loaded design does not edit anything. `python -m agent improve <design> "<request>"` first runs a
read-only **analysis** of records that already exist, then asks one model step (purpose `options` of the model table, [model_config.md](model_config.md)) for
two to four **strategies**. Code checks every option; the user picks one, edits one or asks for more. A chosen option starts the ordinary scoped run
(`agent resume <design> "<request>" --scope <its components>`), and the run record keeps the analysis, the options offered and the choice.

## Commands

```
python -m agent improve <design> "<request>"            analysis, options; saved to <design>/build/managed/strategy.json
python -m agent improve <design> --analyse-only [--json] the analysis alone (no model call)
python -m agent improve <design> --more                 different options for the same request
python -m agent improve <design> --edit N "<change>"    option N rewritten with your change (the others stay)
python -m agent improve <design> --choose N [--dry-run] the ordinary scoped `agent resume` with option N's scope
```
Other flags: `--build-dir` (where the reports are; default `<design>/build/base`, else `<design>/evidence`), `--out`, `--json`, `--blind`, `--models-file`, `--model-config`,
`--replay`, `--record`; with `--choose`, `--board`, `--verif-level`, `--stop-after`, `--max-usd` go to `resume`. The access key is required like any entry point.

## What the analysis reads (`flow/options/analysis.py`)

| Section | Source (all existing files) | If missing |
|---|---|---|
| components, ownership, level, trust | `project.yaml` (a design without one is one owned component: only whole-design options) | |
| latency budget by stage, with the component of each stage | `latency_stages.yaml`, its recorded bench clocks and post-route stage slack (`flow/latency`) | gap: latency unknown; a latency request becomes a question |
| WNS, WHS, TNS, clocks, worst path and the component it is in | `timing_summary.rpt`, `timing_worst_setup.rpt`, or a closure-loop `digest.json` | gap |
| LUT and FF per component (own, excluding nested components) | `utilization_hier.rpt` | gap; totals only from a digest |
| clock crossings | `cdc_summary.rpt` (`report_cdc -summary`) | gap |
| build wall time | `run.json` | cost has no wall-time figure |

The analysis never starts Vivado, a simulation or a build: with no reports it says so and offers to build. **Excluded components are not in it at all** (rows, stages, paths
dropped); frozen ones are listed, read only. Every number is a **fact** with a stable id (`stage.cross_go.clocks`, `timing.wns_ns`, `res.rx_mac.lut`), a value, the file and locator it came
from, and an origin (simulation, post_route_report, stage_file, board, prior_run). The model is shown the facts without file names; the checker maps ids to files.

## The options (schema `fda-options/1`)

Each option has a scope (whole design, a subsystem or individual modules, as the exact component list and the `--scope` it runs with), the approach, the stages it touches, an expected
**gain as a range with its basis**, a cost, a risk, and what is not touched. What a user could get wrong:

- **Gain** is the size of the improvement: clocks removed, LUT or FF removed, nanoseconds of slack gained (for a clock-rate request the model may express headroom as slack). `basis` is
  `model` (arithmetic on cited analysis facts, at least one about that quantity), `measurement` (cites a `prior_run` fact: a recorded earlier change; the analysis has such facts only when
  the design supplies them) or `guess` (no basis; shown as GUESS). A gain with no cited basis is rejected. The high end is bounded by the analysis: the removable clocks (or, in
  the blind arm, the clocks) of the touched stages, the LUTs or FFs in scope, one clock period. Ranges are estimates, not promises.
- **Cost** is computed: the model gives build-and-check rounds (a guess); Vivado runs equal those; wall time is rounds times the recorded Vivado run. Model spend is not estimated.
- **Contract change** is computed by code and the model cannot clear it: a change touching stages in two components (it moves logic across an edge), an interface change the option declares, or a
  clock-crossing stage. Such an option needs the owner's approval: `--choose` refuses until the components are in `approved_contract_changes` of `project.yaml`, a file the agent cannot write.
  The flag is conservative: a stage edit that keeps every port can still be flagged because it changes a timing relationship at a boundary.
- **Not touched** is computed: every other component, frozen ones marked read only. `needs_board` is forced true for a crossing stage.
- **Ambiguous or unsupported request**: a question, no options, and no model call. "Faster" alone is ambiguous (latency, clock rate or size?); throughput, power (not analysed yet) and
  unknown metrics are unsupported; two goals in one request are ambiguous; a request naming only a frozen component gets the 102 question; naming owned components pins the scope to them.
- **Stale**: `--choose`, `--more` and `--edit` refuse when the design's reports or components changed since the options were made (the analysis hash differs).
- `--choose` uses the design-resume path, so the design needs a `handover.yaml` (brief 68 D). `--dry-run` shows the resume without running.

## Checks on what the model writes (`flow/options/schema.py`)

Shape and text limits; scope respects ownership (owned only, the touched stages live inside the scope, whole design means every owned component); every number cites existing facts and is
bounded; gain metric matches the goal; a set has two to four valid options, with a narrow and a broad one when both are possible. A failing option is dropped; the failures are given back
once for a repair; what still fails is recorded under `rejected` with the reasons. The model's own `not_touched`, `scope.cli` and cost are never used.

## Run record

`strategy.json` holds the request, mode, goal, analysis hash and source files (with hashes), the options offered, the rejected ones, the model identity (purpose, endpoint, model, entry and
table hash), and **prompt names and hashes only** (prompts are in the private knowledge repository, brief 99, `graph/options/*`). After `--choose`, the resume copies it into the run
(`runs/<id>/strategy.json`) and `summary.json` gains `strategy` (the choice, the options offered, the chosen option in full).

## The `--blind` ablation

The stage file written for brief 97 carries `technique` and `removable` fields that point at the answers. `--blind` withholds them (and the removable facts) from the model so a back-test can show
how much of an option comes from the analysis and how much from those hints. The `why` and `remove_risk` text stays in both arms.

## Limits

Gains are ranges from the stage table and the reports, not predictions from a simulation of the change. Only latency, timing and area are analysed (no power). Per-module resources need a
hierarchical utilisation report. Evidence files are unsigned. Back-test results and gaps: [../results/104_strategy_options/README.md](../results/104_strategy_options/README.md).
