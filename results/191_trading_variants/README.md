# results/191_trading_variants: trading-path variants, induction proofs and a processor-to-fabric probe (brief 191)

Records of brief 191 (2026-11-23), stacked on brief 188 (PR #311). Ideas from Edwards 2026 (ch 4, 9, 12, 13), written from scratch; no book text, table or code was copied and the private backlog files are not in the repository. All traffic is synthetic. Nothing ran on a board.

## Records
- `sim/`: measured simulation records: `lane_by_type.json` (72 of 72 type-by-start-lane bins), `reject_bits_latency.json`, `feed_arb_latency.json`, `feed_arb_fill_window.json`, `feed_arb_deep_skew_aw5.json` / `_aw8.json`, `probe_sim.json`, and the b110 bench's own records (`latency_sim.json`, `coverage_sim.json`, ...).
- `pytest_junit.xml`: the b110 model, cocotb benches (the new `lane_by_type`, `reject_bits`, the dual-feed module of 14 tests), lint at seven parameter points, SymbiYosys (bmc, prove, cover), b191 probe and host tests, b119, b96 rate-matcher formal CI set and the b127 tests.
- `ooc/`: out-of-context Vivado 2026.1 place-and-route on the K26: `dec_ip0.json`, `dec_ip1.json` (itch_dec alone, 6.2061, 3.6, 3.0 ns), `top_base.json`, `top_inplace.json`, `top_dual.json` (itch_ouch_top at 6.2061 ns). Run by `ooc_all.sh` in one heavy slot.
- `formal_book.json`: k-induction on book_core (`designs/b110_itch_ouch/verif/formal/run_book_formal.py`); `formal_book_draft_with_seven_invariants.json` the first draft. `formal_rm_gp_pdr.json/.md`: IC3/PDR on the rate matcher's progress property.
- `mutation_final.json` (33 changed or new seeded faults), `mutation_rerun2.json` (the one survivor after a test was added), `mutation_probe.json` (12 faults in the PS-AXI probe).
- `uvm/`: the full UVM regression of briefs 170/176 on the final RTL.

## Measured
**Parse in place (item 21).** Same events, counters and latency (whole bench, both decoders; every one of 9 types in each of 8 start lanes, 72 of 72 bins, read where the messages lie). Out of context, `itch_dec` alone: shift decoder 570 LUT, closes 3.0 ns (WNS +0.24, 6 LUT levels); in-place 1782 LUT, **fails 3.0 ns (WNS -0.084)**, closes 3.6 ns (+0.23); both 6 levels at the worst path. In the whole top at 6.2061 ns: base 6836 LUT, WNS +0.075; in place 7899 LUT, WNS +0.385 (the slack gain is placement, not the decoder: the decoder's standalone path is not faster). **Negative result**: the wide byte shifter is already only five to six LUT levels once Vivado prunes it to the bytes used, so fixed-lane wiring buys no depth and costs 3 times the LUTs. Left as a parameter (default 0).
**Reject bits and equal latency (item 23).** `vd_v` is 8 clocks after the last byte of the candidate for the accept, each of 7 single rejects, several rejects and gap+stale+size, with and without speculation; `vd_rej` equals the model's independent evaluation (the seven clock-free check bits). The base build's WNS fell from +0.218 (brief 188 record) to +0.075 ns with this brief's RTL (6.2061 ns, same parameters); it still closes.
**A/B feed arbiter (item 24).** +4 clocks (book update 11, first order word 12) from either feed; fill window: a lost packet is filled iff the other copy's header is in before the next packet's (see `feed_arb_fill_window.json`: filled below the packet pitch, not at or above it); FIFO overflow is loud (s_err) and a deep FIFO (ARB_AW 8) clean. Out of context at 6.2061 ns: base 6836 LUT / 6024 FF, WNS +0.075; DUAL_FEED 1: 8182 LUT / 6889 FF (the arbiter 1526 LUT: feed A's input stage 976, B's 377), WNS +0.112, WHS +0.044, no DSP or block RAM; closes.
**Formal (item 22).** book_core Q1-Q6: k-induction closes at depth 1 with two invariants (swept entries are zero; no live level or order of zero size) for N_INST 2 (LEVELS 4 and 8); each invariant is needed (ablation), and five seeded faults are caught. N_INST not a power of two (3): BMC only, induction open (instrument index beyond the last). rate_match_gp progress (R1, R2): proved unbounded by `abc pdr` at AW 2 (447.4 s) and AW 1 (45.2 s), the no-slot-clock mutant caught, safety re-proved (17 s).
**UVM regression** (final RTL, one copy at a time): 40 runs, 0 failed, 0 SVA failures, SEQ 538 compared / 0 mismatches, 97 of 97 bins.
**Seeded faults**: 33 changed or new mutants: 32 killed first time; `arb_idle_short` survived and was killed after a test that measures the idle clocks at the parser's input (`ab_interleave`); `risk_seen_not_sticky` was killed after a history check (earlier run). Probe: 12 of 12.

## Illustrative or not measured
Synthetic data. No board run; the PS-AXI image was **not built** (recipe only). The brief 188 mutation floor (60 % worst case) was not re-measured. Latencies are simulation, Icarus.

## Known gaps and limits
No reorder buffer in the arbiter (documented fill window); a bad frame on the first copy is not repaired; rm_gp_itch (board build) not rebuilt: b96's `itch_top.sv` only gained unconnected observation pins. k-induction for non-power-of-two N_INST and PDR at AW 4 for the rate matcher not done. The probe's design.xdc clock line is untested.

## Reproduce
`python3 -m pytest -q designs/b110_itch_ouch/tests designs/b191_ps_axi_lat/tests`; `python3 designs/b110_itch_ouch/tests/run_mutants.py --only <names>`; `python3 designs/b110_itch_ouch/verif/formal/run_book_formal.py`; `python3 designs/b96_kr260_10g/verif/formal/run_formal.py --set pdr`; `results/191_trading_variants/ooc_all.sh`; UVM: `designs/b96_kr260_10g/rm_gp_itch/verif/uvm/scripts/run_regress.sh --out <dir> --record results/191_trading_variants/uvm`.
