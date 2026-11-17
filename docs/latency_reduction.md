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
word holding the price to the GT word holding the order's start block, receive 2 to the MAC register, crossing 4, transmit 2 to the preamble
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
why, dollars. A kept change is then built by the flow (heavy-slot rule) and its post-route slack, utilisation and power recorded; a change that
fails post-route timing is reverted as a design change even though the simulation kept it.

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
