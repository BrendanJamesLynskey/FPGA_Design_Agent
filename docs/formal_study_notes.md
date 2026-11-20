# Formal verification of the gray-pointer rate matcher: worked examples for a model-checking course (brief 115)

The block is `designs/b96_kr260_10g/rtl/rate_match_gp.sv`, the own elastic buffer of brief 96E: a gray-pointer asynchronous FIFO between the
receive clock (write side) and the user clock (read side) that also inserts and deletes idle blocks to absorb the clock difference. This page
shows what was proved about it with SymbiYosys, and ties each property to the three parts of a model-checking course (modelling with
Kripke structures; LTL and CTL model checking; equivalences, abstraction and partial-order reduction). The RTL was not edited: the
properties are attached with `bind`. Every number below comes from `results/b115/formal_ci.json` and `results/b115/formal_full.json`
(`designs/b96_kr260_10g/verif/formal/run_formal.py` writes them).

Contents: 1 files and commands; 2 what the tool reads; 3 the design in two paragraphs; 4 the model (clocks, synchronisers, assumptions);
5 the properties and their temporal-logic forms; 6 BMC and k-induction, with the counterexamples to induction met on the way; 7 safety,
liveness, fairness and the ranking function; 8 abstraction; 9 the mutants; 10 results; 11 known gaps; 12 exercises.

## 1. Files and commands

| File (`designs/b96_kr260_10g/verif/formal/`) | What |
|---|---|
| `rm_gp_props.sv` | the properties and their helper invariants, one module bound to `rate_match_gp` |
| `rm_gp_bind.sv` | the `bind` line (the RTL is not touched) |
| `rm_gp_fv_top.sv` | the harness: the block with two free clocks and free inputs |
| `xpm_formal.sv` | formal stand-ins for the three AMD clock-crossing macros the block instantiates (section 4) |
| `rm_gp.sby` | the SymbiYosys jobs: `safety_bmc`, `safety_prove`, `progress_bmc`, `progress_prove`, `cover` |
| `run_formal.py` | runs the jobs and the mutants, writes the result files; also called by `tests/test_b115_formal.py` and CI |

```
python3 designs/b96_kr260_10g/verif/formal/run_formal.py --set ci   --json results/b115/formal_ci.json     # what CI runs
python3 designs/b96_kr260_10g/verif/formal/run_formal.py --set full --json results/b115/formal_full.json   # adds all 74 bits of the entry, deeper runs
python3 designs/b96_kr260_10g/verif/formal/run_formal.py --only mut_wrong_entry                            # one job
cd designs/b96_kr260_10g/verif/formal && sby -f rm_gp.sby safety_prove                                        # one job by hand (default AW = 2)
```

The tool is the OSS CAD Suite release the repo pins (2026-11-12: Yosys 0.70 with the slang front end, SymbiYosys, Boolector). It was already
installed in `~/.local/opt/oss-cad-suite`; `FDA_OSS_CAD` points at another copy. Formal runs are small (a few hundred MB, minutes), so no heavy slot is taken.

## 2. What the tool reads, and why every property is written twice

The free SystemVerilog front end (yosys-slang) accepts only clocked Boolean concurrent assertions: `assert property (@(posedge clk) expr);`.
It rejects `|->`, `|=>`, `##`, `$rose` inside implications, `s_eventually`, sequences and `always`. A commercial front end (Verific, which the
free suite does not include) reads all of them. So each property in `rm_gp_props.sv` has two forms:

1. the intended SVA, in a comment marked `SVA:`, as a commercial tool would read it;
2. the same property compiled by hand into a Boolean assertion over a few monitor registers (a flag, a saved copy, a counter), which is what an SVA compiler builds
   from the operators. The hand-compiled form is what runs.

Writing the compilation by hand is itself a worked example of how a property automaton is built from a temporal formula (section 5). One consequence to
keep in mind: the SVA text in the comments was not run through any tool; the Boolean form was, and every claim below is about the Boolean form.

## 3. The design in two paragraphs

Writer side (`wclk`): a block is written into one of `2**AW` entry flops, indexed by a binary write pointer `wbin` that counts to `2*DEPTH`
(one extra bit tells full from empty). The pointer crosses to the read clock through a register holding its gray code (one bit changes per step) and a
chain of three flip-flops, then is decoded back to binary: that is `wbin_r`. Every entry is also copied bit for bit through its own two-flop chain into the read
clock (`ent_r`, `ENT_SYNC = 1`). The read pointer `rbin` crosses back the same way (two flops): `rbin_w`. The writer stops when it sees `DEPTH` blocks outstanding; its
view is old, so it is conservative.

Reader side (`rclk`): `fill = wbin_r - rbin` blocks are visible. On a slot clock (32 of every 33) a visible block is popped and output; with nothing visible, an idle block is inserted
if the output is not inside a frame, else the reader stalls one clock; on the one non-slot clock, an idle at the head is deleted if more than `HI` blocks are visible and the output is
not inside a frame. While the synchronised block lock is low the reader discards the buffer. The pointers are never reset; only the reader's counters and state are, by `rrst`.

## 4. The model

### 4.1 Two clocks: the Kripke structure is the set of interleavings

`rm_gp.sby` sets `multiclock on`; the clocks `wclk` and `rclk` are free inputs. At each solver step the solver picks any combination of "no edge", "write edge", "read edge" or
"both together". A path of the model is therefore one interleaving of two edge sequences, with every phase and every drift allowed. This is the course's first part in a concrete
form: the state is all registers of both domains; a transition is one global step; concurrency is interleaving (with simultaneous edges allowed, which the solver handles by sampling both
domains' flops before either updates). Steps with no edge are stuttering steps: they change nothing. Properties that are about the state only (for example "the buffer never holds more than
`DEPTH` blocks") are stuttering-invariant, which is why they can be checked at every step.

### 4.2 The synchronisers

AMD's macros are replaced by `xpm_formal.sv`: each crossing is a flop chain in the destination clock. A plain chain would give only the interleaving semantics, which already includes the
two orderings of a source and a destination edge that fall close together (old value seen, new value seen). It would not model metastability and routing skew, so the first flop of each chain may show
the old value of a bit for one more destination clock (`fv_sync_chain`):

* the choice is free per bit (`sk`), but only for a bit that changed at the latest source edge (`d != dlast`), only once per change (`held`), and never after the bit has shown its new value;
* the entry copies share one choice for the whole word (`SHARED = 1`): lateness only hurts, so "every changed bit late together" is the worst case and dominates every per-bit schedule;
  this is sound for the data-integrity claim and removes about 74 free bits per entry per step from the solver's problem;
* the pointer's bits are free independently, which is what lets a multi-bit binary value be seen torn and a gray value not (mutant `mut_binary_pointer`).

Not modelled: skew of more than one source clock (the constraint files and `report_cdc` cover it), and per-bit differences in resolution time beyond one destination clock. A first version let a bit be late at every
destination clock while the source value differed from the flop; its counterexample showed the write pointer going backwards (`001` then `000`): a bit that has shown its new value cannot show the old one again.
Adding that rule is an example of a modelling choice that the model checker forced into the open.

### 4.3 Assumptions (all in `rm_gp_props.sv`, next to what they justify)

| | Assumption | Why it is justified | What it costs |
|---|---|---|---|
| A1 | The reader is reset once before use (its first clock has `rrst` high). | The RTL gives `pace`, `in_frame`, `idle_run` no power-up value and relies on `rrst` (as `rate_match.sv` does); the pointers do have one. | Behaviour before the first reset is not covered. |
| A2 | Between two edges of one clock there are at most `RATIO = 3` edges of the other (counted exactly, `rn`/`wn`). | The real clocks are the same nominal rate within a few hundred ppm; 3:1 is far wider. It also makes both clocks tick infinitely often: the fairness assumption of section 7. | A ratio beyond 3:1 is not covered. The safety proofs hold for any ratio the pointer and the skew rule allow, but they were only run inside this band. |
| A3 | Progress task only: the lock is high, the writer is not in reset, the reader is reset only at its first clock. | These are the conditions under which the block is meant to pass data. | Progress with the lock toggling is not claimed. |
| - | Data are free, the lock, `rrst`, `wrst`, `clr_*` are free in the safety task. | none needed | none |

## 5. The properties, with their LTL and CTL forms

Write `G` for always, `F` for eventually, `X` for next (here "one clock of the property's domain"), `AG`, `AF`, `EF` for the CTL forms. The names are the assertion names in the source.

SVA is a linear-time language: a property is evaluated on one trace at a time, and a design satisfies it if every trace does. So an SVA `assert property (P)` means the LTL formula `A P`, which is the CTL* formula "on all
paths P"; branching statements ("there is a path where...") cannot be written. The one place the branching view appears is `cover`, which asks for one witness trace: it is the stand-in for `EF`. The proofs below that are
checked at every step are `G` (state predicate); the ones tied to an edge (`@(posedge clk)`) are `G` over the steps where that clock rises.

| ID | In words | LTL / CTL | Kind | Proved as | A mutant that breaks it |
|---|---|---|---|---|---|
| P1 `p1_no_overflow`, `p1b_bound` | the writer never writes over an unread block; at most `DEPTH` blocks are outstanding | `G (wr_en -> outstanding < DEPTH)`, `G (outstanding <= DEPTH)` | safety, invariant | k-induction | `mut_overflow` |
| P2 `p2_wview` | the writer's view of the read pointer is old, never ahead | `G (lag_r <= wview <= DEPTH)` | safety, invariant | k-induction | `mut_binary_pointer` |
| P3 `p3_rview` | the reader's view of the write pointer is behind the real one, and never behind the read pointer | `G (lag_w <= true_fill)`, `G (fill <= true_fill)` | safety, invariant | k-induction | `mut_unsynced_pointer`, `mut_binary_pointer` |
| P4 `p4_no_underflow` | a read, delete or drain only when a block has crossed and was written | `G (rd_en -> fill != 0)` | safety | k-induction | `mut_underflow` |
| P5 `p5_gray_w/r` | each pointer's gray code changes at most one bit per own clock | `G (popcount(gray(wbin) ^ gray(wbin_prev)) <= 1)` | safety | k-induction | `mut_gray_step` |
| P6a `p6a_...` | an idle is inserted only between frames (judged from the output stream, not the RTL's flag) | `G ((empty slot clock && output appears next clock) -> !spec_in_frame)` | safety | k-induction | `mut_insert_in_frame` |
| P6b `p6b_...`, P6c | an idle is deleted only between frames; the RTL's frame flag equals the spec's | `G (do_del -> !spec_in_frame)`, `G (in_frame == spec_in_frame)` | safety | k-induction | `mut_delete_in_frame` |
| P7 `p7a`, `p7b` | only pure idle blocks are deleted: the idle flag is set only for the idle pattern (raw inputs), and the flag the reader sees is the one written | `G (wr_en && flag -> idle_pattern)`, `G (del of item N -> flag written for item N)` | safety | k-induction | `mut_delete_any` |
| P8 `p8a`, `p8b` | data integrity: the block popped for write number N is the block that was written, and is on the output one read clock later | `G ((pop of item N) -> head == written[N])`, then `X (out == written[N])` | safety, with a symbolic item | k-induction | `mut_wrong_entry` |
| P9 `p9_consume_after_write` | an item is consumed only after it was written (order) | `G (consume N -> written N)` | safety | k-induction | `mut_wrong_entry` |
| P10 `r1`, `r2` | progress: a written item is eventually consumed | LTL `G (written N && !consumed N -> F consumed N)`; CTL `AG (... -> AF consumed N)`; proved as a bounded response through a ranking function (section 7) | liveness, as safety | bounded model check (not closed by induction) | `mut_no_pop` |
| covers | the proofs are not vacuous: pop, insert, full buffer, stall, wrap, delete are reachable | `EF (event)` | reachability | cover | - |

Why "the block popped for item N" is a property of the whole design and not of one entry: section 8.1.

The helper invariants (`h1` to `h11`, `p`-less names in the source) are also asserted and also proved; they are what makes the k-induction close (section 6).

## 6. BMC and k-induction, and the counterexamples to induction

**BMC** (`safety_bmc`, `progress_bmc`) unrolls the model for `d` steps from the initial state and asks a solver for a violation within `d`. A pass means "no violation in the first `d` steps": an under-approximation of
the claim, exact only up to `d`. With two free clocks one clock period is two solver steps (edge, no edge), and a block takes about ten read clocks to cross, so useful depths are tens of steps.

**k-induction** (`safety_prove`) proves two things. Base: no violation in the first `k` steps (BMC to depth `k`). Step: any `k` consecutive states that all satisfy the property, started from ANY state (not
only a reachable one), are followed by a state that satisfies it. If both hold, the property holds on every reachable state. The step starts in unreachable states, so it can fail without the property being false:
the solver returns a counterexample to induction (CTI), a run from an unreachable start state. A CTI is repaired by strengthening: adding a helper invariant that excludes the start state. All CTIs below were
read from the trace and each led to one invariant or one change to the harness.

1. *Clocked invariants constrain nothing when the clock does not tick.* The first helper invariants were written `assert property (@(posedge wclk) ...)`. The CTI had the first rising read edge at the end of the window: the
   hypothesis was never applied, the state at its start was arbitrary. Cure: state invariants are asserted in `always_comb`, i.e. at every step (macro `FV_BOTH`). This is the multi-clock face of "stuttering":
   a state predicate has to be checked at stuttering steps too, or the induction hypothesis is vacuous.
2. *Tracker state not tied to the pointers.* A CTI with the tracked item "written" while `wbin` was still 0. Helpers H1 (`!written -> wbin <= tp`), H8 (`!written -> rbin <= wbin`), H2/H3 (an unconsumed, written item lies inside the
   window of unread blocks), H3b (`consumed -> written`).
3. *Synchroniser chain contents arbitrary.* A CTI with the third stage of the write pointer showing a value ahead of `wbin`. H5: along `wbin, g, dlast, s0, s1, s2` the distance `(wbin - decode(x))` is nondecreasing and the last one is at most
   the real fill. This is the invariant of a pipeline whose stages hold older and older copies of one counter.
4. *The data copy against the pointer stage.* The CTI for P8 had the pointer visible while the data copy still held the old bit. H4 (the entry flop holds the written bit while the item is unread) and H6: "pointer stage 0 shows the item
   -> data stage 0 holds the bit or is late; stage 1 -> data stage 0; last stage -> data stage 1". H6 is the CDC argument written as an invariant.
5. *The registered check outliving its item* (`chk_out` set with the item unwritten): `done -> written`, `chk_out -> done`.
6. *The gray property's own history register* (`wbin_q`): the CTI started with `wbin_q` unrelated to `wbin`; making P5 a state invariant over the pair (not an edge assertion) closed it.

After these, `safety_prove` closes at induction depth 8 for the shipped `AW = 4` (about 8 s) and at depth 24 for `AW = 2`; the induction step itself is solved immediately, so the depth is the base-case depth the job was given.
A pass of the step at depth 1 would mean the invariants alone are inductive; the proofs here were run at the depths in section 10.

## 7. Safety, liveness, fairness and the ranking function

A safety property says "nothing bad happens": every violation has a finite witness. Everything in P1 to P9 is safety. A liveness property says "something good eventually happens": a violation needs an infinite
trace (`G (written -> F consumed)` is violated by a trace on which the item is never consumed, however long you look). Finite BMC can refute a safety property but never a liveness one; and liveness is usually false without a
fairness assumption: a trace on which the read clock stops forever never consumes anything.

* **Fairness here** is A2: both clocks keep ticking, and not too far apart in rate. In LTL it would be an assumption `GF wclk_edge && GF rclk_edge` added in front of the property; SVA cannot express that in the free tool, so the model
  enforces a stronger, finite version: no more than `RATIO` edges of one clock between edges of the other. That is a safety assumption.
* **From liveness to safety.** The usual step is a ranking (variant) function: a number computed from the state that is bounded, decreases with every clock while the item waits, and forces consumption when it reaches its minimum.
  `rk` in `rm_gp_props.sv` is `vis + LK + (q + 1) + NS`: read clocks until the pointer shows the item (`vis`: a table over the pointer's chain stages, plus the wait for the next write clock, `RATIO - rn`), until the lock arrives (`LK`),
  one per block queued ahead (`q`), and one if the pace counter's non-slot clock falls inside the window (`NS`). The three checked facts: `rk <= RMAX` (R1, `RMAX = RATIO + 4 + 3 + DEPTH + 1`); while the item is unconsumed, `rk` is strictly lower
  than at the previous read clock (R2); `rk >= 1`. Together they say: the item is consumed within `RMAX` read clocks of being written, a bounded response, which is a safety property and implies the liveness one under A2 and A3.
* The ranking function had to be right in detail. The first version (`rk` using a counter that restarts when a write edge is observed) was refuted by BMC in 3 steps: the write edge that wrote the item is observed after the fact and reset the
  counter. Counting edges since the last write edge exactly (`rn`, two single-domain counters and a snapshot) fixed it. The second version assumed "the late bit has been used, so the next clock is sure to take the new value"
  for any held bit; BMC found a run where the held bit belonged to an older pointer step. The late bit that matters is the one the pointer flips over this item (`ibit`).

Status: R1 and R2 are checked by BMC to the depth in section 10 (`progress_bmc`) and the mutant that removes all slot clocks is caught. They are not closed by k-induction: the induction step still has counterexamples whose start states have inconsistent
synchroniser stages (a lock chain with a 1 behind a 0 was one, and was cured by H10; the next one is a ranking value inconsistent with the stored previous rank) and the depth-4 induction run did not finish in several minutes. So the progress result is
"no violation of the bounded response within the BMC depth" and not a proof. Closing it needs two or three more invariants relating the stored previous rank to the chain stages; it is left as the first follow-up.

SVA's `s_eventually` would state the unbounded form directly. The bounded form `##[1:RMAX] done` states the same thing as a finite window; the difference is exactly the difference between the two classes above: `s_eventually` only fails on an infinite trace (it needs
a liveness engine, k-liveness or a fairness-aware tool), the bounded form fails on a finite one and so BMC and induction can handle it.

## 8. Abstraction: how the state space stays small

1. **The symbolic entry** (data abstraction by a free constant). Instead of tracking all `DEPTH` entries, the proof picks one write sequence number `tp` once (a register that reloads itself, unconstrained at step 0, constant afterwards), records the block written when the
   write pointer is at `tp`, and checks it where the read pointer is at `tp`. Because `tp` is any value, a pass is a pass for every item; the checked state is one item, not the whole array.
2. **The bit slice** (`KB`). The datapath is bit-parallel; the proof follows one bit position of the 74-bit entry (`KB`: 0 to 63 data, 64 to 71 control, 72 ordered-set flag, 73 idle flag). One bit instead of 74 cut the data-integrity proof from "no result in minutes at depth 17" to seconds.
   Representative bits in CI: 0, 7, 39, 63, 64, 71, 72, 73; all 74 once, locally.
3. **The shared lateness choice** (section 4.2): sound because lateness is monotone.
4. **Small parameters**: the proofs run at `AW = 4` (the shipped 16 entries), 2 and 1. Pointer wrap behaviour is the same code at each size; a bound on `AW` is not a parametric proof.
5. **Cone of influence and `FV_PROGRESS`**: the progress task removes the data-side invariants, which do not appear in the ranking.

What each abstraction costs, in the course's terms: abstractions 1, 2 and 3 are existential-universal safe over-approximations for the property they serve (a pass implies the concrete pass, because every concrete behaviour is a behaviour of the abstract model
or is covered by a free choice); the assumptions A1 to A3 and the parameter sizes are restrictions of the environment or of the instance, so they reduce what a pass means rather than over-approximate. The bit slice is a symmetry/independence argument (a form of
data independence); the skew model is an over-approximation of the physical behaviour only up to the stated skew bound.

**Equivalence and partial-order links.** Stepping the two clocks one at a time (interleaving) is the plain concurrent semantics; partial-order reduction would notice that a write edge and a read edge that touch disjoint state commute and explore one order;
the model does not reduce, the solver sees all interleavings and that is cheap at this size. The "no-edge" steps are stutter steps, and the properties are stuttering-insensitive (no `X` on the global step), which is why the clock choice does not change their truth value.
The mutant checks are a kind of observational test of the proofs: each mutant is a design that is not equivalent to the original, and the proof tells them apart.

## 9. Mutants

Each mutant is a regular-expression change to a throw-away copy of the RTL (`run_formal.py` checks that the text changed). The deletion mutants use a pace period of 4 instead of 33 in their copy only, because the deletion branch fires on the one non-slot clock in 33 and
would be out of the bounded check's reach; the unmutated proofs keep 33.

| Mutant | The bug | Caught by (first failing assertions) |
|---|---|---|
| `mut_overflow` | `f_full` allows one block too many | P1, P1b, P2 |
| `mut_underflow` | `can_read` always true | P4 |
| `mut_gray_step` | write pointer steps by 2 | P5, H5 |
| `mut_binary_pointer` | the pointers cross as binary, not gray (`FV_BIN_CROSSING`) | H5, P3 (tearing) |
| `mut_unsynced_pointer` | the reader uses `wbin` straight from the write clock | P3 (it reads beyond what crossed), H5 |
| `mut_wrong_entry` | the reader selects the neighbouring entry | P8a, P8b |
| `mut_insert_in_frame` | idle inserted inside a frame | P6a |
| `mut_delete_in_frame` | idle deleted inside a frame | P6b |
| `mut_delete_any` | any block deleted (checked in the idle-flag slice) | P7b |
| `mut_no_pop` | no slot clock: nothing is ever popped | R2 (progress) |

A mutant that was NOT caught, and what it taught: shortening the write pointer's chain from three flops to two (`.DEST_SYNC_FF(2)`, the design's own rule "the pointer needs one flop more than the data copy") was not refuted by BMC. Under this model's skew bound
(a bit may be late only until the next source edge, less than one source clock) the gray register already adds one source clock between the entry write and the pointer's first change, so a two-flop pointer is also safe. The third flop is margin against a skew of more than one clock,
which the model does not claim to cover. This is a case where the proof is honest about its assumptions: the design rule is stronger than the model needs, and the model cannot justify the extra flop.

## 10. Results

RESULTS_PLACEHOLDER

## 11. Known gaps

* Properties are the Boolean forms; the SVA text beside them was not run (the free front end cannot read it).
* Progress (R1, R2) is bounded model checking to a stated depth, not an unbounded proof (section 7).
* Parameters: `AW` 1, 2, 4; `ENT_SYNC = 1`, `HI = 1`, `MIN_KEEP = 0` (defaults). The `ENT_SYNC = 0` variant (direct read of entry flops) and the other `MIN_KEEP` and `HI` values are not proved.
* The clock band is 3:1; skew above one source clock and metastability beyond one destination clock are outside the model (report_cdc and the constraint files are the evidence there).
* The data-integrity proof follows one bit position at a time; the 8 representative bits are proved in CI, all 74 once by the full set.
* The ITCH/MoldUDP64 parser properties of the brief were not written: brief 110 (PR #238) was not merged when this work started, so the rate matcher was done first and the parser left for a later brief.
* The reader's state before its first reset (A1) and a reader reset in the middle of operation (covered in the safety task, not in the progress task).

## 12. Exercises

1. Remove the `held` rule from `fv_sync_chain` and rerun `safety_bmc`: what is the shortest counterexample, and which property fails first? Explain it as a trace of a gray pointer going backwards.
2. Change `RATIO` to 1 (`-D FV_RATIO=1` in a copy of `rm_gp.sby`): what does the model then say about phases, and why does `progress_bmc` bound shrink?
3. Write P8 in CTL with a quantifier over the item: `AG (written(N) -> AF consumed(N))` versus the safety form used here; which part needs fairness?
4. Delete helper H6 and read the counterexample to induction. Which stage of the data copy and which stage of the pointer disagree, and why is that state unreachable?
5. Make the bit slice `KB = 73` and `KB = 5`; which control decisions of the reader depend on which entry bits, and why is that the only data dependence the bit slice has to respect?
6. Start from the CTI of the ranking function (section 7), add the invariant that links the stored previous rank to the chain stages, and close `progress_prove`.
