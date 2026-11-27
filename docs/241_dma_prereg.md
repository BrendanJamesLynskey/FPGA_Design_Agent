# Brief 241: pre-registration of the KR260 board run and the agent run

Written 2026-11-26, before either run. Both are **pending**: the board run is the owner's, the agent run waits for brief 239 to merge. Nothing here is a
result. The simulation numbers it refers to are in [results/241_dma](../results/241_dma/README.md).

## A. KR260 board run: throughput and latency of `sg_dma` (owner runs the board commands)

**Question.** How close does `sg_dma` get to the port limit of the Zynq UltraScale+ PS DDR on the KR260, per transfer size, and how long does one
transfer take from the descriptor write to the status word, compared with the simulation figures?

**Design under test** (to be built by a later brief, from `ip_lib/sg_dma`): MM2S and S2MM instances, `DATA_W` 128, `MAX_BURST` 16 and 256 as separate
arms, `OUTSTANDING` 4 and 16, one HP port (`S_AXI_HP0_FPD`), `AXCACHE` 0011, clock 250 MHz if timing closes (the fabric clock is stated with the
result, not assumed). A stream source (counter pattern) and sink (checker) in the fabric, a cycle counter, and a register block read over the PS.

**Arms and measurements (all measured in fabric clocks by a free-running counter, read after the run):**

| Id | What | Sizes (bytes) | Repeats |
|---|---|---|---|
| T1 | MM2S: first AR to last stream beat, six descriptors back to back | 256, 1024, 4096, 16384, 65536 | 1000 per point |
| T2 | S2MM: first stream beat to the last status response, six descriptors back to back | same | 1000 per point |
| L1 | one descriptor: HEAD write to status response (both directions) | same | 1000 per point |
| C1 | the same T1 and T2 with the buffers cached and software cleaning and invalidating around each run, to show the cost of the contract | 4096, 65536 | 200 per point |

**Comparisons and stopping rules.**

- Primary: the fraction of the port limit (bytes per clock over the data width) against size, on the board and in simulation, each with its spread
  over the repeats. The result states whether the board is above, near or below the simulation curve; no expectation is set beyond "the same shape".
- The simulation used a memory model with fixed latency; the board has DDR refresh and other masters. The report gives the board's latency
  distribution (median, 99th percentile, maximum) beside the model's constant, and does not claim the model predicts the tail.
- Stop and report as a null if: the HP port stalls or the PS reports an AXI error response; the stream checker finds a mismatch (the run is then a failure of
  the design, not a measurement); or the temperature or a rail leaves the recommended operating range (the house rule on operating conditions: SYSMON read at the
  start, at the end and at least once a minute, with alarms latched).
- One run per arm and size; no arm is repeated because its result is disappointing. A re-run for a fault in the set-up is recorded as such.

**Not run by the agent.** The owner runs every board command (house rules: board use, SRAM only; `xmutil unloadapp` before a JTAG load; no flash writes).
Any command is written, when it is time, as a script in `_handoff/fpga_agent/`, not here.

## B. Agent run: does the agent choose and wire a DMA correctly? (after brief 239 merges)

**Task** given to the agent, in the words of the brief: "capture a stream into a DDR ring buffer, report to software". Spec text, not hints: no mention of
`sg_dma`, of a DMA engine, or of the library.

**Question.** With the DMA intake questions (`ensure_dma_questions`), the `dma_coherency` check and the KB skills `dma-engine-selection` and
`dma-coherency-and-driver-contract` available, does the agent (a) ask or default the six intake questions, (b) retrieve an engine from the library or
generate one, (c) wire the memory master to a PS port with a declared cache contract, and (d) pass its own gates?

**Design.** Three runs of the same task, Sonnet only (house rule), the harness defaults of the day (H1), the KB at the pin plus this brief's skills (the KB
PR must be merged and re-pinned first, or the skills are absent and the run says so). Target board KR260, part `xck26-sfvc784-2LV-c`.

**Scoring (no model scores anything).** Each run is judged by files: the spec's `dma:` section present and consistent with the sources (the check),
`ip_lookup` or the generated RTL including a 4 KB split (our formal harness bound to the agent's master, the AXI rule checker in simulation), the status word
or interrupt path exercised in the agent's own bench, and the agent's gates. A pass needs all four; the table reports each separately, with the three runs
side by side and no averaging.

**Stopping rules.** Per-run cost cap from the brief's budget line (the planner sets it when 239 has merged); stop at the first run if the key is not
available; no run beyond three. A run that fails for a harness reason (not the task) is reported and repeated once.

**Status.** Pending: brief 239 had not merged when this was written (no commit with the prefix `239:` on `origin/main` on 2026-11-26).
