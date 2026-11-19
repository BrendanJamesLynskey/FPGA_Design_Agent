# A real frequency offset for the 10G link: plan for the owner to approve (brief 96E)

Status: a plan only. Nothing here has been bought, wired or run. Each step that touches hardware waits for the owner's yes.

## The problem

The rate-matching buffer (`RATE_MATCH = 1`) has only been exercised against a simulated partner at +-100 and +-300 ppm (`results/b96c/ppm_sim_ratematch.json`). On the board the receive clock is recovered from our own
transmission in the fibre loopback, so it has exactly the transmit clock's frequency: the frequency counter (RXV27, RXV28) reads 0 ppm. Brief 96C tried to make an offset with the GT's TX phase interpolator
(TXPIPPM); the counter read 0.0 ppm at every code (steps 0 to 9), because TXUSRCLK2 follows the shifted serial clock and one reference feeds both directions. An offset needs the received data to come from a
**different oscillator** than the one that clocks our transmitter.

## What gives a different oscillator (options, cheapest change first)

| Option | What is needed | Offset you get | Risks and unknowns |
|---|---|---|---|
| A. A second board of the same kind, link through an SFP+ DAC or a pair of modules and fibre | A second KR260 (or any board with an SFP+ cage and a GTH/GTY), both loaded with this design | Whatever the two reference oscillators differ by: typically some tens of ppm, **unknown until measured**; our own frequency counter measures it | Needs a second board and a second power supply; the offset is not chosen, only measured. It may be near 0 ppm by luck (then no test), so the plan below measures first |
| B. A 10G NIC, switch or media converter with an SFP+ port | The owner's own hardware; a DAC or modules and fibre; a host that sends frames | The partner's oscillator error, within the +-100 ppm of IEEE 802.3 clause 49 | Real traffic with a real MAC and PCS (this also tests interoperability, which a PCS talking to itself cannot); the offset is fixed and unknown until measured; the partner's idle behaviour is not ours to choose |
| C. A second board whose GT reference is driven from an adjustable clock source (a programmable clock generator set to 156.25 MHz plus or minus the wanted ppm) | The second board's reference pins must be reachable (the KR260 carrier's reference is a board oscillator; whether its MGTREFCLK0 pins can be driven from outside is **not known**: UG1092 has no clock table, `docs/design.md` section 1) | Chosen: +-50, +-100, +-150 ppm as the generator's resolution allows | Probably needs board modification or a different board with a reference input (SMA); not recommended before A or B has shown whether it is needed |
| D. A Pmod or other fabric clock | The GT reference pins are not Pmod pins; a fabric clock cannot drive the GTH reference | none | Not a route; listed because the brief asked |

The loopback on one board cannot give an offset by any route found so far (96C measured the TX phase interpolator route: no relative offset).

## Proposed order

1. **Measure the offset we already have for free (no change).** Nothing to do: with option A or B the first link-up reports the offset in RXV27 and RXV28 (the receive clock's cycles in a 2^24 core-clock window, 0.1 ppm resolution).
   Decision: if the measured offset is below about 5 ppm the setup is useless for a rate-matching test (insert/delete would happen about once in 20,000 blocks or less); try the other option.
2. **Setup (owner)**: option A or B as above, an SFP+ DAC or two modules and an OS2 patch lead as already used. No wiring beyond the SFP+ cage. Class 1 laser rules as before for modules.
3. **Run (executor, board.lock)**: the same session as `run_96c_stage3.sh` (restarts, safety, dwell) on the `rm_ctl` (macro buffer) and `rm_gp` (own buffer) builds, for 20 s dwells with armed feed frames, recording RXV18 to RXV26 (inserts, deletes, stalls, overflow, fill) and the counter-measured ppm.
   Acceptance per point, as for 96C: every order sent = fired = `order_ok`, every fault counter 0, overflow 0; with an offset, inserts (partner slower) or deletes (partner faster) per second within 15 % of `ppm x 1e-6 x 161,132,812.5 x 32/33`.
   The sign of the offset is seen from the counter: positive means the receive clock is faster, so deletes are expected.
4. **If neither A nor B gives at least about 20 ppm**: C, which needs the owner to say whether a board modification is acceptable.

## What the owner has to decide

- Which of A or B is available (a second board, or a 10G NIC or switch with an SFP+ port).
- Whether any purchase is wanted at all. None is proposed here.

## What this does not claim

No offset has been made on hardware. The partner in simulation is our own Python model, so it shares our reading of the block formats; a NIC (option B) would be the first independent check of that.
