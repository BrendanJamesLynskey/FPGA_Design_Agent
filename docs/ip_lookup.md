# IP library lookup: find a block before writing one

The library (`ip_lib/`, 24 entries) is only useful if somebody looks in it. This page describes the one query behind three
doors: the agent's `ip_lookup` tool (offered at stage 1, board and device planning), the command `python -m agent ip`, and the
plain-Python module `flow/iplookup.py`. It runs no model, no Vivado and no simulator. Brief 150, from the review in brief 147 (journeys J1 and J5).

```
python -m agent ip search "answer ping requests"                    # what fits a request in plain words
python -m agent ip search "FIR filter" --budget dsp=0 --clock-ns 8   # and which variant fits that budget and clock
python -m agent ip show mdio_master                                  # contract, variants, measured cost, an instantiation snippet
python -m agent ip rank fir --budget dsp=0 --objective fabric        # one entry's variants ranked (flow.ipvariants.choose)
python -m agent ip use mdio_master designs/<name>                    # the owner's command: copy in as a frozen component
python3 -m flow.iplookup search ...                                  # the same without the access key
```

## What a user could guess wrong

- **It matches by meaning, not by exact words.** Your request is scored against each entry's name, summary, variant summaries,
  interface signals and the opening of its README, by overlapping words weighted by how rare each word is in the library
  (BM25), after a light stemmer, a few abbreviations ("ping", "TCAM", "low-pass", "mdc") and one guard ("10 Gigabit" is not
  "gigabit": the MACs here are 10/100/1000 Mb/s). The old `python3 -m flow.ipvariants --search` needs *every* word of the request
  to be a whole word of an entry: a sentence finds almost nothing (1 of 20 requests in the probe below).
- **"Nothing fits" is an answer.** An entry needs at least two matching words (or its own name) carrying at least 45% of
  the request's weight; a word the library has never seen ("DDR3", "XGMII", "UART") counts against it. When nothing reaches that, the
  reply says so and lists the **near misses**, marked as such. A near miss is not a recommendation: read its summary before using it.
- **Two different "fits".** The top-level `fits` says an entry answers the request. A *variant's* `fits` says it meets your budget,
  clock and II, from `flow.ipvariants.choose`; a clock is met only where Fmax was *measured at that parameter point*, so
  the reason can read "Fmax not measured at this point".
- **Costs are Artix-7.** LUT, FF, DSP, block RAM and Fmax come from `ip_lib/<entry>/char/xc7a100tcsg324-1.json` (Vivado 2026.1, out of
  context, one run each). For another part the answer is "no characterisation", never an estimate. Latency and II are the `ip.yaml` predictions.
- **No VHDL, no FIFO.** Every entry is SystemVerilog (0 `.vhd`); `--language vhdl` still finds entries but marks them not available.
  There is no FIFO or clock-crossing block: the answer is AMD's XPM macros (`xpm_fifo_async`, `xpm_cdc_*`), whose timing
  exceptions `flow/xpm_cdc.tcl` applies in this flow. The lookup says so when a request names a FIFO or a crossing.
- **The "verified" label is read, never made.** It comes from `ip_lib/<entry>/verified.json` (brief 144, the record behind
  `VERIFIED.md`). On a checkout without that record it is `unknown`. The entry's own `declared_status` is its author's text and is not a verification.
- **Not offered in a scored run.** A scored run measures the agent, not the library, so `ip_lookup` is withheld whenever the run is
  not known to be unscored (fail closed): a `--hidden-spec`, `--interview oracle`, `--spec-tests`, a spec or data directory under
  `benchmark/`, `FDA_SCORED_RUN` set in the environment, or a configuration that cannot be read (`ip_lookup_allowed` in
  `agent/graph/run.py`). The stage-1 bullet is withheld with it. `python -m agent ip` is unaffected: it is the owner's command, not a run.
  If your run is scored and you expected the tool, this is why.
- **The tool never copies files.** `ip_lookup` is read-only (it appends one line per call to `build/ip_lookup.jsonl` in the design: which
  entries were considered). `python -m agent ip use` copies an entry's `rtl/` to `<design>/ip/<entry>/` and adds a **frozen**
  component to the design's existing `project.yaml`; it never creates a managed project and never edits `build.yaml` (it prints
  the source lines to add). The manifest is the owner's; the agent cannot write it.
- **The snippet is a template.** It names the parameters at their defaults and wires each port to a signal of the same name. It is not an integration check.

## What the agent is told

At stage 1 the conventions gain a bullet (`flow.iplookup.IP_LOOKUP_CONVENTION`): call `ip_lookup` before designing a block a standard
function could cover; on "nothing fits" write the block fresh and do not force a near miss; on a fit, read the contract with `show`,
use the entry, and record it in `ARCHITECTURE.md` under "Library entries considered" with one line each on why it was taken or not.
No gate checks that section (it is asked for, not enforced). The design-time plan's prompt (`flow/timing_plan.py`, `--design-plan`) names the
tool too; before brief 150 it told the model to run `python3 -m flow.ipvariants --search`, a command the model could not run.

## Measured

The retrieval probe, its labelled set and the stage-1 trial are in [results/150_ip_lookup](../results/150_ip_lookup/README.md).
