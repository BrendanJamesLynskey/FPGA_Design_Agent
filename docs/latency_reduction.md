# Latency reduction as an agent skill (brief 97, phase 1)

Owner direction, 2026-11-17: "the 10G design is an opportunity to refine the agent's ability to improve latency": the agent identifies the
critical path, then works to reduce latency on it. This page says what was built, how a loop iteration is judged, and how to run it.
Phase 2 (a planning loop over all modules, several strategies, manual placement and routing, our own tools against Vivado's, device
characterisation) is planned in [latency_phase2_plan.md](latency_phase2_plan.md).

## Two different critical paths

- The **timing-critical path** has the worst slack. It limits the clock period.
- The **latency-critical path** is the chain of registers and clock crossings from the first bit of the input on the wire to the first bit
  of the output on the wire. Its latency is (registers on that chain) x (clock period), plus the transceiver (GT) and the optics.

Cutting a register usually beats shaving picoseconds. Shaving picoseconds matters only when it lets the clock go faster or lets two stages
merge into one. A loop that confuses the two shortens the wrong path.

## The tools (agent/core/latency_tools.py, flow/latency/)

| Tool | What it returns | Where the numbers come from |
| --- | --- | --- |
| `latency_path(path, refresh)` | every register and clock crossing of the chain (`tick_to_trade` or `echo`) with its clock domain, clocks and ns added, cumulative clocks, the registers it is made of and, when a post-route checkpoint has been read, the setup slack of those registers, marked timing-critical when below 0.30 ns | the design's `latency_stages.yaml` (structure, written from the RTL), the whole-core bench (`refresh` re-runs it, about a minute; simulation only), `flow/latency/netlist_slack.tcl` on a post-route checkpoint |
| `latency_budget(path, refresh)` | the table to reason from: per stage the clocks, ns, why it exists, what removing it risks, the technique that removes it, the clocks that could come out; then the board's share (GT, optics, wire-to-wire from the recorded stage 3 run) and the unattributed residual | as above, plus `results/b96/hw/*/stage3.json` |

Both **reconcile**: the stage clocks, summed per segment, must equal what the bench measured (the 96 numbers: 11 digital clocks from the GT
word holding the price to the GT word holding the order's start block, receive 2 to the MAC register, decision register 1, crossing 4, transmit 2 to the preamble
and 2 to the start block). When the design changed and the stage file did not, the tools say so in a warning and the bench's total stands.
Neither tool takes a path, a command or a board. The budget **never adds a board figure to a simulation figure** without showing the
residual: wire-to-wire on the board is L - E - fibre = 29.9 clocks (185 ns, medians of 100 restarts); the simulated digital chain is 11; the
GT and optics share of the echo is E - 5 = 15; the difference (about 4 clocks) is the two accountings' disagreement (the RX stamp's
synchroniser delay understates D; the echo counts the digital transmit and receive clocks once) and is shown as unattributed, never as saved.

## The loop (agent/graph/latency_loop.py, `python -m agent latency <checkout> --arm A1|A0`)

One visit per iteration. The Designer (a tool-using model, `openai/gpt-6-luna` through OpenRouter, provider-reported cost, `deny` data
collection) reads the RTL, proposes and applies one change (`rtl/*.sv` only; the tools' own stage file is not readable by the agent in either arm),
and may call `measure`, which runs the **independent bench and the model twin** and returns pass/fail and the measured clocks. Then the **flow**
decides, not the model:

1. the bench (`tests/test_b96_pcs_rtl.py`: the PCS and MAC against the Python twin cycle by cycle, and the whole core with frame checks against
   brief 58A's builders) and the model tests pass, unedited;
2. the tick-to-trade clocks, read from the bench's own JSON, are lower; the echo's are not higher;
3. otherwise the files are restored.

Every iteration is a row of `history.jsonl`: hypothesis (the agent's NOTE), tools used, diff hash, clocks before and after, tests, kept or reverted and
why, dollars. The loop has no build step: a kept change is built afterwards by hand (`results/b97/build_variant.sh`, heavy-slot rule) and a change that fails post-route
timing is to be reverted as a design change even though the simulation kept it.

Arms: **A1** has the two tools and the skill text (`latency-critical-path`, a private knowledge-bank file); **A0** is the agent as it was (file tools and
`measure`; it finds the path from the RTL). Same design, same prompt skeleton, same budget. The prompts and skill text live in the private
knowledge bank (`prompts/latency/`, brief 94: new prompts go private by default); the public code refuses to run without them.

## What the independent checks can and cannot see

- The model twin and the PCS and MAC benches compare the stream **cycle by cycle**, so any change that moves a clock inside the PCS or MAC is
  reported as a failure, whether or not the behaviour is right. A change there needs a latency parameter in the twin first (a follow-up).
- The cut-frame bench injects a bit error at a fixed cycle; its effect depends on the gearbox phase, so a change that shifts the phase of *every*
  frame can fail it for a reason that is not a functional break (seen in the hand reference below). Shifting only the order frames passes.
- The whole-core bench runs both user clocks in phase, so it shows the receive-to-transmit crossing's fixed latency only; on the board there is up
  to one clock of phase on top, and a metastability margin that only an analysis (MTBF) or a soak can show.
- The transceiver's 15 clocks are not simulated. Buffer bypass is board-only and is a plan, not a result, here.

## Known limits found in review (brief 97)

- The measured clocks read internal RTL events (`wi`, `fire`, `go_p`, `sop`) plus two fixed constants, so the agent controls the signals the bench reads. They are not
  measured at the GT ports; a port-level measurement is a follow-up.
- The 15-clock GT share (E - 5) and the 29.9-clock wire-to-wire figure are different accountings (frame start to frame start on the board, price word to start block
  in simulation); the roughly 4-clock residual is a net of definitional differences, not a small unknown. Quote the GT share as derived, not measured.
- All savings are in-phase, fixed-latency simulation without the gearbox pause; the board adds up to one clock of crossing phase. The simulated CDC cells are the
  repository's behavioural stand-ins, not AMD's XPM; no MTBF analysis, CDC injection or soak was run on the changed crossing. Both the shorter pulse and the combinational
  decision cut the margin between the pulse and the order data bus (sampled for four clocks) and put a 32-bit compare in front of the crossing flop: post-route timing is required before any claim.
- The stage file's `removable`/`technique` fields and the test file `test_b96_latency.py` spell out the stage structure, so neither arm is blind to it; the A1 tools therefore
  state structure A0 can also read in `docs/design.md`. The A0/A1 prompts are private files; their sameness is by construction, not checkable from this repository.

## Post-route and CDC evidence (Vivado 2026.1, `xck26-sfvc784-2LV-c`, `results/b97/postroute.md`, `results/b97/cdc/`)

All four variants route and meet timing at 161.13 MHz (WNS +0.078 to +0.298 ns, WHS +0.010 ns, no failing endpoint; the 96 baseline was +0.115 / +0.010). LUT and FF move by under 1 %.
`report_cdc` (routed, `results/b97/cdc/<variant>_cdc_summary.rpt`) is identical to the baseline's for every variant: the same nine clock-pair rows, the receive-to-transmit
row (151 endpoints, "No Common Node", False Path exception) all Safe, no Unsafe, no Unknown, no missing `ASYNC_REG`. The setup slack of the path into the go pulse's source flop,
which carries the new combinational decision, falls from 5.59 ns (baseline) to 2.20 ns (agent_both) and 2.23 ns (all3): met, with margin.

Written reasoning for the two edits that touch the crossing (report_cdc cannot see data-bus skew):
- **`u_p_go` `REG_OUTPUT` 1 -> 0** removes only the output register after the destination-domain synchroniser chain. The asynchronous hop (toggle flop to the first of two `ASYNC_REG` flops)
  and the number of synchroniser flops (2) are unchanged, so the metastability failure rate is unchanged; what changes is a combinational XOR in front of the consumer, checked by timing.
  report_cdc agrees (same structure, Safe).
- **`trade64.fire` combinational** is a source-domain change (it feeds the toggle flop's D input in the same clock domain); it adds no crossing. It does move the pulse one clock earlier relative to the order
  data bus (`u_bus`, 3 synchroniser stages, each bit independent), which `frame_src` samples for four clocks after it starts. Worst case the bus bits settle one clock after the pulse and one more if a bit slips a clock, so the last
  effective sample leaves about two clocks of margin (was about four). The `stale` counter checks only the sequence word, not the price or quantity bits, so a late price bit would not be caught by it.
  This is reasoning, not proof: the receive-to-transmit crossing is a false path in the constraints, only the board shows bit skew. The board session therefore reads `stale`, `late` and the order bytes at the receiving end
  on every variant, and a variant with a non-zero `stale` or a wrong order byte is reverted.
- **Order-only early MAC start** (`s_valid | (fs_start && go_p)`, found by the A0 arm in round 2) is a same-domain change: no crossing; its risk is the gearbox pause, which holds MAC state (an early valid during a pause is ignored and costs a clock, not data).

## Agent before/after, both rounds (`results/b97/ab_summary.md`, k = 2 per arm, `openai/gpt-6-luna`, provider-reported cost)

- Round 1 (start 11): all four runs ended at 9 clocks with the same two edits; A1 cost less (about 0.016 against 0.023 USD) but k = 2 allows no inference.
- Round 2 (start 9, stage file updated, pre-registered as an addendum written after round 1): both A0 runs found the order-only early MAC start (9 -> 8, bench and twin pass); both A1 runs
  made no gain and stopped after two visits (the stall rule), after reverting attempts that touched `pcs_rx`. So the tools-plus-skill-text bundle did not help here and may have hurt: the skill text's
  "start from the earlier event" led A1 to a version that failed the cut-frame bench, while A0 found the narrower order-only form. This is two runs per arm; it is reported as a null with a reversal, not a finding.
