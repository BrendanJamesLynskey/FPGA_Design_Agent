# What if a human had disagreed? Six counterfactual decisions, measured (brief 136)

Written 2026-11-21 (brief 136). On 2026-11-21 the owner delegated the open decisions to the planner as learning material ("I take whatever you recommend": `_handoff/fpga_agent/owner_decisions_2026-11-19.md`, decision 23). In a real project a human decides these, and a human may decide differently. For six of them this note states the recommendation, the alternative a human might pick and why, **measures** what the alternative changes where that is cheap (simulation, Lean, the repository's own records; no board, no Vivado), and says what the agent should do. Machine-readable form: [results/b136/what_if.json](../results/b136/what_if.json); the scripts and records are in [results/b136](../results/b136/README.md).

How to read it: a number is **measured** only where a record path is given; arithmetic on measured numbers is called arithmetic; anything else is called assumed or not measured. Every "agent response" is a proposal for the agent's training material, not something built.

Summary of what the six alternatives change:

| # | Human alternative | What it changes (measured) | Agent response in one line |
|---|---|---|---|
| 1 | test only +-100 ppm | of 12 seeded bugs, the +-100 set catches all but one that the full set catches (`mut_delete_any`, caught only at +300 ppm); 2 are caught by neither set | keep +-300 ppm in the plan and name the bug only it catches |
| 2 | cut-through default | an order leaves before its frame's check for 0 %, 0 % and 8.5 % of candidates at 1, 3 and 6 messages a packet; the speculative start is 4.8 clocks (29.8 ns) faster than starting at the verdict | accept, and make risk count each unverified order as live exposure; report the share with its assumed frame-error rate |
| 3 | Lean statement at 32 words | the theorem holds at 32 with the proof text unchanged; the RTL equations fail at 33 words (all-ones payload) | accept the wider bound; state that the RTL's own length is fixed at 59 bytes (30 words) |
| 4 | E <= 16, tick-to-trade <= 20 clocks as targets | no recorded board run meets either; the best, `rm_gp_bypass`, is E 17 and 29 clocks; the pre-registered `lat_all3_bypass` is E 16 and 22 | do not re-plan on the numbers: first make the human name the definition; then propose loop timing |
| 5 | reject `gray_sample` as too weak | the bit-wise statement is proved (kernel axioms only); it needs the one-step condition, which a skew of one source clock breaks | re-state, prove, and ask the RTL model for a per-bit skew bound |
| 6 | eye width >= 0.75 UI | LPM 0.71875 UI fails; DFE 0.75 UI meets it exactly; the grid step is 0.03125 UI | scan the edges finer and on DFE before claiming either way |

## 1. B96-F-OFFSET narrowed to +-100 ppm

**Decision and recommendation.** `B96-F-OFFSET` says the rate matcher holds at +-100 and +-300 ppm. The recommendation keeps both. The alternative: the human keeps only +-100 ppm, the 802.3 limit per end (the two ends together can differ by up to 200 ppm, so +-100 is the spec's per-end figure and the extra reach to +-300 is margin).

**Why a human might pick it.** It is the standard's number, each extra point costs bench time (below: about 100 s of simulation per point), and a point beyond the standard tests something the link is not required to survive.

**Measured.** [results/b136/run_mutants_ppm.py](../results/b136/run_mutants_ppm.py) takes `rate_match_gp.sv` (the shipped buffer, `rm_gp`) and applies one seeded bug at a time to a throw-away copy: the nine of brief 115's ten formal mutants that a simulation can run (`mut_binary_pointer` needs the formal harness's `FV_BIN_CROSSING` define and is not run) and three added here whose effect depends on how fast the buffer fills or drains (`mut_no_delete`, `mut_delete_late`, `mut_no_stall`). Each is built with brief 96E's cocotb bench (the Python partner is the stimulus: frames from 64 to 1000 bytes with gaps of 1 to 4 idle blocks, 500 frames a point, the same seed) and run at 0, +100, -100, +300 and -300 ppm. A bug is **caught** at a point if a frame offered comes out changed or lost, the overflow counter is above 0, or the output carries X (the *functional* verdict a human's test would use). A **stricter** verdict also counts any difference from the Python twin (`model/ratematch.py`), which catches an idle block inserted inside a frame (the bench's frame parser tolerates it). Control: the unmutated RTL is clean at all five points under both verdicts. Records: [mutants_ppm.json](../results/b136/mutants_ppm.json) (per point: frames, inserts, deletes, stalls, fill, twin mismatch).

Caught at the point (1) or not (0), points in the order 0, +100, -100, +300, -300 ppm; "narrow" = the +-100 points only, "full" = all five:

| Seeded bug | Functional verdict | Stricter verdict (also the twin) | Needs an offset to be seen? |
|---|---|---|---|
| `mut_underflow` (reads when empty) | 11111 | 11111 | no: seen at 0 ppm |
| `mut_gray_step` (pointer steps by 2) | 11111 | 11111 | no |
| `mut_unsynced_pointer` (unsynchronised pointer) | 11111 | 11111 | no |
| `mut_wrong_entry` (reads the neighbour) | 11111 | 11111 | no |
| `mut_no_pop` (never pops) | 11111 | 11111 | no |
| `mut_insert_in_frame` (idle inserted in a frame) | 00000 | 00101 | yes: seen at -100 and -300 (2 and 6 cases) |
| `mut_no_stall` (idle output instead of waiting when empty in a frame) | 00000 | 00101 | yes: -100 and -300 |
| `mut_no_delete` (idles never deleted) | 00000 | 01010 | yes: +100 and +300, as a difference from the twin; no overflow in 500 frames |
| `mut_delete_late` (delete only above 14 blocks) | 00000 | 01010 | yes: +100 and +300, same |
| **`mut_delete_any`** (delete any block, not only an idle) | **00010** | **00010** | **yes: only at +300 ppm** |
| `mut_overflow` (writer overwrites one block too many) | 00000 | 00000 | not reached in 500 frames at any point |
| `mut_delete_in_frame` (delete inside a frame) | 00000 | 00000 | not reached: this stimulus has no idle block inside a frame |

**Result.** The +-100 ppm set misses **one** bug that the full set catches: `mut_delete_any`. It deletes a data block instead of an idle, but only when a deletion happens to land on one; at +-100 ppm the 500-frame run had 2 deletions (and no data block was hit), at +300 ppm 7, and one of them cut a frame (1,602 cycles differ from the twin, frames not equal). The nine other caught bugs are caught by the narrow set already, five of them without any offset and four only by the stricter verdict. Two seeded bugs are caught by **neither** set on this bench (`mut_overflow`, `mut_delete_in_frame`): their conditions (a buffer that fills to its 16 blocks, an idle block inside a frame) are not reached by 500 frames of this stimulus at any ppm, so the bench's own limit, not the ppm, hides them. Brief 115's formal proofs do catch both (`mut_overflow` by `p1_no_overflow`, `mut_delete_in_frame` by `p6b_delete_only_between_frames`). Time scales, arithmetic: a buffer that never deletes needs about 14 extra blocks to overflow, which is about 47,000 clocks at +300 ppm and 140,000 at +100 ppm, 10 to 30 times this run's length.

**Caveats.** One stimulus, one seed, 500 frames a point, so +-100 ppm saw only 2 slips per point: a single data block cut is luck at that rate, and the +300 ppm catch of `mut_delete_any` is one catch, not a rate. The twelve bugs are not a sample of all bugs.

**Agent response.** Do not drop +-300 on the strength of the standard alone: say that on this bench the narrow set loses one of twelve seeded bugs (the data-deleting one) and that the full set is the cheaper way to see it, then let the human decide knowing that. Offer to keep +-300 as a simulation-only point (the board loopback has no offset at all, `B96-F-OFFSET` stays hardware-open either way). Report the two bugs neither point set reaches and point to the formal proofs as what covers them; do not claim the narrow bench covers them. If the human insists on +-100, keep the one-line note in the testplan that the `mut_delete_any` bug is only seen at +300 ppm.


## 2. Cut-through as the default instead of STRICT (brief 127)

**Decision and recommendation.** Brief 127's receive path starts the order frame before the packet's frame check sequence (FCS) is known (the "late verdict"). Two policies handle a bad packet. **Cut-through** (127's default, `IT_CTRL` bit 5 clear): the order leaves; if the verdict is already bad when the order's last word goes, the frame is poisoned (sent with a wrong FCS and dropped by the receiver), and if the verdict is still unknown the order leaves unpoisoned and is counted `ord.unverified`. **STRICT** (bit 5 set): an order whose packet's verdict is not yet known and good is poisoned. The planner's recommendation is STRICT for a design that will trade; the owner's wording for this brief is "cut-through as default instead of STRICT".

**Why a human might pick cut-through.** It never loses an order that a good frame would have produced, and it is what brief 110 did; STRICT kills those orders (8.5 % of them at 6 messages a packet, below).

**Measured** (brief 127's records, PR #253, copied into [results/b136/inputs_b127](../results/b136/inputs_b127); the arithmetic is [results/b136/cut_through.py](../results/b136/cut_through.py), output [cut_through.json](../results/b136/cut_through.json)):

- The window: with a bad frame, an order is poisoned if the bytes after its trigger message are 126 or fewer with the speculative start, and escapes from 128 (start at the verdict: 166 and 168). `fcs_window_unit_sim.json`.
- Share of candidate orders whose tail is longer than the window (the seeded generator, 20 seeds of 400 messages, `fcs_window_share.json`):

| Messages per packet | Candidates | Outside the speculative window | Outside the start-at-verdict window |
|---|---|---|---|
| 1 | 984 | 0 % | 0 % |
| 3 | 1,015 | 0 % | 0 % |
| 6 | 988 | 8.5 % (84) | 1.0 % (10) |

- **Share of orders sent for frames that later fail the check** = (that share) x P(frame fails). P(frame fails) was **not measured** (the generator's frames are good). Arithmetic on an assumed grid, per million orders at 6 messages a packet: 0.0001 at P = 1e-9, 0.085 at 1e-6, 85 at 1e-3, 850 at 1e-2; at 1 and 3 messages a packet zero at every P. Given that a frame fails, 8.5 % of the orders it triggered have already left at 6 messages a packet.
- Latency gained: from the first byte-complete event T to the start strobe, 5 to 6 clocks speculative against 10 to 11 at the verdict (Icarus, real MACs, `latency_sim.json`); whole core, GT port to GT port, **16.8 clocks (104 ns) against 21.6 (134 ns): 4.8 clocks, 29.8 ns** (report 127, xsim 2026.1, four phases). STRICT with the speculative start has the same 16.8 for the orders it keeps; its cost is the orders it poisons (the same 0 / 0 / 8.5 %), not time.

**What the risk logic must then do** (design reasoning; nothing of this was built or simulated in brief 136): an order that has left cannot be recalled (127, item 4), so (1) count every `ord.unverified` order as live exposure at full size in the position and notional limits until its packet's verdict arrives, because it may be spurious; (2) when a verdict arrives bad and an unverified order is outstanding, raise a flag and let the host cancel it (127 has no cancel path; `risk_glue` has no release input, a follow-up in 127's list); (3) cap the unverified orders in flight (for example one) and stop sending speculative orders after a number of bad verdicts (`pkt_err`) in a window; (4) log the share of unverified orders and the frame-error rate seen, so that the policy is chosen from the real feed's numbers, which are unknown here.

**Agent response.** Accept the human's cut-through, apply (1) to (4) as requirements of the risk block, and put the table above, with the assumed frame-error grid labelled as assumed, in the sign-off page next to the choice. Offer the third option (start at the verdict: 4.8 clocks slower, window 1 % at 6 messages a packet) as the setting that keeps cut-through's no-lost-orders property with a smaller window. Do not tell the human the exposure is small until the real packet lengths and frame-error rate are measured.

## 3. B96-F-LEAN-CKSUM-TCP at 32 words instead of the proved 30

**Decision and recommendation.** `Cksum.rtl_tcp_correct` (`formal/lean/Cksum/Spec.lean`) is proved for payloads of up to 30 sixteen-bit words, the 59-byte payload of brief 119's `tcp_fast.sv` (`PAYLEN = 59`, 30 words). The alternative: state it at 32 words, the capacity of the RTL's 512-bit `pay` register (32 words) and of its 21-bit payload sum register (the sum of 32 words of 0xFFFF is 2,097,120, which fits in 21 bits, 2,097,152).

**Measured** ([results/b136/lean/run_lean.sh](../results/b136/lean/run_lean.sh), log [run_lean.log](../results/b136/lean/run_lean.log); in a scratch copy, `formal/lean` is not edited):

- Changing the hypothesis `pw.length <= 30` to `<= 32` and nothing else: **the theorem builds**, with the same proof text (the proof used the bound only through `omega` and the existing lemma `sum21`, which already assumed 32). `#print axioms` lists the same five axioms as before (`propext`, `Classical.choice`, `Quot.sound` and the two `bv_decide` axioms), so the tier is unchanged.
- At 33 words the claim is false for the RTL's equations: with every payload word 0xFFFF, the RTL's checksum equals the Internet checksum for 0 to 32 words and is **wrong for 33 to 39** (the first example: 0xAFB2 against 0xAF92, a difference of 32 = 2^21 mod 65535, the 21-bit sum wrapping). `Probe33.lean` evaluates the transcribed equations of `Spec.lean`, not the RTL.
- What the RTL does at 33 words: it cannot be given 33. `PAYLEN` is a fixed localparam (59 bytes), `pay` holds 64 bytes, the order's payload is built by `ouch_enter` at a fixed size; there is no length input. Nothing was simulated for a changed `PAYLEN`; the statement about 33 is about the transcribed equations only (the 21-bit `sump` would wrap and `pay` would overflow its 512 bits).

**Agent response.** Take the 32-word statement: it is stronger, no proof work was needed, and its bound is the register's own capacity. Record, next to the statement, that the bound is a capacity of two registers and that a payload above 32 words needs wider `sump` and `pay` and a new proof (the hypothesis change would then fail to build, which is the useful signal). Because the statement changed, the frozen-statement gate requires a new approval (`lean_approvals.yaml` is empty for it); the proved file in `formal/lean` was **not** changed by this brief.

## 4. Latency bounds as targets: E <= 16 and tick-to-trade <= 20 clocks

**Decision and recommendation.** The test plan holds regression bounds (`designs/b96_kr260_10g/verif/testplan.yaml`: E <= 22, L <= 55, D <= 13 clocks; simulated tick-to-trade <= 14; `rm_gp_bypass` E <= 19.5): a build that gets worse fails. The alternative is to make E <= 16 and tick-to-trade <= 20 clocks the **targets**, so that a build that does not reach them fails.

**Why a human might.** Targets pull the design toward what a trading customer wants and make the agent plan for them; a regression bound only guards the past.

**Measured** (all board medians of 100 restarts, from the committed records; [results/b136/latency_targets.py](../results/b136/latency_targets.py) and [latency_targets.json](../results/b136/latency_targets.json)). Tick-to-trade on the board is L - E (docs/latency_definitions.md), in clocks of 6.206 ns:

| Build (record) | E | L - E | E <= 16 | L - E <= 20 |
|---|---|---|---|---|
| default control (97C) | 20 | 30 | fails by 4 | fails by 10 |
| `lat_agent_both` (97C) | 20 | 28 | fails by 4 | fails by 8 |
| `lat_all3` (97C) | 20 | 26 | fails by 4 | fails by 6 |
| 96C rate matcher, macro FIFO | 24.5 | 36.5 | fails by 8.5 | fails by 16.5 |
| `rm_gp` (96E) | 21 | 33 | fails by 5 | fails by 13 |
| `rm_gp_bypass` (96F1b) | 17 | 29 | fails by 1 | fails by 9 |
| `rm_gp_ml` (113) | 21 | 32 | fails by 5 | fails by 12 |

In none of the nine runs was a single restart's E at or under 16 (0 of 100 each). **No recorded board run meets either target.** Not recorded on a board: `lat_all3_bypass` (brief 126), pre-registered at E 16.0 (band 15.6 to 16.6) and L - E 22 (band 21.6 to 22.6): it **fails the tick-to-trade target by about 2 clocks** and is at the edge of the E target. Under the **simulation** definition (price word to order start, zero-latency stand-in) the same words give a different verdict: `control` 10.7, `lat_all3` 7.7, `lat_all3_bypass` 7.6, `rm_gp_bypass` 12.9 clocks all pass 20; brief 127's whole-core GT-to-GT 16.8 passes and its start-at-verdict 21.6 fails. The same number "20 clocks" passes or fails depending on the definition, which is the main finding.

**What design work the agent would propose** (from `docs/latency_definitions.md`, 96F, 96F2, 97C and 126; predictions, not measurements): (1) run the pre-registered `lat_all3_bypass` board test first; it either confirms E 16 or shows what the bypass and the cuts do not add up to. (2) For tick-to-trade, the remaining items are the receive-to-transmit fabric crossing (96F predicted loop timing saves 3 to 4 clocks; applied to 126's 22 clocks that is **18 to 19 by arithmetic**, which would meet 20), but 96F2 found 96F's V1 mis-specified (AMD derives the receive and transmit clocks from one transmit clock with a fabric DPLL, XAPP1276), the saving rests on a GTY figure that is unconfirmed for this GTH, and it needs a new design and a board session. (3) E <= 16 has 0 clocks of margin in the prediction; what is left on E is inside the transceiver and the module, which no RTL change reaches (97's plan puts about 15 of E's 20 clocks there); the agent should say so and not promise it. (4) Report any claim against the definition: board L - E includes the optical module's own delay and is a first-bit-in to first-bit-out figure (FIFO), not STAC-T0's actionable latency.

**Agent response.** Before re-planning, ask the human which definition the targets use, and write it into the target text (the latency-path-clarity rule). Then mark every current build as failing the board target, keep the old bounds as regression bounds alongside (so nothing gets worse while the targets are chased), and queue (1) then the loop-timing redesign as the one item that can reach 20.

## 5. A rejected Lean statement: `gray_sample` is too weak

**Decision and recommendation.** `Gray.gray_sample` says: if the sampled gray value *is* the code of the old count or of the new count, it decodes to the old or the new count. It is proved (kernel axioms only, brief 125) and accepted by the planner on delegation. A human objects: "a sample may also be taken mid-glitch". They are right that the hypothesis is not what a synchroniser delivers: a sample taken while the pointer changes is not the old bus or the new bus, it can be any **mixture of bits**, each bit resolving to its old or its new value.

**The statement the human would want** (written in this brief, [results/b136/lean/Stronger.lean](../results/b136/lean/Stronger.lean)):

`gray_sample_bitwise (hn : 0 < n) (b g : BitVec n) (h : forall j < n, g[j] = (bin2gray b)[j] or g[j] = (bin2gray (b+1))[j]) : gray2bin g = b or gray2bin g = b + 1`

**Measured.** It builds in the scratch copy (`run_lean.sh`) with `#print axioms`: `propext`, `Classical.choice`, `Quot.sound` only. The proof uses `gray_step` (consecutive codes differ in exactly one bit): every bit except one is the same old or new, so the mixture is the old code or the new code, and the old theorem finishes it. So the stronger statement costs one short proof and **adds nothing to the trust base**. In the same file, an `example` shows what the statement does *not* cover: a bus whose bits come from codes **two** steps apart (width 3, counts 3 and 5, gray 010 and 111) can read 011, which decodes to count 2, below both (`decide` proves it, and 011 equals none of the codes of 3, 4, 5).

**What the agent would need from the RTL model.** The stronger theorem is true only under the condition that each bit of the sampled bus is the old or the new value of **one** step. That is a statement about the circuit that Lean does not see and the repository does not currently state in one place: (1) a bound on the skew between the bits of the crossing, below one source clock (`rate_match_gp.sv` assumes it in its comments for ENT_SYNC = 1; the formal proof of brief 115 models it as one-clock lateness); (2) that the pointer steps at most once per source clock and the destination samples each bit through its own first flop (the two-flop output of the synchroniser, whose second flop only delays); (3) the clock-ratio assumption; (4) the constraint that enforces (1) (`set_max_delay -datapath_only`, `report_cdc`). Without (1) the theorem is correct and useless: the two-step example is what a larger skew produces, and then `fill = wbin_r - rbin` can go backwards. The agent should ask the RTL-model owner for (1) as a stated, checked assumption, write it as a hypothesis of a second theorem about a sequence of samples, and not claim that the crossing is safe from the Lean proof alone.

**Agent response.** Replace `gray_sample` by `gray_sample_bitwise` as the statement offered for approval (keeping the old one as a lemma it rests on), re-record the build, and say in the matrix row that the link between the statement and the circuit is the skew bound, which is a manual claim. The proved file in `formal/lean` was **not** changed by this brief (the new file lives in `results/b136/lean`), so no approval hash moved.

## 6. A tighter eye bound: width >= 0.75 UI at BER 1e-9

**Decision and recommendation.** requirement `B96-P-EYE` requires an eye width of at least 0.5 UI (LPM equaliser, BER 1e-9). The alternative sets 0.75 UI. The measured width is 0.71875 UI.

**Measured** ([results/b136/eye_target.py](../results/b136/eye_target.py), [eye_target.json](../results/b136/eye_target.json); the committed captures of 2026-11-20 10:51, `results/b96d/hw/20261120_105134/`, read with the same code that wrote `summary.txt`):

- LPM at BER 1e-9, four scans (`lpm_1` to `lpm_4`): width 0.71875 UI each, height 360 mV. **Fails 0.75 by 0.03125 UI, one grid step.** DFE (`dfe_1`, BER 1e-9): **0.75 UI, height 288 mV: meets 0.75 exactly**, with no margin.
- The measurement's own resolution: the grid steps 2 DRP counts of 0.015625 UI, that is 0.03125 UI, so a width is known to a step. `capture.eye_at` gives the width's grid bounds: LPM 0.6875 to 0.75 UI, DFE 0.71875 to 0.78125. For the LPM the upper bound only just reaches the target, so the target is not decided by the grid; a log-linear interpolation of the bathtub edge between the last open point and the first closed one (an **estimate**, assuming that shape, using the zero-error bound for the open point) gives **0.723 UI** for LPM and **0.758 UI** for DFE.
- The five `tx_*` scans (TX swing 16 and 8, post-cursor 4 and 8, pre-cursor 4) ran at BER **1e-7**, not 1e-9; each reads 0.71875 UI. They cannot say anything about a 1e-9 target, and show only that those TX changes moved no edge by a grid step at 1e-7.
- One module, one fibre (0.17 m), room temperature (27 C), one session; four repeats of the LPM scan agree because they are the same setup, not independent.

**Equaliser settings to try** (proposals; not measured at 1e-9): DFE is the only recorded setting at or above the target, at the price of 72 mV of height; the LPM's remaining knobs in the capture settings are the TX swing, pre and post emphasis (no change seen at 1e-7); a second module and a longer or shorter lead would show whether the width is the link's or the receiver's.

**Agent response.** Do not report 0.75 as passed or failed on this data. Propose one board action (owner's session, laser and board rules apply): rescan the two edges of the LPM and DFE eyes on a finer grid (hstep 1: 0.0156 UI) at BER 1e-9, repeated, with the TX variants at 1e-9; then decide. Until then record the target as **met by DFE at the grid's resolution, not met by LPM**, and say the margin is one grid step.

## What was not measured

- Nothing ran on a board and no Vivado run was made: every result above is simulation, Lean, or arithmetic on committed records.
- Scenario 1 is a bench of limited length (see its section): bugs that need a long fill are not reachable at the bench's length at any ppm, and are listed as such.
- The frame-error rate and real packet lengths of a feed (scenario 2); the real RTL at 33 words (scenario 3); any build at E <= 16 on a board (scenario 4); the circuit's bit skew (scenario 5); the eye on a finer grid, at 1e-9 for TX variants, or on another module (scenario 6).
