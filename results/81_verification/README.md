# Brief 81: unbounded proofs, equivalence checking and a recorded formal counterexample

Three new formal records, made for the site's Verification page. All use the OSS CAD Suite release 2026-11-12 (build 20261112:
Yosys 0.70+385, SymbiYosys, eqy, z3, ABC), the release CI pins for its network-block formal step. No Vivado, board or paid
agent run was used. Every number the page shows from these files is read from them by `site/verification.py`.

## Records

| File | What | Made by |
|---|---|---|
| `unbounded.json` | six attempts to prove, for all cycles, the "quiet" property of the AXI4-Lite checker and of the AXI4-Stream checker (never fires on legal traffic) and the slave rules of the generated register block `demo_accel`: k-induction (`smtbmc z3`, prove mode) and PDR (`abc pdr`) on each, with status and seconds | `python3 axi_tx/formal/unbounded.py` |
| `equivalence.json` | three eqy comparisons of the generated register block `demo_accel_regs`: the committed block before and after brief 73 (interface profiles), and the house profile against `amd_compatible` and against `strict` | `python3 hwsw/equiv.py` |
| `demo_accel_regs_before_73.sv` | the generated block as committed before brief 73 (`git show 1c21d598:hwsw/examples/generated/demo_accel_regs.sv`), kept so the comparison reproduces without the history | copied from git |
| `counterexample.json` | the signals of the counterexample SymbiYosys finds when the AXI4-Lite checker carries the mutation `b_early_aw_only` (early write response checked against the address channel alone), with the cycles where the mutated checker flags the rule | `python3 axi_tx/formal/counterexample.py` |

## Results

- **Unbounded proofs.** k-induction returned UNKNOWN on all three blocks (no invariant was written, and the cause of each unknown
  was not investigated). PDR proved all three for every cycle, in seconds.
- **Equivalence.** The before and after block is proved equivalent (the generator change added comment lines and a profile banner
  only). `house` against `amd_compatible` and against `strict` are reported different, as intended (error-capture registers removed;
  rejections added). The equivalent case took the longest, about five minutes, because every register must be proved.
- **Counterexample.** The seed proof for rule B_EARLY fails at step 3 (search depth 12) on the mutant; the trace shows an address
  accepted, a write response valid, no write data, and the mutated checker flagging at the first cycle only.

## Parameters and how it was checked

- Properties and assumptions are the ones of the bounded proofs: `axi_tx/formal/formal_axil_rules.sv` and `formal_axis_rules.sv`
  with `-DQUIET`, and `hwsw/tests/regmap_formal.py` for the register block. The bounded proofs have cover tasks that reach the
  interesting events, so the assumptions are not contradictory. A PDR pass in seconds was not treated as a proof by itself for that reason.
- eqy: `prep -top demo_accel_regs` on both sides, registers matched by name, strategy `sby`, depth 5, engine `smtbmc z3`.
- `site/tests/test_verification.py` checks that the page text matches these records (for example, that the counterexample still has
  no write data and a silent checker at the step the page describes).

## Known gaps and limits

- Three blocks only. The 63D network blocks and the MAC FSMs are not attempted with PDR; the MAC FSMs' k-induction returned
  unknown in brief 58A.
- PDR proves "never fires on legal traffic" for the checkers under free inputs; it does not show the rules are the right rules (that is
  the seed proofs and mutants, `results/59a_axi_tx`).
- eqy equivalence is of designs with the same register names; the strict-against-house difference is shown, not explained, by this file.
- One run each; the times are one run on a shared PC.
- The counterexample uses a different Yosys (0.70) from the 59A records (0.33).

## Next steps

PDR on the network-block proofs that are bounded today; an eqy run on every regenerated register block in CI.

## Reproduce

```
export FDA_OSS_CAD=<OSS CAD Suite 2026-11-12 folder>
python3 axi_tx/formal/unbounded.py            # a few minutes
python3 hwsw/equiv.py                          # about 15 minutes
python3 axi_tx/formal/counterexample.py        # seconds
```
Heavy local jobs on this PC take a slot first (`_handoff/take_heavy_slot.sh`).
