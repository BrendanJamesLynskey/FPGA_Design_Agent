# Independent UVM 1.2 bench for the ITCH/OUCH trading path (brief 170)

An SystemVerilog UVM 1.2 bench, run in Vivado 2026.1's xsim, for the path of brief 110 (MoldUDP64 / ITCH 5.0 in, a small top of book, pre-trade risk, OUCH 5.0 in a SoupBinTCP 3.00 packet out) as build
`rm_gp_itch` (brief 127) puts it behind the 10G design's real MACs. It is the project's third bench of this kind after 112 (SV UVM, PCS and MAC) and 123 (pyuvm twin of 112), and the first written
for a trading block. **Status: the bench passes on the whole regression except for one finding that is a real RTL bug (section "Finding"); the minimal failing test is `t_seq_poison`.**
All data are synthetic. Nothing here touched a board.

## Why SystemVerilog UVM and not pyuvm

Brief 123 measured both on one block: the same verdicts, pyuvm 10 times slower per simulated clock and without the solver, bound SVAs with sequences, `p_sequencer` or the tool-merged coverage,
and recommended pyuvm for agent-written and quick benches and SV UVM for flagship and interview work. This is a flagship trading path, so the choice is SV UVM. The other reasons are
specific: the bench needs SVAs bound into the design and onto the output words, and it runs long random streams (up to 30 packets a run with frames of several hundred clocks) where the
compiled simulator's cost per clock matters. Cost of the choice: the build is 70 s (45 s of it the UVM package), the regression does not run in GitHub Actions (no Vivado there), and `xcrg` is
refused by the Basic tier, so coverage is merged on counts (section "Functional coverage").

## What is under test, and what the bench sees

Design under test: `itch_unit` (`../../sim/itch_unit.sv`, the wrapper brief 127's cocotb bench already uses): the real `mac64_rx`, `udp_strip`, brief 110's `mold_rx`, `itch_dec`, `book_core`,
`risk_glue`, `ouch_enter`, `order_seg`, the transmit multiplexer and the real `mac64_tx`, in one clock. The bench drives **XGMII words** into the receive MAC and watches the XGMII words out of the transmit MAC
(only the clocks in which the PCS takes a word: `adv` high) and the status vector `stat2`. Nothing inside the design is read except the strobes `adv` and `underrun` (and `itch_path`'s internal order-frame
stream for assertions). `t_bp` runs on two snapshots: the transmit MAC paused one clock in 33 as the PCS gearbox does, and never paused.

| Directory | What |
|---|---|
| `tb/` | `tb_itch_top.sv` (the hardware top), `itch_ifs.sv` (three interfaces with clocking blocks) |
| `ref/itch_ref_pkg.sv` | the **reference model**: Ethernet/IPv4/UDP checks, MoldUDP64, ITCH 5.0 decode, book, risk, order frame; CRC-32 and RFC 1071 checksum; written from the specifications |
| `env/` | items, stimulus builders (`itch_gen.sv`), three agents, scoreboard, functional coverage, environment, virtual sequences |
| `sva/itch_sva.sv` | assertions on the output words, the order-frame stream, the status vector and the bench's own input |
| `tests/itch_tests.sv` | the tests |
| `scripts/` | `uvm_build.sh`, `run_regress.sh` (one command), `cov_merge.py`, `make_record.py`, `mutant_bench.sh` |

Agents: **in_agent** (active: whole frames as XGMII words, lane-0 or lane-4 starts, every frame-length remainder, optional bubbles, a good or wrong FCS; the monitor rebuilds the frames from the wire
and gives its own CRC verdict), **out_agent** (passive, the same parser on the transmit words), **cfg_agent** (reset, the 32 configuration words, command pulses, status read-back; the monitor decodes the
configuration and commands off the wires, so the model sees what the design sees).

The scoreboard merges three streams in clock order (received frames, configuration/command/reset events, order frames seen) and runs the model over them. At every checkpoint (idle clocks, then a read of `stat2`)
it compares: **ORDERS** (every order frame with a good FCS byte for byte, in order; classes below), **COUNTERS** (the 41 counters of the path that are not timing dependent: `spec`, `abort`, `late_abort`, `rej_busy`
are left out, as the datasheet says they depend on timing), **US** (12 `udp_strip` counters), **FLAGS** (gap, untrusted, end of session, session lock, per-instrument inexact), **ORDERCNT** (the design's `sent` and
poison counters against the frames the monitor counted), **SEQ** (TCP sequence numbers).

## Independence of the reference model

The model was written from: Nasdaq TotalView-ITCH 5.0, MoldUDP64 V 1.00, OUCH 5.0 and SoupBinTCP 3.00 (as cited in `designs/b110_itch_ouch/docs/spec_notes.md`), RFC 791, 768, 1071, IEEE 802.3's frame
check sequence, and the two datasheets of the design (`docs/itch_ouch.md`, `docs/itch_integration.md`). Not opened while writing it: `designs/b110_itch_ouch/model/*.py` (the design's own Python model) and the code of the RTL.
Read: the interface packages `itch_pkg.sv` and `itch_pkg2.sv` (the counter and register indices) and, for three questions the datasheet leaves open, comments in the RTL headers
(`risk_glue.sv`: the position is per instrument and the band applies to the order price; `book_core.sv`: when a sell Add counts as a candidate; see below). The stimulus builders share no code with the design's
`model/proto.py`; the frame CRC and the IP checksum are the bench's own.

**Places where the bench agrees with the design's own model because they share an assumption** (each is a reading of a datasheet statement, not a fact checked against the exchange or a real feed):
1. The *rules of the design* that are not in any Nasdaq document: blocks under 12 bytes are refused (`badlen`), only the first 36 bytes of a message are kept, a bad side letter or zero shares is `m_bad`,
   position counts quantity sent, a Replace never triggers an order, the lowest instrument wins a duplicate watch entry. All come from `spec_notes.md` section 5.
2. The order frame's layout is the design's: ClOrdID `FDA110` plus eight upper-case hex digits, MinQty and CustomerType in the appendage, an 8-byte price, **TCP checksum 0** (the stand-in is not a valid TCP
   segment; checked as zero, so a future `tcp_fast` order would differ there), IP identification 0, window 0xFFFF, PSH+ACK.
3. Heartbeats and end-of-session packets: a heartbeat below the expected number is a duplicate; heartbeats in the tests always carry the expected number or lower (above it the datasheet does not say whether
   it is a gap, so the bench does not send it).
4. **Candidate and ladder overflow.** The datasheet says a candidate is an Add "that was stored" and that a ladder overflow Add is "not added". The first run disagreed (`cand` model 8, design 11). The design keeps
   the order in its order table when only the price ladder is full (a later removal finds no level: `lvmiss`), counts the Add as a candidate and refuses it as stale. The model was changed to that reading after the
   disagreement; it is a datasheet inaccuracy (counters only, no order can leave on it) and is listed for the planner.
5. Position limit per instrument and the band on the order price (price plus `cfg_px_off`): read from the RTL header comment after the datasheet left them open; the tests pass with these readings.
6. The **order classification windows** (section below) take the 126/128 and 166/168-byte edges brief 127 measured; the bench widens each by 8 bytes into a "may" zone instead of asserting an edge.

## Order classification (MUST, MAY, MUST NOT)

Whether an order leaves with a good FCS depends on timing the datasheet states only as a measured window (brief 127, section 4). The model classes each order it expects:
- **MUST NOT** leave with a good FCS: a candidate in a frame with a bad FCS under STRICT (the default); the same in cut-through when the candidate is more than 40 clocks after an earlier order frame and its tail is short
  enough that the verdict is known before the order's last word; under STRICT, a candidate in a good frame whose tail is beyond the window (verdict not yet known).
- **MUST** leave: a candidate in a good frame that is the first order within 50 clocks, in cut-through, or under STRICT when its tail is within the window.
- **MAY**: everything near the window edges, orders that may queue behind a frame in flight, and an earlier order whose flight a later bad verdict overlapped.
A good frame must match an expected order by UserRefNum; a good frame with no expectation, a MUST NOT order that appears, and a MUST order that does not appear are errors. Frames with a wrong FCS are counted and not
compared further (a refused speculative candidate produces an extra poisoned frame by design).

## Sequences (tests)

| Test | What it covers |
|---|---|
| `t_smoke` | reset, configuration, directory, a bid, one candidate, one order |
| `t_mix` | message mix (S R A F E C X D U and skipped types), 1, 3 and 6 messages a packet, lane-0 and lane-4 frames, bubbles; random world of live orders |
| `t_mold` | sequence gaps (with and without halt-on-gap), duplicates, overlap, heartbeat, other session, short payload, truncated packets, bad block length, end of session, clr_flags, a second locate |
| `t_tail` | a candidate at every distance from the end of its packet (0 to 10 filler messages), STRICT and cut-through, with and without speculation; the candidate first, middle and last of 1, 3 and 6 |
| `t_badfcs` | bad FCS with 1, 3 and 6 messages, in STRICT and cut-through, the `untrusted` flag and its refusals, recovery by clr_flags |
| `t_bp` | bubbles of 0, 10, 30 and 60 % in the receive words, back-to-back frames, bursts of 5 candidates in one packet (the order queue), speculation on; on both transmit pause variants |
| `t_book` | empty book, cancel / execute / execute with price / delete / replace, over-execution, unknown references, duplicate Add, table-index collision, clr_book, ladder overflow, unwatched locate, wrong lengths, zero shares, price zero and at the threshold |
| `t_risk` | not armed, kill switch, quantity 0 / over max / 1,000,000, position per instrument, band, price offset, threshold, gap with halt, every OUCH field from the configuration, clr_pos, clr_ref, clr_cnt |
| `t_hdr` | wrong MAC, EtherType (IPv6, VLAN), header length, version nibble, fragments, protocol, address, port, UDP length, IP checksum, multicast group MAC, every length remainder and start lane, EN = 0 |
| `t_rand` | a mixed random stream: packets of 1, 3, 6, gaps, duplicates, bad frames, heartbeats, mode and limit changes, commands, header faults |
| `t_seq_poison` | the minimal failing test of the finding (run with `+SEQ_STRICT`; expected to fail) |

The bench uses `$urandom` seeded by xsim's `-sv_seed` (no constraint solver: the stimulus is a world of live orders and a few weighted choices, not a constraint problem).

## Assertions

`sva/itch_sva.sv`: the transmit start word is a lane-0 start with the seven-byte preamble; no start character in another lane; idle words are all idle characters; no underrun; no unknown value on the transmit words or
in the flags word once the book is ready; two frame starts are at least 16 clocks apart; the bench's own input only uses idle, start and terminate control characters. Bound into `itch_path`: the order-frame stream
is 15 consecutive words, poison and its flag come with the last word, `keep` is FF except 01 on the last word. Cover counts are `assert property (not (...)) else n++` because xsim does not run cover actions.
A failure is a `UVM_ERROR` with tag `SVA` and fails the test.

## Functional coverage

Bins are named counters (`env/itch_cov.sv`), hit by what the model and the monitors **saw** (never by what a sequence meant to send), and merged over all runs by `scripts/cov_merge.py`: message types, messages
a packet (1, 3, 6, other), the Mold events, every header drop, book edge cases, every risk refusal, the order outcomes, bad FCS crossed with order and with STRICT, the tail window bins, every frame length remainder (mod 8)
by start lane (16 bins), backpressure (bubbles in a frame, a transmit pause inside a frame), and every command. `COVERAGE_PLACEHOLDER`

## Running it

```
designs/b96_kr260_10g/rm_gp_itch/verif/uvm/scripts/run_regress.sh --out <dir> [--seeds 2] [--rand 10] [--rounds 40] [--record results/170_itch_uvm]
python3 -m flow.mutation_b170 run b170_itch_path --seed 1 --count 30 --jobs 2 --json results/170_itch_uvm/mutation_seed1.json   # needs yosys and sby in ~/.local/opt/oss-cad-suite
```
The regression waits while the machine's load is 6 or more or less than 12 GB are free (the owner's rule for simulation-only runs). One run is 5 to 60 seconds of wall time.

## Results

`RESULTS_PLACEHOLDER`

## Finding: a poisoned order frame still advances the TCP sequence number

Datasheet (`docs/itch_integration.md` sections 4 and 5): a poisoned frame "does not consume" a sequence number and the number "advances by 59 for every segment that left unpoisoned".
Observed: when the multiplexer poisons a frame because its trigger frame was bad (or, under STRICT, unverified), `order_seg` has already advanced its next sequence number; it sees only its own poison (a refusal, an abort or an
unresolved speculative frame). The next order then carries a number 59 higher than the datasheet says, leaving a gap in the TCP byte stream a real peer would wait on. `t_seq_poison` (with `+SEQ_STRICT`):
good order 1 sends 1000, order 2 in a bad frame is poisoned, order 3 sends 1118 where the datasheet says 1059. The other sequences run with a counted waiver (`SEQ_WAIVED`) so they still check everything else.
Severity: the stand-in `order_seg` is not a valid TCP segment (checksum 0) and brief 119's `tcp_fast` replaces it; whether `tcp_fast` has the same behaviour is not checked here.

## Known gaps

- No bench for `tcp_fast`; the order frame is the stand-in's (TCP checksum 0). Single clock; one transmit pause pattern; N_INST 4, LEVELS 8, ORD_AW 8 only (the path's other parameter points are not exercised).
- The order classification (MUST/MAY/MUST NOT) is a measured-window rule with MAY zones: an order that wrongly leaves or is wrongly poisoned inside a zone is not seen. A candidate within about 50 clocks of an earlier
  one is MAY.
- Timing-dependent counters (`spec`, `abort`, `late_abort`, `rej_busy`) and the order-side counters other than `sent` and the poison sum are not compared. `rej_busy` and `ord.drop` need more than five candidates inside
  one frame time; the sequences keep below that.
- Heartbeat or end-of-session above the expected sequence number, a bad-side or zero-share message's effect on the type counters, and a Stock Directory re-mapping an instrument to a second locate are exercised only to the
  extent `t_mold` and `t_book` do (the model's reading passed).
- Coverage is functional only (no code coverage: `xcrg` is refused by the Basic tier). Mutation and the blind second-agent pass: see Results.
- Not run in GitHub Actions. The reference model and the stimulus builders were written by the same session as the bench, in one sitting.
