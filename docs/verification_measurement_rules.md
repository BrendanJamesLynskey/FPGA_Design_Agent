# Verification and measurement rules (brief 189)

Status 2026-11-23. Nine advisory checks, each with a tool, tests and a recorded result. **None is a gate:** every record carries
`"enforced": false`, every command exits 0 on a finding unless it has an explicit `--enforce` flag (only the ratchet does), and nothing is wired into
the stage gates or the check registry. Making one a gate is the planner's decision after a run of the agent has used it. The ideas come from
Edwards, *FPGA Design for Low-Latency Trading* (2026), chapter numbers below; the wording and all code are ours.

Records are in [`results/189_verification_rules/`](../results/189_verification_rules/README.md); each command below reproduces its record.
Tests are `flow/tests/test_189_*.py`; the four that simulate are `*_rtl.py` (CI's rtl-sim job, Icarus Verilog), the others run in the Python job. No Vivado, no board.

| # | Rule | Tool | Record |
|---|---|---|---|
| 4 | Frames in = frames out + counted drops + frames held (ch 18) | `flow/verif_lib/fda_conservation.sv`, `flow/verif_lib/conservation.py` | `conservation.json` |
| 5 | A tail percentile needs 100 observations beyond it (ch 17) | `python -m flow.claims_tail` | `claims_tail.json` |
| 6 | Regression ratchet on per-module depth, LUTs, FFs and clocks (ch 17) | `python -m flow.ratchet` | `ratchet/` |
| 7 | Two independent latency methods; a planted racy counter (ch 15) | `python -m flow.latency.crosscheck` | `latency_race.json`, `latency_crosscheck_scan.json` |
| 8 | CDC simulation with per-bit skew; a torn-pointer FIFO (ch 12) | `FDA_CDC_INJECT_SKEW=<k>`, `python -m flow.cdc_skew_table` | `cdc_skew.json` |
| 9 | Latency histograms split by class (ch 17) | `python -m flow.latency.split_hist` | `hist_split_b127_*.json` |
| 11 | Testbench compares that cannot fail on X or Z (ch 4) | `python -m flow.tb_xcheck` | `tb_xcheck.json` |
| 12 | Synchroniser MTBF per crossing (ch 6) | `python -m flow.mtbf`, `flow/build.tcl` | `mtbf_*.json` |
| 13 | Our own delay per logic level and per register stage (ch 10) | `python -m flow.level_delay` | `level_delay.json` |

## 4. Conservation

**Rule.** For a block that carries frames, every clock: frames in = frames out + the block's own drop counter + frames held inside it. The helper
counts frames at the block's ports and reads the block's counter and occupancy as values; it never infers drops from a discard event, so a path
that discards without counting is what it catches. An X or Z in the counter or occupancy fails the check.

**Use.** Instantiate `fda_conservation` in the bench next to the block (ports and timing in the file header) or call `Conservation.step` once per clock from a
cocotb bench. **Development design:** `flow/tests/fixtures/conservation/cons_filter.sv`, a four-deep filter with no input backpressure; `SILENT_DROP = 1`
drops a frame on a full FIFO without counting it. **Measured (Icarus 12.0, three seeds):** the correct filter passes with 1,205 to 1,285 counted drops in about
2,800 frames; the mutant fails at frame 15, 12 and 7. The silent drop in a real block (b110) is brief 188's: the helper binds in its bench, the
mutant belongs in its mutant list.

## 5. Tail claims need observations

**Rule.** At least 100 observations lie beyond a quoted percentile: p99 needs 10,000 samples, p99.9 100,000, p99.99 one million (`required_samples`). A percentile
with no stated sample count is a separate, lighter finding. The maximum is not a percentile. A waiver is `tail-ok: <reason>` on the line (or the one above).
**Board runs:** `python -m flow.claims_tail --need 99.99 --rate 1000000` prints the observations and seconds a run needs.

**Measured on this repository (2,590 files scanned):** 205 findings of "too few observations" and 31 of "no count stated", almost all in the memory scheduler's records (`results/b141`:
p99 and p99.9 quoted from 2,115 to 3,000 reads, so about 21 to 30 observations lie beyond the p99 and 2 to 3 beyond the p99.9) and its results table. The next board visit plan quotes no percentile, so it has none to flag;
the run-length rule is added to it as a note. One more is a weight-calibration quantile in `designs/b92_history_attention`, not a latency; no document was edited to waive it (the `tail-ok:` marker is there for the owner of the text).

## 6. Regression ratchet

**Rule.** Keep, per build, per module: LUTs, FFs and the most logic levels on any reported path ending in the module; and named latencies in clocks. Flag growth of
more than 5 % against the last accepted build (RATCHET-01) or 10 % against the best ever accepted (RATCHET-02, which catches creep in small steps), when the growth also
reaches an absolute floor (5 LUTs or FFs, one level, one clock). A waiver (module, metric, reason; the reason is required) or an override for the build accepts a growth and is
recorded. `snapshot` builds a record from an out-of-context result (`blocks`), timing reports and a latency JSON; `check` compares; `record` appends. Only advisory unless `--enforce`.

**Demonstration on recorded data (illustrative):** the b110 out-of-context record at 6.2 ns and at 4.4 ns are two builds of the same RTL; `check` flags `u_book` LUTs 4,397
to 4,631 (+5.3 %), the cost of pushing the clock. That is not a regression; it shows the mechanism. The logic depth needs a post-route report the repository does not hold for b110, so the record has no depth yet.
**Limit:** a report lists a few paths, so the depth is a floor.

## 7. Two independent latency methods

**Rule.** A latency is quoted with two measurements of different kinds that agree (counter, simulator time, waveform marker, hardware counter, external instrument, analytic) and with named
start and end events. Findings: one method (LAT-X-01), same kind (02), disagreement (03), events not named (04), and, in a scan of existing records, no `methods` list (05).
**Planted defect:** `flow/tests/fixtures/latency_race`: a three-clock pipeline whose latency a bench measures with a cycle counter that one process increments and another reads on the
same edge. **Measured (Icarus 12.0):** the counter reads 2 and 4 clocks in the two source orders, 3 with a non-blocking increment; the simulator-clock method reads 3 in all. The check flags both
racy variants and passes the repair. **Existing records:** 29 of the 31 latency-named JSON files scanned in `results/` carry no second method (LAT-X-05). **Not done:** the design is not added to the brief-84 review benchmark;
that benchmark is in the private repo and its held-out split is not read by executors, so the planner adds it as a development task (the fixture's README has the truth).

## 8. CDC simulation with per-bit skew

The existing injection (brief 16) holds each first-stage synchroniser bit for 0 or 1 extra destination cycle. `FDA_CDC_INJECT_SKEW=<k>` (plusarg `+CDC_INJ_SKEW`) lets a bit be held up to k
cycles in a row, drawn per bit; k = 1 (the default) leaves every earlier result unchanged. **Torn-pointer mutant:** `cdcfx_m12` is the C10 asynchronous FIFO with binary pointers.
**Measured (8 seeds, Icarus 12.0 and cocotb 2.0.1, `cdc_skew.md`):** the binary-pointer FIFO passes plain simulation and passes at k = 1 in all 8 seeds, fails in 2 of 8 at k = 2 and in 8 of 8 at k = 4; the Gray-pointer FIFO
passes every case. So the existing 0-or-1 model does not catch this mutant with this bench (state that when quoting the model's coverage); a larger skew does. A skew of several destination cycles on a constrained crossing is
beyond what a bus-skew constraint allows in hardware; the injection is a stress that makes the missing Gray coding visible, not a model of the silicon.

## 9. Histograms split by class

`flow/latency/split_hist.py` gives a histogram and summary per class value, and ranks candidate classes by the share of the variance they explain (eta squared). `class_label` and `packet_position` name the two classes
the hardware histogram would carry: message type and index of the message in its packet. **Demo on recorded data** (`results/b127/latency_unit_sim.json`, the ITCH path's latency from the MAC word holding the message's last
byte to the order's first byte, 24 messages per mode): the latency has three values (11, 12, 13 clocks at the verdict; 6, 7, 8 speculative), and the byte lane the message ends in explains 88.8 % of the variance:
lanes 0 and 1 give one clock fewer than the others, and the single one-clock-more sample per mode is the gearbox pause. **Not done:** a per-class histogram on the board (the in-fabric histogram has no class input yet; the
board-plan note says what to log).

## 11. Compares that cannot fail on X

**Rule.** `if (got != want) $error` is skipped when `got` holds X (the condition is X, so `if` takes the false branch): a DUT that outputs X passes. Use `!==` or `===`, or test `$isunknown` first. `assert (got == want)` is safe. The source check flags an `if`
whose condition has `!=` (or a negated `==`) and no case operator or `$isunknown`, and whose statement raises an error; a deliberate one carries `// x-ok: <reason>`; queue sizes are exempt (two-state).
**Seeded defect:** `flow/tests/fixtures/xcompare`: an encoder that outputs X for one input; the `!=` bench prints PASS, the `!==` bench prints FAIL (Icarus 12.0), the check flags only the first. **Measured on the repository:**
5 flags in 67 testbench files, all in b96's UVM scoreboard and the memory scheduler's bench, for the author to confirm. **Gap:** cocotb benches are not scanned (`int(sig.value)` raises on X, and the CDC and conservation benches assert `is_resolvable`).

## 12. Synchroniser MTBF per crossing

`flow/build.tcl` writes `mtbf.rpt` after routing (`report_synchronizer_mtbf`, inside `catch`: it never fails a build). `flow/mtbf.py` parses it into one record per chain (stage count, settling time, toggle and sample rates, MTBF in years),
the worst chain, and findings: below a target (MTBF-01, default 1,000 years, the design's to set), a one-stage chain (02), no MTBF for a chain whose data toggles (03). **No new Vivado run was needed:** the reports of brief 105
(Vivado 2026.1) exist. **Measured:** the K26 survey fixture lists 24 chains, worst 6.31e+25 years; the KR260 design (b96) lists 1,345 chains, worst 1.13e+52 years, with 8 chains the tool gives no figure for (`n/a` toggle rate: flagged), 35 more it reports as undefined for static or infinite-settling
data (counted, not flagged) and 46 whose MTBF it states only as a lower bound beyond its range (`> 1.8e+308 years`). The plain variant without ASYNC_REG lists no chain, and a 7-series build has no report (the family matrix `cdc` row: warning 12-3426), so
the record says `no_chains` or `no_report` instead of passing. **Gap:** mapping a chain to the structural CDC check's crossings (the report names the source net; the paths use register names) is not done.

## 13. Per-level delay and register overhead

`flow/level_delay.py` reads the data-path rows of post-route setup paths (register to register, no DSP or RAM) and reports, per part, the mean delay per logic level (feeding net plus cell), by cell type, the
register overhead, and a least-squares fit. Its level count equals Vivado's own `Logic Levels` on all 57 paths. **Measured (Vivado 2026.1; brief 89's out-of-context LUT networks, `results/b89/ooc`):**

| Part | Per level | of which cell + net | Clock-to-Q | Setup | Fit (data path + setup on levels) |
|---|---|---|---|---|---|
| xck26-sfvc784-2LV-c (30 paths, 1 to 18 levels) | 0.28 ns | 0.13 + 0.15 | 0.11 ns | 0.04 ns | 0.27 ns per level + 0.36 ns, R2 0.91 |
| xc7a100tcsg324-1 (27 paths, 1 to 16 levels) | 0.80 ns | 0.24 + 0.56 | 0.47 ns | 0.03 ns | 0.70 ns per level + 1.29 ns, R2 0.95 |

These are the worst paths of designs closed at their limit, with the fan-out and routing of big LUT networks: a first estimate for a stage budget, not a device constant. They replace the book's placeholder figures in our budgets, where a budget needs
one. Brief 185 measures DSP-slice paths; its runs had produced no data when this was written, so nothing here duplicates them and the K26 and Artix-7 per-level figures should be compared with its first records.

## Known gaps

- Nothing is a gate; the checks run on request. Wiring them into `flow/checks` (rules in `hdl_rules.yaml`) needs a planner decision.
- The 0-or-1-cycle CDC injection does not catch a binary-pointer FIFO with this bench; the skewed injection does (section 8).
- Conservation and the racy counter are shown on development fixtures, not on b110 or b58a (brief 188 owns their RTL and benches).
- Tail claims: the scan reads text and JSON, not figures or plots.
