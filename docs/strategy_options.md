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

The analysis never starts Vivado, a simulation or a build: with no reports it says so and offers to build. **Excluded components are not in it at all** (rows, stages, the cell names of a worst path inside one, and their share of the totals are dropped; this needs the manifest to give the excluded component its `instance`, otherwise the reports cannot be attributed to it); frozen ones are listed, read only. Every number is a **fact** with a stable id (`stage.cross_go.clocks`, `timing.wns_ns`, `res.rx_mac.lut`), a value, the file and locator it came
from, and an origin (simulation, post_route_report, stage_file, board, prior_run). The model is shown the facts without file names; the checker maps ids to files.

## The options (schema `fda-options/1`)

Each option has a scope (whole design, a subsystem or individual modules, as the exact component list and the `--scope` it runs with), the approach, the stages it touches, an expected
**gain as a range with its basis**, a cost, a risk, and what is not touched. What a user could get wrong:

- **Gain** is the size of the improvement: clocks removed, LUT or FF removed, nanoseconds of slack gained (for a clock-rate request the model may express headroom as slack). `basis` is
  `model` (arithmetic on cited analysis facts, at least one about that quantity), `measurement` (cites a `prior_run` fact: a recorded earlier change; the analysis has such facts only when
  the design supplies them) or `guess` (no basis; shown as GUESS). A `model` or `measurement` gain with no cited basis is rejected, and so is a non-guess gain for which the analysis gives no upper bound; only a labelled `guess` may stand without one. The high end is bounded by the analysis: the removable clocks (or, in
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
(`runs/<id>/strategy.json`) and `summary.json` gains `strategy` (the choice, the options offered with their origin, the chosen option in full).

## The combiner: cumulative options built by code (brief 104A)

The model offers single changes; **code** builds the cumulative options from the ones that passed the checks (`flow/options/combine.py`). The model is not asked to combine, and the combiner never reads a back-test's truth.

- **Compatible** parts touch no stage in common and declare no interface change to the same port of the same component. The combined scope is the union of the parts' components (`whole_design` when that is every owned component), still owned-only.
- **Gain composed by code.** `latency_clocks`: the cuts of disjoint stages add (stage clocks are additive along the chain), so low and high are sums, capped by the checker's ceiling for the union; a labelled guess among the parts makes the whole a guess.
  `lut`/`ff`: added only across different components. `wns_ns`: **not composable** (the worst path sets the clock). A combination that cannot be composed is not offered; it is listed under `combiner.not_composable` with the reason. The sum is not a
  simulation: interactions between the changes are not modelled (the basis note says so).
- **Measured earlier.** If the design supplies `prior_runs.yaml` (schema `fda-prior-runs/1`) and a combination touches exactly the stages of one of its runs, the measured cut replaces the sum and the basis is `measurement`, citing the `prior_run` fact. A run is used only
  when every stage it names is in the design's latency chain: `designs/b96_kr260_10g/prior_runs.yaml` holds the brief 97 and 97C variants measured on the pre-96C chain (with `cross_go`), which today's rate-matched stage file no longer has, so for that file they are listed in
  the analysis notes and not used.
- **Validated like any option.** The combined option is built as a raw option and goes through the same per-option checks (`schema.check_single`): contract flags (a change across components, a crossing), owner approval, cost, not-touched.
- **Ranked by code, capped at four.** Order (version 3, brief 104C): measured earlier, higher composed mid-gain, fewer components touched, no owner approval needed, more model support, more timing headroom, then a content-only key (see "The menu rule" below). It never depends on the model's order. The best combination of each size is kept (small, medium, full), then the cap is filled with the next best. Combined options are numbered after
  the model's, ids `C1`..., `origin: combiner`, `combined_from`, shown as "COMBINED by code" in the CLI. `--more` and `--edit` rebuild them; `--edit` of a combined option is refused (edit one of its parts).
- **What it cannot do.** It combines what the model offered (and, since brief 104B, the parts the splitter derives from the model's bundles, below). Results: [../results/104A_combiner/README.md](../results/104A_combiner/README.md).
- **Pool (104B).** The combiner draws on the model's options that were not split, plus the splitter's parts (at most ten in all); a split bundle is replaced by its parts. Parts of one bundle together count at most the bundle's own high end.

## The splitter: bundled options become per-stage options (brief 104B)

The model often bundles several stages into one option (in the 104A runs `decide` came only inside bundles, never alone, so `cross_go` + `decide` could not be built). **Code** (`flow/options/split.py`) derives per-stage parts from a bundle of a latency request, from the stage file. It never reads a back-test's truth and calls no model.

- **Parts.** One part per *unit* of the bundle's stages. `high` = the checker's own ceiling for the unit (the stage file's removable clocks; the stage's clocks in a `--blind` run) and never more than the bundle claimed; `low` = what the bundle's own low end forces on the unit after the other units give their most (usually 0). A unit with no backable gain is dropped, with the reason in `rec["splitter"]`.
- **Scope and provenance.** Only the components the stage lives in; only the interface changes of those components; `origin: splitter`, `split_from` (the bundle's id), `split_bundle_gain` (the bundle's range). Each part passes `schema.check_single` like any option. Text is built from the stage file (name, risk of removing it, and, unless `--blind`, the technique) and the bundle's sentences that name the stage or its component. The bundle's risk is carried over, not re-assessed.
- **Coupling (never split across it).** Stages stay in one unit when (1) the stage file marks them (`coupled_with: [stage ids]` on a stage record; optional, absent in today's files), or (2) the bundle declares one interface change on a component that holds two or more of its stages. A bundle with an interface change on a component none of its stages live in is **not split at all** (the change may be what ties the stages together). Every decision is listed under `rec["splitter"]["report"]`, and the CLI prints it.
- **Offered.** Parts are numbered `S1`... after the model's options and before the combined ones, shown as "SPLIT by code from O3". A stage set the model already offers alone, or an earlier bundle already gave, is skipped. `--more` and `--edit` rebuild them; `--edit` of a part is refused (edit the model's option).
- **Limits.** The parts' ranges are bounds, not predictions; their risk text is the bundle's. A bundle of stages the stage file does not know, or only latency chains, is not split. The combiner's cap of four still limits what is offered: many parts tie on composed gain, so the cumulative option you want may be valid and listed under `combiner.not_composable` ("valid, not in the best four") rather than offered. Results: [../results/104B_split/README.md](../results/104B_split/README.md).

## The menu rule: the same menu for any order of the model's options (brief 104C)

Briefs 104A and 104B broke the combiner's ties by the model's listing order, so the same set of options could give different menus. The rule is now a function of the *set* of options and the stage file (`flow/options/combine.py`, version 3; `flow/options/split.py`, version 2).

- **Keys, in order** (each only breaks ties of the keys before it): earlier measured; higher composed mid-gain; fewer components; no owner approval; **model support** (how many of the model's own options name the touched stages, summed; the model reached the stage independently in several options, and a count does not depend on position); **timing headroom** (the touched stages' post-route setup slack from the stage file, compared tightest first: the combination whose weakest stage has the most slack first, then the next weakest; a stage with no slack figure ranks below every known one); a **content key** (stage-file chain positions, component names, gain bounds; never an option id, number or position).
- **Why these.** Support is the only evidence about a stage's opportunity that the pool carries besides the stage file. Headroom is a risk argument: removing a register puts its logic in front of the next one, and the stage with least slack is the one most likely to fail timing. Both are heuristics, stated as such; neither reads a measured result.
- **Pools** are truncated by the same content rule (higher mid-gain, then the content key), so which option is dropped never depends on list position. The splitter handles bundles in a content order (widest claimed range first, then chain position); parts and combined options are numbered in that order.
- **Unchanged:** the cap of four, the best-of-each-size and largest-size selection, the checks and bounds, the scorer. Not changed either: the generator's own cap of four on what the *model* offers (`schema.check_options` keeps the first four if the model offers more); that truncation is by list position and is a known gap.
- **Limits.** A deterministic, truth-blind rule cannot be expected to surface a particular pair under a cap of four: a pair is offered when the pool and these keys rank it in the top four, and every valid combination stays listed under `combiner.not_composable`. Results: [../results/104C_menu/README.md](../results/104C_menu/README.md).

## The `--blind` ablation

The stage file written for brief 97 carries `technique` and `removable` fields that point at the answers. `--blind` withholds them (and the removable facts) from the model so a back-test can show
how much of an option comes from the analysis and how much from those hints. The `why` and `remove_risk` text stays in both arms.

## The tool

The registry tool `design_analysis` (schema 1.16.0) gives an agent the same read-only analysis as text. No stage or role is offered it yet.

## Limits

Gains are ranges from the stage table and the reports, not predictions from a simulation of the change. Only latency, timing and area are analysed (no power). Per-module resources need a
hierarchical utilisation report. Evidence files are unsigned. The analysis hash covers the reports and the component files' hashes, not the cell-level netlist. Back-test results and gaps: [../results/104_strategy_options/README.md](../results/104_strategy_options/README.md).
